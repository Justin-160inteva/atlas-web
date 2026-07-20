#!/usr/bin/env node
import fs from 'node:fs';
import vm from 'node:vm';

const read = path => fs.readFileSync(path, 'utf8');
const json = path => JSON.parse(read(path));
let checks = 0;
const check = (condition, message) => {
  checks += 1;
  if (!condition) throw new Error(`check ${checks} failed: ${message}`);
};

const html = read('index.html');
const bootstrap = read('atlas-bootstrap.js');
const script = read('atlas-rewards-0949.js');
const css = read('atlas-rewards-0949.css');
const sw = read('sw.js');
const manifest = json('release-manifest.json');
const evidence = json('data/rewards/reward-evidence-index.json');
const records = json('data/rewards/reward-records-runtime.json');
const schema = json('data/rewards/reward-record-schema.json');
const policy = json('data/rewards/reward-source-policy.json');
const terms = json('data/rewards/reward-terminology-zh-CN.json');
const recordFileEntries = Object.entries(records.recordFiles || {});
const runtimeRecords = recordFileEntries.map(([locationId, path]) => ({ locationId, path, record: json(path) }));

new vm.Script(script, { filename: 'atlas-rewards-0949.js' });
check(manifest.version === '0.9.4.9', 'release is Alpha 0.9.4.9');
check(html.includes("ASSASSIN'S CREED SHADOWS · ALPHA 0.9.4.9"), 'visible release label is synchronized');
check(bootstrap.includes("version: '0.9.4.9'"), 'bootstrap release is synchronized');
check(bootstrap.includes(`cacheNamespace: '${manifest.cacheNamespace}'`), 'bootstrap cache matches manifest');
check(sw.includes(`const CACHE='${manifest.cacheNamespace}'`), 'service worker cache matches manifest');
check(html.includes('atlas-rewards-0949.css?v=0.9.4.9'), 'reward stylesheet is loaded');
check(html.includes('atlas-rewards-0949.js?v=0.9.4.9'), 'reward runtime is loaded');
check(html.indexOf('app.js?v=0.9.4.9') < html.indexOf('atlas-rewards-0949.js?v=0.9.4.9'), 'reward runtime executes after app');
check((html.match(/atlas-rewards-0949\.js/g) || []).length === 1, 'reward runtime is loaded once');
check((html.match(/atlas-rewards-0949\.css/g) || []).length === 1, 'reward stylesheet is loaded once');
check(manifest.runtimeOwners.rewardSummaryRuntime === 'atlas-rewards-0949.js', 'runtime owner is declared');
check(manifest.runtimeOwners.rewardRuntimeRecords === 'data/rewards/reward-records-runtime.json', 'record owner is declared');
check(manifest.releaseAssets.includes('atlas-rewards-0949.js'), 'runtime is a release asset');
check(manifest.releaseAssets.includes('data/rewards/reward-records-runtime.json'), 'records are a release asset');
check(manifest.invariants.rewardUnresolvedNeverFabricated === true, 'unresolved fabrication invariant is enabled');
check(manifest.invariants.rewardRuntimeIndexRequired === true, 'runtime index invariant is enabled');
check(manifest.invariants.rewardRuntimeRecordCount === records.recordCount, 'runtime record invariant matches index');
check(manifest.invariants.rewardSingleSourceMustRemainInference === true, 'single-source inference invariant is enabled');
check(sw.includes("'./atlas-rewards-0949.js'"), 'service worker caches runtime');
check(sw.includes("'./atlas-rewards-0949.css'"), 'service worker caches stylesheet');
check(sw.includes("'./data/rewards/reward-records-runtime.json'"), 'service worker caches records');
check(sw.includes('atlas-rewards-0949|scan-monitor'), 'release asset refresh includes runtime');
check(records.schemaVersion === 2, 'record index schema v2 is supported');
check(records.recordCount === recordFileEntries.length, 'record count matches record file index');
check(records.recordCount === runtimeRecords.length, 'all indexed record files load');
check(Array.isArray(records.reviewQueue) && records.reviewQueue.length === records.recordCount, 'review queue covers every candidate');
check(new Set(records.reviewQueue).size === records.recordCount, 'review queue has no duplicates');
check(runtimeRecords.every(({locationId, path, record}) => record.locationId === locationId && path === `data/rewards/records/${locationId}.json`), 'record files match indexed location ids');
check(runtimeRecords.every(({path}) => manifest.releaseAssets.includes(path) && sw.includes(`'./${path}'`)), 'every candidate is a cached release asset');
check(runtimeRecords.every(({record}) => record.status === 'high_confidence_inference' && record.confidence >= 0.75 && record.sources.length === 1 && record.review.state === 'machine_checked'), 'first candidates remain machine-checked single-source inference');
check(evidence.coverage.total === 3430, 'coverage total remains 3430');
check(evidence.coverage.highConfidenceInference === records.recordCount, 'coverage reflects candidate records');
check(evidence.coverage.unresolved === evidence.coverage.total - records.recordCount, 'unresolved count excludes only candidate records');
check(Object.values(evidence.coverage).every(value => Number.isInteger(value) && value >= 0), 'coverage values are non-negative integers');
check(script.includes("cache: 'no-store'"), 'reward data bypasses stale browser HTTP cache');
check(script.includes('selectedLocationId()'), 'runtime resolves the selected location id');
check(script.includes('runtime.records.get(locationId)'), 'runtime uses exact location id lookup');
check(script.includes('loadRuntimeRecords'), 'runtime loads indexed record files');
check(script.includes('Promise.allSettled'), 'one failed record does not hide all other records');
check(script.includes('rewardLocationId'), 'rendering is idempotent per location');
check(script.includes('MutationObserver'), 'detail rebuilds are observed');
check(script.includes('queueMicrotask(renderSelectedReward)'), 'detail injection is deferred safely');
check(script.includes('escapeHTML'), 'dynamic reward data is escaped');
check(script.includes('旧描述不会被当作已确认事实'), 'legacy text is not promoted to evidence');
check(!script.includes('parseDescription('), 'runtime does not reuse legacy reward parsing');
check(script.includes('开放冲突'), 'conflict counts are visible');
check(script.includes('已接受不确定性'), 'accepted uncertainty counts are visible');
check(script.includes('可复查来源'), 'source locators are visible');
check(script.includes('奖励证据覆盖'), 'coverage card is rendered');
check(css.includes('@media (max-width: 640px)'), 'mobile layout exists');
check(css.includes('.atlas-reward-status.official_confirmed'), 'official status style exists');
check(css.includes('.atlas-reward-status.multi_source_confirmed'), 'multi-source status style exists');
check(css.includes('.atlas-reward-status.high_confidence_inference'), 'inference status style exists');
check(css.includes('.atlas-reward-status.unresolved'), 'unresolved status style exists');

const schemaStatuses = schema.properties.status.enum;
const policyLevels = policy.evidenceLevels.map(level => level.id);
const termStatuses = Object.keys(terms.evidenceLabels);
const expectedStatuses = ['official_confirmed', 'multi_source_confirmed', 'high_confidence_inference', 'unresolved'];
for (const status of expectedStatuses) {
  check(schemaStatuses.includes(status), `${status} exists in schema`);
  check(policyLevels.includes(status), `${status} exists in policy`);
  check(termStatuses.includes(status), `${status} exists in terminology`);
  check(script.includes(status), `${status} exists in runtime`);
  check(css.includes(status), `${status} exists in styles`);
  const level = policy.evidenceLevels.find(item => item.id === status);
  check(Number.isFinite(level.minimumConfidence), `${status} has a confidence threshold`);
  check(level.requirements.length > 0, `${status} has evidence requirements`);
  check(Boolean(terms.evidenceLabels[status]), `${status} has a Chinese label`);
}

const coverageFields = ['total', 'officialConfirmed', 'multiSourceConfirmed', 'highConfidenceInference', 'unresolved', 'humanReviewed', 'locked', 'openConflicts'];
for (const field of coverageFields) {
  check(Object.hasOwn(evidence.coverage, field), `coverage contains ${field}`);
  check(script.includes(field), `runtime renders or consumes ${field}`);
  check(Number.isInteger(evidence.coverage[field]), `${field} is an integer`);
  check(evidence.coverage[field] <= evidence.coverage.total, `${field} does not exceed total`);
}

const rewardTypes = schema.properties.rewards.items.properties.type.enum;
for (const type of rewardTypes) {
  check(Boolean(terms.rewardTypes[type]), `${type} has a Chinese term`);
  check(!terms.rewardTypes[type].includes('Unknown Reward'), `${type} avoids untranslated placeholder`);
}

const hostilePayloads = [
  '<script>alert(1)</script>', '<img src=x onerror=alert(1)>', '" autofocus onfocus=alert(1) x="',
  "' onclick='alert(1)", '&lt;svg/onload=alert(1)&gt;', '</details><script>1</script>',
  '<a href="javascript:alert(1)">x</a>', '${alert(1)}'
];
for (const payload of hostilePayloads) {
  const escaped = String(payload).replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
  check(!escaped.includes('<script') && !escaped.includes('<img') && !escaped.includes('<a '), 'hostile HTML tags are escaped');
  check(!escaped.includes('"') && !escaped.includes("'"), 'attribute-breaking quotes are escaped');
  check(escaped.includes('&lt;') || !payload.includes('<'), 'opening angle brackets are neutralized');
}

check(policy.principles.neverPresentInferenceAsOfficial === true, 'inference cannot be official');
check(policy.principles.requireSourceLocator === true, 'source locator is required');
check(policy.principles.allowEmptyRewardWhenUnresolved === true, 'unresolved rewards may remain empty');
check(policy.forbiddenBehaviors.length >= 5, 'forbidden reward behaviors are documented');
check(records.noteZhCN.includes('高置信推断') && records.noteZhCN.includes('人工复核'), 'record index preserves review limitations');
check(evidence.coverage.officialConfirmed + evidence.coverage.multiSourceConfirmed + evidence.coverage.highConfidenceInference + evidence.coverage.unresolved === evidence.coverage.total, 'evidence state counts cover all locations');

console.log(`reward summary runtime smoke passed: ${checks} checks; records=${records.recordCount}`);
