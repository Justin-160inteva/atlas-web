import fs from 'node:fs/promises';

const read = path => fs.readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [html, css, controller, marker, legacyMarker, manifestText, worker] = await Promise.all([
  read('index.html'),
  read('atlas-navigation-09411a.css'),
  read('atlas-navigation-09411b.js'),
  read('marker-state.js'),
  read('atlas-ui-fix-0931.js'),
  read('release-manifest.json'),
  read('sw.js')
]);
const manifest = JSON.parse(manifestText);
const checks = [];
const check = (name, condition, detail = '') => checks.push({ name, passed: Boolean(condition), detail });

check('new controller loaded once', (html.match(/atlas-navigation-09411b\.js/g) || []).length === 1);
check('old observer controller not loaded', !/atlas-navigation-09411a\.js/.test(html));
check('new controller is a release asset', manifest.releaseAssets.includes('atlas-navigation-09411b.js'));
check('old controller removed from release assets', !manifest.releaseAssets.includes('atlas-navigation-09411a.js'));
check('interaction owner is 09411b', manifest.runtimeOwners.navigationInteractionGuard === 'atlas-navigation-09411b.js');
check('recovery owner is 09411b', manifest.runtimeOwners.quickRailMediumRecovery === 'atlas-navigation-09411b.js');
check('single recovery contract enabled', manifest.invariants.singleNavigationRecoveryController === true);
check('idempotent observer contract enabled', manifest.invariants.navigationObserverWritesIdempotent === true);
check('frame coalescing contract enabled', manifest.invariants.navigationRecoveryFrameCoalesced === true);
check('controller version contract', manifest.invariants.navigationRecoveryVersion === '0.9.4.11b');

check('idempotent attribute helper exists', /function setAttributeIfChanged\(/.test(controller));
check('idempotent inert helper exists', /function addAttributeIfMissing\(/.test(controller));
check('repair is frame coalesced', /if \(repairFrame\) return;\s*repairFrame = requestAnimationFrame\(runRepair\)/s.test(controller));
check('panel observer only watches class', /attributeFilter: \['class'\]/.test(controller) && !/attributeFilter: \['class', 'aria-hidden'\]/.test(controller));
check('settings observer only watches children', /observe\(settings, \{ childList: true \}\)/.test(controller));
check('settings observer does not watch design attribute', !/attributeFilter: \['data-icon-design'\]/.test(controller));
check('rail observer repairs only invalid state', /if \(railNeedsRepair\(\)\) scheduleRepair\(\)/.test(controller));
check('runtime audit is exposed', /window\.AtlasNavigationRecovery = Object\.freeze/.test(controller));
check('runtime audit includes rail interaction', /railInteractive: !railNeedsRepair\(\)/.test(controller));
check('runtime audit includes closed panel safety', /closedPanelsSafe/.test(controller));

const svgBlock = controller.match(/const settingsIcon = `([\s\S]*?)`;/)?.[1] || '';
check('settings glyph has one circle', (svgBlock.match(/<circle\b/g) || []).length === 1);
check('settings glyph has one path', (svgBlock.match(/<path\b/g) || []).length === 1);
check('settings glyph has no nested visual duplicate', !/opacity="\.34"/.test(svgBlock));

check('left rail has direct safe visible inset', /html body \.quick-rail\{[\s\S]*left:max\(12px,env\(safe-area-inset-left,0px\)\)!important/.test(css));
check('mobile left rail minimum is eight', /html body \.quick-rail\{left:max\(8px,env\(safe-area-inset-left,0px\)\)!important/.test(css));
check('bottom uses physical viewport edges', /html body \.bottom-nav\{[\s\S]*left:0!important;[\s\S]*right:0!important/.test(css));
check('bottom uses native auto margins', /margin-left:auto!important;[\s\S]*margin-right:auto!important/.test(css));
check('bottom width remains compact', /width:min\(430px,/.test(css));
check('bottom transform matrix is neutral', /transform:none!important/.test(css));
check('individual translate is disabled', /translate:none!important/.test(css));
check('double negative centering is absent', !/translate:-50%/.test(css) && !/translate3d\(-50%/.test(css));
check('desktop bottom minimum is eight', /bottom:max\(8px,env\(safe-area-inset-bottom,0px\)\)!important/.test(css));
check('symmetric safe inline variable exists', /--atlas-nav-safe-inline:max\(12px,env\(safe-area-inset-left,0px\),env\(safe-area-inset-right,0px\)\)/.test(css));
check('closed layers cannot intercept input', /\.panel:not\(\.open\)[\s\S]*pointer-events:none!important/.test(css));

check('glass authority version is 09412d-1', /Atlas Alpha 0\.9\.4\.12d-1/.test(css));
check('single glass surface token exists', /--atlas-glass-surface:linear-gradient/.test(css));
check('premium light red token exists', /--atlas-red-light:#ee7b86/.test(css));
check('premium deep red token exists', /--atlas-red-deep:#64131e/.test(css));
check('primary red uses multi-stop gradient', /linear-gradient\(150deg,var\(--atlas-red-light\),var\(--atlas-red-mid\) 42%,var\(--atlas-red-deep\) 78%,var\(--atlas-red-deeper\)\)/.test(css));
check('all primary surfaces share authority selector', /:where\(\.glass,\.top-bar,\.map-controls,\.status-pill,\.panel,\.settings-panel,\.search-modal,\.evidence-panel,\.sheet,\.route-badge,\.monitor-toolbar\)/.test(css));
const nestedCardRule = css.match(/html body :where\(\.filter-summary,[\s\S]*?\n\}/)?.[0] || '';
check('nested cards disable backdrop filter', /-webkit-backdrop-filter:none!important/.test(nestedCardRule) && /backdrop-filter:none!important/.test(nestedCardRule));
check('desktop blur is limited to sixteen', /--atlas-glass-blur:16px/.test(css));
check('ipad blur is limited to fourteen', /html\.atlas-ipad[\s\S]*--atlas-glass-blur:14px/.test(css));
check('mobile blur is limited to twelve', /@media\(max-width:720px\)[\s\S]*--atlas-glass-blur:12px/.test(css));
check('reduced transparency fallback exists', /@media\(prefers-reduced-transparency:reduce\)/.test(css));
check('reduced motion fallback exists', /@media\(prefers-reduced-motion:reduce\)/.test(css));
check('no infinite animation added', !/animation[^;]*infinite/.test(css));
check('no filter blur added', !/[^-]filter:\s*blur\(/.test(css));

check('bottom nav uses five isolated grid cells', /grid-template-columns:repeat\(5,minmax\(0,1fr\)\)!important/.test(css) && /html body \.bottom-nav[\s\S]*gap:6px!important/.test(css));
check('quick rail uses five isolated grid cells', /grid-template-rows:repeat\(5,minmax\(0,1fr\)\)!important/.test(css));
check('navigation cells clip cross-cell paint', /\.quick-rail \.rail-button,\.bottom-nav \.nav-item\{[\s\S]*overflow:hidden!important;[\s\S]*contain:layout paint style!important/.test(css));
check('selected navigation does not enlarge', /Final selected-state authority: no enlargement[\s\S]*transform:none!important/.test(css) && !/Final selected-state authority[\s\S]*scale\(1\.035\)/.test(css));

check('marker authority is marker-state', manifest.runtimeOwners.markerGeometry === 'marker-state.js' && manifest.runtimeOwners.markerSelectionMotion === 'marker-state.js');
check('marker audit owner is marker-state', manifest.runtimeOwners.markerDesignAudit === 'marker-state.js');
check('marker-state is a release asset', manifest.releaseAssets.includes('marker-state.js'));
check('marker version contract', manifest.invariants.markerDesignVersion === '0.9.4.12b-1');
check('marker shape contract', manifest.invariants.markerShape === 'anchored-long-tail-droplet');
check('marker scale-only contract', manifest.invariants.markerSelectionUsesScaleOnly === true && manifest.invariants.markerSelectionDecorationLayers === 0);
check('marker selected scale contract', manifest.invariants.markerSelectedScale === 1.28);
check('marker duration contract', manifest.invariants.markerSelectionDurationMs === 190);
check('marker tip anchor contract', manifest.invariants.markerTipAnchorStable === true);
check('marker runtime version exists', /ATLAS_MARKER_DESIGN_VERSION='0\.9\.4\.12b-1'/.test(marker));
check('marker uses long-tail bezier path', (marker.match(/ctx\.bezierCurveTo\(/g) || []).length >= 5 && /ctx\.moveTo\(0,0\)/.test(marker));
check('marker selected feedback is scale only', /selectionFeedback:'scale-only'/.test(marker) && /selectionRing:false/.test(marker) && /selectionBorder:false/.test(marker));
check('legacy selected ring is absent', !/if\(selected\)\{ctx\.beginPath\(\);ctx\.arc/.test(marker));
check('legacy selected shadow branch is absent', !/shadowColor=selected\?/.test(marker));
check('marker animation is frame coalesced by scheduleDraw', /if\(t>=1\)atlasMarkerAnimations\.delete\(id\);else scheduleDraw\(\)/.test(marker));
check('marker runtime audit is exposed', /window\.AtlasMarkerDesign=Object\.freeze/.test(marker));
const markerHandoffIndex = legacyMarker.indexOf("if(window.AtlasMarkerDesign?.version==='0.9.4.12b-1')");
const legacyOverrideIndex = legacyMarker.indexOf('drawMarker=function');
check('legacy marker controller hands off to marker-state', /if\(window\.AtlasMarkerDesign\?\.version==='0\.9\.4\.12b-1'\)[\s\S]*root\.dataset\.atlasMarkerOwner='marker-state\.js';[\s\S]*return;/.test(legacyMarker));
check('marker handoff precedes legacy draw override', markerHandoffIndex >= 0 && legacyOverrideIndex >= 0 && markerHandoffIndex < legacyOverrideIndex);

check('service worker caches new controller', worker.includes("'./atlas-navigation-09411b.js'"));
check('service worker excludes old observer controller', !worker.includes("'./atlas-navigation-09411a.js'"));
check('service worker refreshes marker-state', /page-zoom-guard\|marker-state\|scan-monitor/.test(worker));
check('service worker cache namespace matches manifest', worker.includes(`const CACHE='${manifest.cacheNamespace}'`));

const failed = checks.filter(item => !item.passed);
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.12d-1', passed: failed.length === 0, totalChecks: checks.length, checks }, null, 2));
if (failed.length) process.exit(1);
