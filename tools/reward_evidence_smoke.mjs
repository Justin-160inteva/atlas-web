import fs from 'node:fs/promises';

const read=path=>fs.readFile(new URL(`../${path}`,import.meta.url),'utf8');
const [manifest,indexData,locations,runtime,css,html,worker]=await Promise.all([
  read('release-manifest.json').then(JSON.parse),
  read('data/reward-evidence-index.json').then(JSON.parse),
  read('data/locations.json').then(JSON.parse),
  read('atlas-reward-evidence.js'),
  read('atlas-reward-evidence.css'),
  read('index.html'),
  read('sw.js')
]);

const profiles=[
  {name:'desktop-wide',mobile:false,touch:false,performance:false,reduced:false,offline:false},
  {name:'desktop-compact',mobile:false,touch:false,performance:false,reduced:false,offline:false},
  {name:'ipad-landscape',mobile:false,touch:true,performance:false,reduced:false,offline:false},
  {name:'ipad-portrait',mobile:false,touch:true,performance:false,reduced:false,offline:false},
  {name:'tablet-compact',mobile:true,touch:true,performance:false,reduced:false,offline:false},
  {name:'mobile',mobile:true,touch:true,performance:false,reduced:false,offline:false},
  {name:'desktop-performance',mobile:false,touch:false,performance:true,reduced:false,offline:false},
  {name:'ipad-performance',mobile:false,touch:true,performance:true,reduced:false,offline:false},
  {name:'mobile-reduced-motion',mobile:true,touch:true,performance:false,reduced:true,offline:false},
  {name:'offline-fallback',mobile:false,touch:false,performance:false,reduced:false,offline:true}
];

const records=indexData.records||[];
const recordIds=records.map(record=>record.locationId);
const locationById=new Map(locations.map(location=>[location.id,location]));
const allowedStatus=new Set(['official_confirmed','multi_source_confirmed','high_confidence_inference','unresolved']);
const rewardItems=records.flatMap(record=>record.rewards||[]);
const evidenceItems=records.flatMap(record=>record.evidence||[]);
const sourceIds=new Set(Object.keys(indexData.sources||{}));
const chinese=/[\u3400-\u9fff]/;
const countStatus=status=>records.filter(record=>record.evidenceStatus===status).length;
const countRewardStatus=status=>rewardItems.filter(reward=>reward.evidenceStatus===status).length;
const scriptCount=(html.match(/atlas-reward-evidence\.js\?v=/g)||[]).length;
const styleCount=(html.match(/atlas-reward-evidence\.css\?v=/g)||[]).length;

const contracts=[
  ['release is 0.9.4.8',()=>manifest.version==='0.9.4.8'],
  ['reward owner declared',()=>manifest.runtimeOwners?.rewardEvidence==='atlas-reward-evidence.js'],
  ['target invariant is 3430',()=>manifest.invariants?.rewardEvidenceTargetLocationCount===3430],
  ['seed invariant is eight',()=>manifest.invariants?.rewardEvidenceSeedRecords===8],
  ['matrix invariant is 500',()=>manifest.invariants?.requiredRewardEvidenceMatrixChecks===500],
  ['sidecar schema one',()=>indexData.schemaVersion===1],
  ['sidecar release matches',()=>indexData.release===manifest.version],
  ['locale is zh-Hans',()=>indexData.locale==='zh-Hans'],
  ['locations total is 3430',()=>locations.length===3430],
  ['sidecar target is 3430',()=>indexData.targetLocationCount===3430],
  ['seed records count eight',()=>records.length===8],
  ['coverage record count matches',()=>indexData.coverage?.records===records.length],
  ['coverage totals to target',()=>['officialConfirmed','multiSourceConfirmed','highConfidenceInference','unresolved'].reduce((sum,key)=>sum+Number(indexData.coverage?.[key]||0),0)===3430],
  ['official seed count remains zero',()=>indexData.coverage?.officialConfirmed===0&&countStatus('official_confirmed')===0],
  ['multi-source seed count eight',()=>indexData.coverage?.multiSourceConfirmed===8&&countStatus('multi_source_confirmed')===8],
  ['record ids are unique',()=>new Set(recordIds).size===records.length],
  ['all records map to locations',()=>records.every(record=>locationById.has(record.locationId))],
  ['record titles match locations',()=>records.every(record=>locationById.get(record.locationId)?.title===record.title)],
  ['record statuses allowed',()=>records.every(record=>allowedStatus.has(record.evidenceStatus))],
  ['record confidence bounded',()=>records.every(record=>Number.isFinite(record.confidence)&&record.confidence>=0&&record.confidence<=1)],
  ['all records have rewards',()=>records.every(record=>Array.isArray(record.rewards)&&record.rewards.length>0)],
  ['all records have evidence',()=>records.every(record=>Array.isArray(record.evidence)&&record.evidence.length>=2)],
  ['all summaries are Chinese',()=>records.every(record=>chinese.test(record.summaryZhHans||''))],
  ['translations are project standardized',()=>records.every(record=>record.translation?.status==='project_standardized')],
  ['no translation impersonates official',()=>records.every(record=>record.translation?.official===false)],
  ['all gear keeps original name',()=>rewardItems.filter(item=>item.kind==='gear'||item.kind==='engraving').every(item=>Boolean(item.originalName))],
  ['all rewards have Chinese names',()=>rewardItems.every(item=>chinese.test(item.nameZhHans||''))],
  ['reward statuses allowed',()=>rewardItems.every(item=>allowedStatus.has(item.evidenceStatus))],
  ['reward confidence bounded',()=>rewardItems.every(item=>Number.isFinite(item.confidence)&&item.confidence>=0&&item.confidence<=1)],
  ['unresolved subclaims remain visible',()=>countRewardStatus('unresolved')>0],
  ['confirmed gear batch covers eight',()=>rewardItems.filter(item=>item.kind==='gear'&&item.evidenceStatus==='multi_source_confirmed').length===8],
  ['source registry contains Game8',()=>sourceIds.has('game8-all-castles')],
  ['source registry contains Mibuno video',()=>sourceIds.has('youtube-bing-mibuno')],
  ['source registry contains Osaka video',()=>sourceIds.has('youtube-bing-osaka')],
  ['registered URLs use HTTPS',()=>Object.values(indexData.sources||{}).every(source=>String(source.url||'').startsWith('https://'))],
  ['evidence references resolve',()=>evidenceItems.every(item=>item.source==='mapgenie_location_snapshot'||sourceIds.has(item.source))],
  ['evidence locators are present',()=>evidenceItems.every(item=>Boolean(item.locator))],
  ['Mibuno timestamp retained',()=>indexData.sources?.['youtube-bing-mibuno']?.locator==='06:10'],
  ['Osaka timestamp retained',()=>indexData.sources?.['youtube-bing-osaka']?.locator==='07:13'],
  ['runtime validates target',()=>runtime.includes("payload.targetLocationCount!==3430")],
  ['runtime validates duplicate ids',()=>runtime.includes("duplicate reward evidence location")],
  ['runtime uses safe DOM construction',()=>runtime.includes("document.createElement")&&!runtime.includes('innerHTML=')],
  ['runtime has unresolved fallback',()=>runtime.includes('该点位尚未进入奖励证据批次')&&runtime.includes('不会把它显示为官方事实')],
  ['runtime preserves original names',()=>runtime.includes('reward.originalName')],
  ['runtime uses noopener links',()=>runtime.includes("noopener noreferrer")],
  ['runtime loads only once',()=>runtime.includes('if(loadPromise)return loadPromise')],
  ['style defines all four statuses',()=>['official_confirmed','multi_source_confirmed','high_confidence_inference','unresolved'].every(status=>css.includes(`[data-status="${status}"]`))],
  ['style includes mobile and performance paths',()=>css.includes('@media(max-width:720px)')&&css.includes('.atlas-quality-performance .atlas-reward-evidence')],
  ['entry includes one style and one script',()=>styleCount===1&&scriptCount===1],
  ['service worker caches reward assets',()=>worker.includes("./atlas-reward-evidence.css")&&worker.includes("./atlas-reward-evidence.js")&&worker.includes("./data/reward-evidence-index.json")]
];

if(contracts.length!==50)throw new Error(`Expected 50 reward evidence contracts, got ${contracts.length}`);

const results=[];
let failed=false;
for(const profile of profiles){
  for(const [index,[name,test]] of contracts.entries()){
    let passed=false;
    let detail='';
    try{
      passed=Boolean(test(profile));
      const responsive=!profile.mobile||css.includes('@media(max-width:720px)');
      const performance=!profile.performance||css.includes('.atlas-quality-performance .atlas-reward-evidence');
      const reduced=!profile.reduced||css.includes('@media(prefers-reduced-motion:reduce)');
      const offline=!profile.offline||runtime.includes("dataset.atlasRewardEvidence='unavailable'");
      passed=passed&&responsive&&performance&&reduced&&offline;
      detail=JSON.stringify({contract:index+1,responsive,performance,reduced,offline});
    }catch(error){detail=String(error?.message||error);}
    results.push({profile:profile.name,name,passed,detail});
    if(!passed)failed=true;
  }
}

const totalChecks=results.length;
const report={
  schemaVersion:1,
  release:manifest.version,
  generatedAt:new Date().toISOString(),
  passed:!failed,
  totalChecks,
  targetLocationCount:indexData.targetLocationCount,
  seedRecords:records.length,
  profiles:profiles.map(profile=>({name:profile.name,checks:results.filter(item=>item.profile===profile.name)}))
};
await fs.mkdir(new URL('../data/conflict-reports/',import.meta.url),{recursive:true});
await fs.writeFile(new URL('../data/conflict-reports/reward-evidence-matrix.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(`Reward evidence matrix: ${results.filter(item=>item.passed).length}/${totalChecks}`);
if(totalChecks!==500){console.error(`Expected exactly 500 reward evidence checks, got ${totalChecks}`);process.exit(3);}
if(failed)process.exit(2);
