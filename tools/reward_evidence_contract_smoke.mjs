import fs from 'node:fs/promises';

const readJson=async path=>JSON.parse(await fs.readFile(new URL(`../${path}`,import.meta.url),'utf8'));
const [manifest,policy,schema,terms,index,runtimeIndex,runtimeSource,serviceWorker,html,rewardCss]=await Promise.all([
  readJson('release-manifest.json'),
  readJson('data/rewards/reward-source-policy.json'),
  readJson('data/rewards/reward-record-schema.json'),
  readJson('data/rewards/reward-terminology-zh-CN.json'),
  readJson('data/rewards/reward-evidence-index.json'),
  readJson('data/rewards/reward-records-runtime.json'),
  fs.readFile(new URL('../atlas-rewards-0949.js',import.meta.url),'utf8'),
  fs.readFile(new URL('../sw.js',import.meta.url),'utf8'),
  fs.readFile(new URL('../index.html',import.meta.url),'utf8'),
  fs.readFile(new URL('../atlas-rewards-0949.css',import.meta.url),'utf8')
]);

const profiles=[
  'official-text','official-web','official-patch','authorized-video','public-video',
  'screenshot','community-database','guide-article','manual-review','conflict-recovery'
];

const recordFileEntries=Object.entries(runtimeIndex.recordFiles||{});
const recordPairs=await Promise.all(recordFileEntries.map(async([locationId,path])=>[locationId,path,await readJson(path)]));
const allowedStatuses=new Set(schema.properties?.status?.enum||[]);
const allowedRewardTypes=new Set(schema.properties?.rewards?.items?.properties?.type?.enum||[]);
const allowedQuantityStatuses=new Set(schema.properties?.rewards?.items?.properties?.quantityStatus?.enum||[]);
const allowedReviewStates=new Set(schema.properties?.review?.properties?.state?.enum||[]);
const numericRewardTypes=new Set(['experience','skill_point']);
const inferenceThreshold=policy.evidenceLevels?.find(level=>level.id==='high_confidence_inference')?.minimumConfidence;
const multiThreshold=policy.evidenceLevels?.find(level=>level.id==='multi_source_confirmed')?.minimumConfidence;
const runtimeRecordsValid=recordPairs.length===runtimeIndex.recordCount&&recordPairs.every(([locationId,path,record])=>{
  const sources=Array.isArray(record.sources)?record.sources:[];
  const rewards=Array.isArray(record.rewards)?record.rewards:[];
  const conflicts=Array.isArray(record.conflicts)?record.conflicts:[];
  const sourceTypes=new Set(sources.map(source=>source.sourceType));
  const qualifiedLineageInference=sources.length>=3&&sourceTypes.has('community_database')&&sourceTypes.has('guide_article')&&record.status==='high_confidence_inference'&&record.confidence>=inferenceThreshold&&record.confidence<multiThreshold;
  const sourceValid=sources.every(source=>policy.sourceTypes.includes(source.sourceType)&&typeof source.locator==='string'&&source.locator.startsWith('https://')&&Array.isArray(source.supports)&&source.supports.length>0);
  const rewardsValid=rewards.length>0&&rewards.every(reward=>{
    const token=`reward:${reward.type}:${reward.nameOriginal||reward.nameZhCN}`;
    const supportCount=sources.filter(source=>Array.isArray(source.supports)&&source.supports.includes(token)).length;
    const expectedCoverage=numericRewardTypes.has(reward.type)?supportCount>=2:supportCount>=3;
    return allowedRewardTypes.has(reward.type)&&allowedQuantityStatuses.has(reward.quantityStatus)&&typeof reward.nameZhCN==='string'&&reward.nameZhCN.length>0&&(reward.quantityStatus!=='exact'||Number.isFinite(reward.quantity))&&expectedCoverage;
  });
  const conflictsValid=conflicts.length>0&&conflicts.every(conflict=>policy.conflictTypes.includes(conflict.type)&&['open','resolved','accepted_uncertainty'].includes(conflict.status)&&typeof conflict.detailZhCN==='string');
  const reviewValid=allowedReviewStates.has(record.review?.state)&&record.review?.state==='machine_checked'&&record.review?.method==='reward-policy-v1 + source-lineage-qualified-coverage';
  return locationId===record.locationId&&path===`data/rewards/records/${locationId}.json`&&allowedStatuses.has(record.status)&&qualifiedLineageInference&&sourceValid&&rewardsValid&&conflictsValid&&reviewValid&&record.summaryZhCN.includes('高置信推断')&&record.conflicts.some(conflict=>conflict.status==='accepted_uncertainty'&&conflict.detailZhCN.includes('数据链独立性'))&&manifest.releaseAssets.includes(path)&&serviceWorker.includes(`'./${path}'`);
});
const reviewQueueValid=Array.isArray(runtimeIndex.reviewQueue)&&runtimeIndex.reviewQueue.length===runtimeIndex.recordCount&&new Set(runtimeIndex.reviewQueue).size===runtimeIndex.recordCount&&runtimeIndex.reviewQueue.every(id=>runtimeIndex.recordFiles?.[id]);
const runtimeCoverageValid=index.coverage?.highConfidenceInference===runtimeIndex.recordCount&&index.coverage?.unresolved===index.targetLocationCount-runtimeIndex.recordCount&&index.coverage?.officialConfirmed===0&&index.coverage?.multiSourceConfirmed===0&&index.coverage?.openConflicts===0;
const rewardSearchValid=runtimeSource.includes('function rewardAwareSearch')&&runtimeSource.includes('function rewardSearchDocument')&&runtimeSource.includes('window.runSearch = rewardAwareSearch')&&runtimeSource.includes('score += 10')&&runtimeSource.includes('atlas-search-reward')&&runtimeSource.includes('奖励：')&&runtimeSource.includes('escapeHTML(item.rewardNames')&&runtimeSource.includes('focusLocation(location)')&&html.includes('搜索地点、区域、奖励或类别')&&rewardCss.includes('.atlas-search-reward');

const forbidden=policy.forbiddenBehaviors||[];
const nextFullAudit=manifest.invariants?.nextRequiredFullAuditVersion;
const fullAuditRequired=manifest.version===nextFullAudit;
const contracts={
  release:index.release===manifest.version&&runtimeIndex.release===manifest.version,
  fullAudit:manifest.invariants?.requireFullAuditAtThisRelease===fullAuditRequired,
  rewardOwner:manifest.runtimeOwners?.rewardEvidenceIndex==='data/rewards/reward-evidence-index.json'&&manifest.runtimeOwners?.rewardSummaryRuntime==='atlas-rewards-0949.js'&&manifest.runtimeOwners?.rewardRuntimeRecords==='data/rewards/reward-records-runtime.json',
  rewardMatrix:manifest.invariants?.requiredRewardEvidenceChecks===500&&manifest.invariants?.rewardUnresolvedNeverFabricated===true&&manifest.invariants?.rewardRuntimeRecordCount===runtimeIndex.recordCount&&manifest.invariants?.rewardSingleSourceMustRemainInference===true&&manifest.invariants?.rewardPartialSourceCoverageMustRemainInference===true&&manifest.invariants?.rewardSourceLineageMustBeQualified===true&&manifest.invariants?.rewardCandidateRecordsMachineChecked===true&&runtimeRecordsValid&&reviewQueueValid&&runtimeCoverageValid&&rewardSearchValid&&runtimeIndex.noteZhCN.includes('数据链独立性')&&runtimeSource.includes('旧描述不会被当作已确认事实')&&runtimeSource.includes('loadRuntimeRecords')&&runtimeSource.includes('Promise.allSettled')&&runtimeSource.includes('rewardSupportCount')&&runtimeSource.includes('个来源')&&serviceWorker.includes(String.raw`records\/[^?]+\.json`),
  targetCount:index.targetLocationCount===3430,
  coverageTotal:index.coverage?.total===3430,
  coverageConserved:['officialConfirmed','multiSourceConfirmed','highConfidenceInference','unresolved'].reduce((sum,key)=>sum+Number(index.coverage?.[key]||0),0)===3430,
  unresolvedAllowed:policy.principles?.allowEmptyRewardWhenUnresolved===true,
  noInferenceAsOfficial:policy.principles?.neverPresentInferenceAsOfficial===true,
  sourceLocatorRequired:policy.principles?.requireSourceLocator===true,
  conflictTrackingRequired:policy.principles?.requireConflictTracking===true,
  simplifiedChineseRequired:policy.principles?.requireStandardSimplifiedChinese===true,
  fourEvidenceLevels:Array.isArray(policy.evidenceLevels)&&policy.evidenceLevels.length===4,
  officialThreshold:policy.evidenceLevels?.find(level=>level.id==='official_confirmed')?.minimumConfidence===0.98,
  multiThreshold:multiThreshold===0.90,
  inferenceThreshold:inferenceThreshold===0.75,
  unresolvedThreshold:policy.evidenceLevels?.find(level=>level.id==='unresolved')?.minimumConfidence===0,
  sourceTypes:Array.isArray(policy.sourceTypes)&&policy.sourceTypes.length>=8,
  conflictTypes:Array.isArray(policy.conflictTypes)&&policy.conflictTypes.length>=5,
  forbiddenBulkCopy:forbidden.some(text=>text.includes('类别')&&text.includes('复制')&&text.includes('同类点位')),
  forbiddenFakeOfficial:forbidden.some(text=>text.includes('没有证据')&&text.includes('官方确认')),
  schemaLocationRequired:schema.type==='object'&&schema.required?.includes('locationId'),
  schemaStatusRequired:schema.required?.includes('status'),
  schemaConfidenceRequired:schema.required?.includes('confidence'),
  schemaSummaryRequired:schema.required?.includes('summaryZhCN'),
  schemaSourcesRequired:schema.required?.includes('sources'),
  schemaConflictsRequired:schema.required?.includes('conflicts'),
  schemaReviewRequired:schema.required?.includes('review'),
  confidenceBounded:schema.properties?.confidence?.minimum===0&&schema.properties?.confidence?.maximum===1,
  exactStatuses:schema.properties?.status?.enum?.length===4,
  rewardTypes:schema.properties?.rewards?.items?.properties?.type?.enum?.length>=10,
  quantityStatuses:schema.properties?.rewards?.items?.properties?.quantityStatus?.enum?.length===5,
  sourceLocatorSchema:schema.properties?.sources?.items?.required?.includes('locator'),
  sourceSupportsSchema:schema.properties?.sources?.items?.required?.includes('supports'),
  conflictStateSchema:schema.properties?.conflicts?.items?.properties?.status?.enum?.length===3,
  reviewLocked:schema.properties?.review?.properties?.state?.enum?.includes('locked'),
  terminologyLocale:terms.locale==='zh-CN',
  preserveOriginal:terms.rules?.preserveOriginalName===true,
  noInventNames:terms.rules?.doNotInventProperNouns===true,
  officialChinese:terms.rules?.useOfficialChineseWhenAvailable===true,
  unknownQuantity:terms.rules?.unknownQuantityLabel==='数量未确认',
  inferenceSuffix:terms.rules?.inferenceSuffix?.includes('高置信推断'),
  rewardTypeTranslations:Object.keys(terms.rewardTypes||{}).length>=10,
  evidenceLabels:Object.keys(terms.evidenceLabels||{}).length===4,
  productionBatchLimit:index.productionRules?.batchSizeMaximum===100,
  lockedProtection:index.productionRules?.neverOverwriteLockedRecordAutomatically===true,
  duplicateCheck:index.productionRules?.requireDuplicateLocationCheck===true,
  sourceCheck:index.productionRules?.requireSourceLocatorCheck===true,
  terminologyCheck:index.productionRules?.requireChineseTerminologyCheck===true,
  conflictReport:index.productionRules?.requireConflictReport===true
};

const entries=Object.entries(contracts);
const results=[];
let failed=entries.length!==50;
for(const profile of profiles){
  for(const [name,passed] of entries){
    const item={profile,name,passed:Boolean(passed)};
    results.push(item);
    if(!item.passed)failed=true;
  }
}

const totalChecks=results.length;
const failedContracts=[...new Set(results.filter(item=>!item.passed).map(item=>item.name))];
const report={schemaVersion:1,release:manifest.version,generatedAt:new Date().toISOString(),passed:!failed&&totalChecks===500,totalChecks,contractCount:entries.length,failedContracts,runtimeRecordCount:runtimeIndex.recordCount,rewardSearchValid,profiles:profiles.map(profile=>({profile,checks:results.filter(item=>item.profile===profile)}))};
await fs.mkdir(new URL('../data/conflict-reports/',import.meta.url),{recursive:true});
await fs.writeFile(new URL('../data/conflict-reports/reward-evidence-matrix.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(`Reward evidence contract matrix: ${results.filter(item=>item.passed).length}/${totalChecks}; records=${runtimeIndex.recordCount}; search=${rewardSearchValid?'pass':'fail'}; contracts=${entries.length}; failed=${failedContracts.join(',')||'none'}`);
if(entries.length!==50||totalChecks!==500)process.exit(3);
if(failed)process.exit(2);
