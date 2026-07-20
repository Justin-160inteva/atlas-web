import fs from 'node:fs/promises';

const read = path => fs.readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [manifestText, searchSource, rewardCss, serviceWorker, html] = await Promise.all([
  read('release-manifest.json'),
  read('location-search-patch.js'),
  read('atlas-rewards-0949.css'),
  read('sw.js'),
  read('index.html')
]);
const manifest = JSON.parse(manifestText);
const checks = {
  searchOwnerRegistered: manifest.runtimeOwners?.locationSearch === 'location-search-patch.js',
  searchAssetRegistered: manifest.releaseAssets?.includes('location-search-patch.js'),
  singleControllerRequired: manifest.invariants?.singleLocationSearchController === true,
  exactRankingRequired: manifest.invariants?.rewardSearchExactMatchesFirst === true,
  matchedRewardOnlyRequired: manifest.invariants?.rewardSearchMatchedRewardOnly === true,
  viewportSettleRequired: manifest.invariants?.rewardSearchWaitsForViewportSettle === true,
  ownerV2Installed: searchSource.includes("const OWNER = 'reward-aware-bilingual-search-v2'") && searchSource.includes('window.AtlasSearchOwner = OWNER'),
  ownerDatasetInstalled: searchSource.includes('dataset.atlasSearchOwner = OWNER'),
  localizedAliasesUsed: searchSource.includes('const aliases = [reward.nameOriginal, reward.nameZhCN]') && searchSource.includes('item.aliases.includes(query.normalized)'),
  localizedLocationAliasesUsed: searchSource.includes('titleAliases: [location.title_zh, location.title, location.title_en]') && searchSource.includes('document.titleAliases.includes(query.normalized)'),
  exactRewardTier: searchSource.includes("kind = 'reward-exact'") && searchSource.includes("label = '奖励精确匹配'"),
  exactLocationTier: searchSource.includes("kind = 'location-exact'") && searchSource.includes("label = '地点精确匹配'"),
  deterministicTierSort: searchSource.includes('right.tier - left.tier') && searchSource.includes("localeCompare(right.document.titleZh, 'zh-CN')"),
  everyTokenMustMatch: searchSource.includes('if (!matched) return null'),
  matchedRewardMapUsed: searchSource.includes('const matchedRewards = new Map()') && searchSource.includes('rewardNames: [...matchedRewards.keys()]'),
  matchedRewardHintEscaped: searchSource.includes('命中奖励：') && searchSource.includes('escapeHTML(item.rewardNames.slice(0, 2).join'),
  resultDelegationUsed: searchSource.includes("event.target.closest('.result-item[data-id]')") && searchSource.includes('String(item.id) === String(button.dataset.id)'),
  keyboardBlurBeforeFocus: searchSource.includes('if (input) input.blur()') && searchSource.indexOf('if (input) input.blur()') < searchSource.indexOf('closeSearch()'),
  visualViewportObserved: searchSource.includes('const visual = window.visualViewport') && searchSource.includes('stableFrames >= 2'),
  focusTimeoutBounded: searchSource.includes('performance.now() - startedAt >= 480'),
  searchApiExposed: searchSource.includes('window.AtlasSearch = Object.freeze'),
  resultBadgeStyled: rewardCss.includes('.atlas-search-match') && rewardCss.includes('.atlas-search-match.reward'),
  mobileTouchTargetStyled: rewardCss.includes('.result-item { min-height: 68px; padding: 10px; }'),
  exactResultStyled: rewardCss.includes('.result-item[data-search-kind$="exact"]'),
  serviceWorkerRefreshesSearch: serviceWorker.includes('location-search-patch|page-zoom-guard'),
  singleSearchScriptTag: (html.match(/location-search-patch\.js/g) || []).length === 1,
  searchLoadedAfterRewards: html.indexOf('atlas-rewards-0949.js') < html.indexOf('location-search-patch.js')
};

const failed = Object.entries(checks).filter(([, passed]) => !passed).map(([name]) => name);
const report = {
  schemaVersion: 1,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: failed.length === 0,
  totalChecks: Object.keys(checks).length,
  failed,
  checks
};
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/reward-search-contract.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(`Reward search contract: ${report.totalChecks - failed.length}/${report.totalChecks}; failed=${failed.join(',') || 'none'}`);
if (failed.length) process.exit(2);
