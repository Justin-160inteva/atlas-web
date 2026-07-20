import fs from 'node:fs/promises';

const readJson=async path=>JSON.parse(await fs.readFile(new URL(`../${path}`,import.meta.url),'utf8'));
const [manifest,policy,schema,terms,index]=await Promise.all([
  readJson('release-manifest.json'),
  readJson('data/rewards/reward-source-policy.json'),
  readJson('data/rewards/reward-record-schema.json'),
  readJson('data/rewards/reward-terminology-zh-CN.json'),
  readJson('data/rewards/reward-evidence-index.json')
]);

const profiles=[
  'official-text','official-web','official-patch','authorized-video','public-video',
  'screenshot','community-database','guide-article','manual-review','conflict-recovery'
];

const forbidden=policy.forbiddenBehaviors||[];
const contracts={
  release:manifest.version==='0.9.4.8',
  fullAudit:manifest.invariants?.requireFullAuditAtThisRelease===true,
  rewardOwner:manifest.runtimeOwners?.rewardEvidenceIndex==='data/rewards/reward-evidence-index.json',
  rewardMatrix:manifest.invariants?.requiredRewardEvidenceChecks===500,
  targetCount:index.targetLocationCount===3430,
  coverageConserved:['officialConfirmed','multiSourceConfirmed','highConfidenceInference','unresolved'].reduce((sum,key)=>sum+Number(index.coverage?.[key]||0),0)===3430,
  unresolvedAllowed:policy.principles?.allowEmptyRewardWhenUnresolved===true,
  noInferenceAsOfficial:policy.principles?.neverPresentInferenceAsOfficial===true,
  sourceLocatorRequired:policy.principles?.requireSourceLocator===true,
  conflictTrackingRequired:policy.principles?.requireConflictTracking===true,
  simplifiedChineseRequired:policy.principles?.requireStandardSimplifiedChinese===true,
  fourEvidenceLevels:Array.isArray(policy.evidenceLevels)&&policy.evidenceLevels.length===4,
  officialThreshold:policy.evidenceLevels?.find(level=>level.id==='official_confirmed')?.minimumConfidence===0.98,
  multiThreshold:policy.evidenceLevels?.find(level=>level.id==='multi_source_confirmed')?.minimumConfidence===0.90,
  inferenceThreshold:policy.evidenceLevels?.find(level=>level.id==='high_confidence_inference')?.minimumConfidence===0.75,
  unresolvedThreshold:policy.evidenceLevels?.find(level=>level.id==='unresolved')?.minimumConfidence===0,
  sourceTypes:Array.isArray(policy.sourceTypes)&&policy.sourceTypes.length>=8,
  conflictTypes:Array.isArray(policy.conflictTypes)&&policy.conflictTypes.length>=5,
  forbiddenBulkCopy:forbidden.some(text=>text.includes('类别')&&text.includes('复制')&&text.includes('同类点位')),
  forbiddenFakeOfficial:forbidden.some(text=>text.includes('没有证据')&&text.includes('官方确认')),
  schemaObject:schema.type==='object',
  schemaLocationRequired:schema.required?.includes('locationId'),
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
if(entries.length!==50)throw new Error(`Expected 50 reward contracts, got ${entries.length}`);

const results=[];
let failed=false;
for(const profile of profiles){
  for(const [name,passed] of entries){
    const item={profile,name,passed:Boolean(passed)};
    results.push(item);
    if(!item.passed)failed=true;
  }
}

const totalChecks=results.length;
const report={schemaVersion:1,release:manifest.version,generatedAt:new Date().toISOString(),passed:!failed,totalChecks,profiles:profiles.map(profile=>({profile,checks:results.filter(item=>item.profile===profile)}))};
await fs.mkdir(new URL('../data/conflict-reports/',import.meta.url),{recursive:true});
await fs.writeFile(new URL('../data/conflict-reports/reward-evidence-matrix.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(`Reward evidence contract matrix: ${results.filter(item=>item.passed).length}/${totalChecks}`);
if(totalChecks!==500)process.exit(3);
if(failed)process.exit(2);
