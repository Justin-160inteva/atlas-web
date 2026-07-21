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
const numericRewardTypes = new Set(['experience', 'skill_point']);
const supportCount = (reward, sources) => {
  const token = `reward:${reward.type}:${reward.nameOriginal || reward.nameZhCN}`;
  return sources.filter(source => Array.isArray(source.supports) && source.supports.includes(token)).length;
};
const version = manifest.version;
const versionText = manifest.versionText;

new vm.Script(script, { filename: 'atlas-rewards-0949.js' });
check(/^0\.9\.4\.\d+$/.test(version), `release version is valid: ${version}`);
check(html.includes(versionText), 'visible release label is synchronized');
check(bootstrap.includes(`version: '${version}'`), 'bootstrap release is synchronized');
check(bootstrap.includes(`cacheNamespace: '${manifest.cacheNamespace}'`), 'bootstrap cache matches manifest');
check(sw.includes(`const CACHE='${manifest.cacheNamespace}'`), 'service worker cache matches manifest');
check(html.includes(`atlas-rewards-0949.css?v=${version}`), 'reward stylesheet is loaded');
check(html.includes(`atlas-rewards-0949.js?v=${version}`), 'reward runtime is loaded');
check(html.indexOf(`app.js?v=${version}`) < html.indexOf(`atlas-rewards-0949.js?v=${version}`), 'reward runtime executes after app');
check((html.match(/atlas-rewards-0949\.js/g) || []).length === 1, 'reward runtime is loaded once');
check((html.match(/atlas-rewards-0949\.css/g) || []).length === 1, 'reward stylesheet is loaded once');
check(manifest.runtimeOwners.rewardSummaryRuntime === 'atlas-rewards-0949.js', 'runtime owner is declared');
check(manifest.runtimeOwners.rewardRuntimeRecords === 'data/rewards/reward-records-runtime.json', 'record owner is declared');
check(manifest.releaseAssets.includes('atlas-rewards-0949.js'), 'runtime is a release asset');
check(evidence.coverage.total === 3430, 'reward coverage total is preserved');
check(records.recordCount === runtimeRecords.length, 'runtime reward record count is coherent');
check(runtimeRecords.every(({ record }) => record.status === 'high_confidence_inference'), 'candidate records remain labeled inference');
check(runtimeRecords.every(({ record }) => record.rewards.every(reward => supportCount(reward, record.sources) >= (numericRewardTypes.has(reward.type) ? 2 : 3))), 'per-reward source coverage remains qualified');
check(schema.properties.confidence.minimum === 0 && schema.properties.confidence.maximum === 1, 'confidence schema remains bounded');
check(policy.principles.neverPresentInferenceAsOfficial === true, 'inference cannot be presented as official');
check(terms.locale === 'zh-CN', 'reward terminology locale remains zh-CN');
check(css.includes('@media (max-width: 640px)'), 'mobile reward layout remains available');

console.log(`reward summary runtime smoke passed: ${checks} checks; release=${version}; records=${records.recordCount}`);
