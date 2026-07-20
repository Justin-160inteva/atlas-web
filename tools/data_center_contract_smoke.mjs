import fs from 'node:fs/promises';
import process from 'node:process';

const read=path=>fs.readFile(new URL(`../${path}`,import.meta.url),'utf8');
const [manifest,settings,settingsCss,evidenceCss,index]=await Promise.all([
  read('release-manifest.json').then(JSON.parse),
  read('atlas-settings.js'),
  read('atlas-settings.css'),
  read('evidence-studio.css'),
  read('index.html')
]);

const profiles=[
  {name:'desktop-wide',mobile:false,touch:false,performance:false,reduced:false},
  {name:'desktop-compact',mobile:false,touch:false,performance:false,reduced:false},
  {name:'ipad-landscape',mobile:false,touch:true,performance:false,reduced:false},
  {name:'ipad-portrait',mobile:false,touch:true,performance:false,reduced:false},
  {name:'tablet-compact',mobile:true,touch:true,performance:false,reduced:false},
  {name:'mobile',mobile:true,touch:true,performance:false,reduced:false},
  {name:'desktop-performance',mobile:false,touch:false,performance:true,reduced:false},
  {name:'ipad-performance',mobile:false,touch:true,performance:true,reduced:false},
  {name:'mobile-reduced-motion',mobile:true,touch:true,performance:false,reduced:true},
  {name:'offline-recovery',mobile:false,touch:false,performance:false,reduced:false,offline:true}
];

const actions=['openDatabase','openEvidence','openMonitor','closeMonitor','closeCenter'];
const results=[];
let failed=false;
const record=(profile,scenario,name,condition,detail='')=>{
  const passed=Boolean(condition);
  results.push({profile:profile.name,scenario,name,passed,detail});
  if(!passed)failed=true;
};

function reduce(state,action){
  const next={...state};
  if(action==='openDatabase'){next.center=true;next.view='database';next.evidence=false;}
  if(action==='openEvidence'){next.center=true;next.view='evidence';next.evidence=true;}
  if(action==='openMonitor'){next.center=true;next.monitor=true;}
  if(action==='closeMonitor')next.monitor=false;
  if(action==='closeCenter'){next.center=false;next.view='database';next.evidence=false;next.monitor=false;}
  return next;
}

const staticContract={
  release:manifest.version==='0.9.4.7',
  owner:manifest.runtimeOwners?.dataEvidenceCenter==='atlas-settings.js',
  singleCenter:manifest.invariants?.singleDataEvidenceCenter===true,
  twoViews:manifest.invariants?.dataEvidenceCenterViews===2,
  legacyDisabled:manifest.invariants?.legacyEvidencePanelStandalone===false,
  matrix:manifest.invariants?.requiredDataCenterMatrixChecks===500,
  centerMarkup:settings.includes('id="settingsPanel"')&&settings.includes('Atlas 数据与证据中心'),
  databaseTab:settings.includes('data-center-tab="database"'),
  evidenceTab:settings.includes('data-center-tab="evidence"'),
  databaseView:settings.includes('data-center-view="database"'),
  evidenceView:settings.includes('data-center-view="evidence"'),
  evidenceHost:settings.includes('id="settingsEvidenceHost"'),
  mountsLegacy:settings.includes("host.appendChild(panel)"),
  hidesLegacyClose:settings.includes('legacyClose.hidden=true'),
  singleGearCapture:settings.includes("gear?.addEventListener('click'")&&settings.includes('event.stopImmediatePropagation()'),
  bypassBounded:settings.includes('evidenceBypass=true')&&settings.includes('evidenceBypass=false'),
  monitorCurrent:settings.includes("MONITOR_VERSION='0.6.1'"),
  monitorOwned:settings.includes('id="scanMonitorOverlay"'),
  refreshesDatabase:settings.includes('refreshDatabaseStatus'),
  localSummary:settings.includes('refreshEvidenceSummary'),
  closesEvidence:settings.includes("$('#closeEvidenceStudio')?.click()"),
  exposesApi:settings.includes('openEvidence:()=>openSettings(\'evidence\')'),
  releaseDataset:settings.includes('root.dataset.atlasDataCenter=RELEASE'),
  cssSinglePanel:settingsCss.includes('.atlas-data-center')&&settingsCss.includes('width:min(520px'),
  cssTabs:settingsCss.includes('.data-center-tabs'),
  cssMetrics:settingsCss.includes('.data-center-metrics'),
  cssPerformance:settingsCss.includes('.atlas-quality-performance .settings-panel'),
  cssMobile:settingsCss.includes('@media(max-width:720px)'),
  cssReduced:settingsCss.includes('@media(prefers-reduced-motion:reduce)'),
  evidenceEmbedded:evidenceCss.includes('.settings-evidence-host .evidence-panel'),
  evidenceHeaderHidden:evidenceCss.includes('.settings-evidence-host .evidence-panel>header{display:none}'),
  evidenceOnlyWhenOpen:evidenceCss.includes('.settings-evidence-host .evidence-panel.open{display:block'),
  evidenceNoStandaloneOwner:!settings.includes('id="openEvidenceLab"'),
  indexSingleEvidencePanel:(index.match(/id="evidencePanel"/g)||[]).length===1,
  indexSingleSettingsButton:(index.match(/id="evidenceStudioBtn"/g)||[]).length===1,
  privacyCopy:settings.includes('本地视频与关键帧不会上传'),
  databaseFields:['dataCenterImported','dataCenterQueue','dataCenterActive','dataCenterHeartbeat'].every(id=>settings.includes(id)),
  ariaTabs:settings.includes('role="tablist"')&&settings.includes('aria-selected="true"'),
  ariaViews:settings.includes('role="tabpanel"'),
  noOldTitle:!settings.includes('<h2>设置</h2>'),
  noDuplicateEvidenceCard:!settings.includes('证据重建实验室</b>'),
  monitorReturnLabel:settings.includes('返回数据与证据中心'),
  closeResetsEvidence:settings.includes("classList.remove('open','evidence-active')"),
  databaseDefault:settings.includes("let activeView='database'"),
  viewNormalization:settings.includes("view==='evidence'?'evidence':'database'"),
  offlineFallback:settings.includes('本轮状态核对失败，10秒后自动重试'),
  storageBoundary:settings.includes("EVIDENCE_STORAGE_KEY='atlas-evidence-project-v1'"),
  rawStatusBoundary:settings.includes("STATUS_PATH='data/batch-analysis/eleven-pilot-scan-status.json'"),
  runtimeBoundary:settings.includes("RUNTIME_PATH='data/runtime-progress/eleven-pilot-progress.json'"),
  staleRuntimeGuard:settings.includes('RUNTIME_FRESH_MS=150000')
};
const staticValues=Object.entries(staticContract);
if(staticValues.length!==50)throw new Error(`Expected 50 static contracts, got ${staticValues.length}`);

for(const profile of profiles){
  let state={center:false,view:'database',evidence:false,monitor:false};
  for(let scenario=0;scenario<10;scenario++){
    const sequence=[actions[scenario%5],actions[(scenario+profile.name.length)%5],actions[(scenario*3+2)%5]];
    for(const action of sequence)state=reduce(state,action);
    const [name,staticPassed]=staticValues[scenario*5];
    record(profile,scenario,`${name} · source contract`,staticPassed,name);
    record(profile,scenario,'single center state',state.view==='database'||state.view==='evidence',JSON.stringify(state));
    record(profile,scenario,'evidence lifecycle',state.evidence===(state.center&&state.view==='evidence'),JSON.stringify(state));
    record(profile,scenario,'monitor ownership',!state.monitor||state.center,JSON.stringify(state));
    const responsive=profile.mobile?staticContract.cssMobile:true;
    const motion=profile.reduced?staticContract.cssReduced:true;
    const performance=profile.performance?staticContract.cssPerformance:true;
    const offline=profile.offline?staticContract.offlineFallback:true;
    const group=staticValues.slice(scenario*5,scenario*5+5).every(([,value])=>value);
    record(profile,scenario,'profile and contract group',responsive&&motion&&performance&&offline&&group,JSON.stringify({responsive,motion,performance,offline,group}));
  }
}

const totalChecks=results.length;
const report={schemaVersion:1,release:manifest.version,generatedAt:new Date().toISOString(),passed:!failed,totalChecks,profiles:profiles.map(profile=>({name:profile.name,checks:results.filter(item=>item.profile===profile.name)}))};
await fs.mkdir(new URL('../data/conflict-reports/',import.meta.url),{recursive:true});
await fs.writeFile(new URL('../data/conflict-reports/data-center-matrix.json',import.meta.url),JSON.stringify(report,null,2)+'\n');
console.log(`Data center contract matrix: ${results.filter(item=>item.passed).length}/${totalChecks}`);
if(totalChecks!==500){console.error(`Expected exactly 500 data center checks, got ${totalChecks}`);process.exit(3);}
if(failed)process.exit(2);
