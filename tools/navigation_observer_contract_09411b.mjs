import fs from 'node:fs/promises';

const read = path => fs.readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const [html, css, controller, manifestText, worker] = await Promise.all([
  read('index.html'),
  read('atlas-navigation-09411a.css'),
  read('atlas-navigation-09411b.js'),
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

check('service worker caches new controller', worker.includes("'./atlas-navigation-09411b.js'"));
check('service worker excludes old observer controller', !worker.includes("'./atlas-navigation-09411a.js'"));
check('service worker cache namespace matches manifest', worker.includes(`const CACHE='${manifest.cacheNamespace}'`));

const failed = checks.filter(item => !item.passed);
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.11c', passed: failed.length === 0, totalChecks: checks.length, checks }, null, 2));
if (failed.length) process.exit(1);
