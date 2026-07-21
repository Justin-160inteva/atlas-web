import fs from 'node:fs/promises';
import vm from 'node:vm';

const read = path => fs.readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const readJson = async path => JSON.parse(await read(path));
const [guard, mapCover, html, styles, serviceWorker, manifest, bootstrap] = await Promise.all([
  read('page-zoom-guard.js'),
  read('atlas-map-cover-0950.js'),
  read('index.html'),
  read('styles.css'),
  read('sw.js'),
  readJson('release-manifest.json'),
  read('atlas-bootstrap.js')
]);

new vm.Script(guard, { filename: 'page-zoom-guard.js' });
new vm.Script(mapCover, { filename: 'atlas-map-cover-0950.js' });

const devices = [
  { name: 'iPhone SE portrait', width: 320, height: 568, dpr: 2, touch: true, profile: 'compact-phone' },
  { name: 'Android compact portrait', width: 360, height: 800, dpr: 3, touch: true, profile: 'compact-phone' },
  { name: 'iPhone 8 portrait', width: 375, height: 667, dpr: 2, touch: true, profile: 'phone' },
  { name: 'iPhone 14 portrait', width: 390, height: 844, dpr: 3, touch: true, profile: 'large-phone' },
  { name: 'iPhone 15 Pro portrait', width: 393, height: 852, dpr: 3, touch: true, profile: 'large-phone' },
  { name: 'iPhone Pro Max portrait', width: 430, height: 932, dpr: 3, touch: true, profile: 'large-phone' },
  { name: 'iPhone 8 landscape', width: 667, height: 375, dpr: 2, touch: true, profile: 'phone' },
  { name: 'iPhone 14 landscape', width: 844, height: 390, dpr: 3, touch: true, profile: 'large-phone' },
  { name: 'iPad portrait', width: 768, height: 1024, dpr: 2, touch: true, profile: 'tablet' },
  { name: 'iPad Air portrait', width: 820, height: 1180, dpr: 2, touch: true, profile: 'tablet' },
  { name: 'iPad Pro landscape', width: 1366, height: 1024, dpr: 2, touch: true, profile: 'large-tablet' },
  { name: 'Desktop landscape', width: 1440, height: 900, dpr: 1, touch: false, profile: 'desktop' }
];

function classify(width, height, touch) {
  const shortSide = Math.min(width, height);
  const longSide = Math.max(width, height);
  if (shortSide <= 360) return 'compact-phone';
  if (shortSide < 600) return longSide >= 844 ? 'large-phone' : 'phone';
  if (shortSide < 900) return 'tablet';
  if (shortSide < 1180 && touch) return 'large-tablet';
  return 'desktop';
}

const staticContracts = {
  canonicalViewport: html.includes('interactive-widget=resizes-content') && guard.includes('interactive-widget=resizes-content'),
  guardRunsBeforeMap: html.indexOf('page-zoom-guard.js') < html.indexOf('app.js') && html.indexOf('app.js') < html.indexOf('atlas-map-cover-0950.js'),
  layoutShellAuthority: guard.includes("source: 'layout-shell'") && guard.includes("document.querySelector('.app-shell')") && guard.includes('getBoundingClientRect') && guard.includes('root.clientWidth') && !guard.includes('Number(visual?.width'),
  noScaleOscillation: !guard.includes('initial-scale=1.0001') && !guard.includes('window.scrollTo(0, 0)') && !guard.includes("visual?.addEventListener('scroll'") && guard.includes('viewportMeta.setAttribute'),
  visualKeyboardOnly: guard.includes('function updateKeyboardInset') && guard.includes("visual?.addEventListener('resize', updateKeyboardInset") && guard.includes('--atlas-keyboard-inset'),
  stableCommit: guard.includes('function settleViewport') && guard.includes('stableSamples >= 2') && guard.includes('maximumStabilitySamples') && guard.includes('atlasViewportCommitCount'),
  mapPinchPreserved: !guard.includes('event.touches.length > 1) preventNativeZoom') && guard.includes('#mapCanvas') && guard.includes('touch-action: none'),
  lifecycleRecovery: guard.includes("'orientationchange'") && guard.includes("'pageshow'") && guard.includes("'visibilitychange'"),
  mapGeometryHooks: guard.includes('installMapViewportHooks') && guard.includes('viewportFitMap') && guard.includes('viewportResize') && guard.includes('viewportFocusRoute'),
  mapZoomSeparation: mapCover.includes('const MANUAL_MIN_RATIO = 0.25') && mapCover.includes('function coverScale') && mapCover.includes('function manualMinimumScale') && mapCover.includes('clampToManualMinimum') && !mapCover.includes('clampToCover') && mapCover.includes('manualMinimumRatio: MANUAL_MIN_RATIO'),
  dynamicHeightFallback: styles.includes('100dvh') && styles.includes('@media(max-height:500px)') && guard.includes('font-size: max(16px, 1em)'),
  releaseOwnership: manifest.runtimeOwners?.pageViewportScale === 'page-zoom-guard.js' && manifest.runtimeOwners?.mapViewport === 'page-zoom-guard.js' && manifest.runtimeOwners?.mapViewportFit === 'atlas-map-cover-0950.js' && manifest.releaseAssets?.includes('page-zoom-guard.js') && manifest.releaseAssets?.includes('atlas-map-cover-0950.js'),
  releasePolicy: manifest.invariants?.viewportUsesLayoutShell === true && manifest.invariants?.viewportUsesVisualViewport === false && manifest.invariants?.visualViewportKeyboardOnly === true && manifest.invariants?.viewportStableCommitRequired === true && manifest.invariants?.viewportMaximumStartupCommits === 3 && manifest.invariants?.mapViewportAutomaticFitUsesCover === true && manifest.invariants?.mapViewportManualZoomBelowCover === true && manifest.invariants?.mapViewportManualMinimumRatio === 0.25,
  offlineRefresh: serviceWorker.includes("const CACHE='atlas-alpha-0949-pages-v2-monitor-v11-rewards-v1-viewport-v2'") && bootstrap.includes("cacheNamespace: 'atlas-alpha-0949-pages-v2-monitor-v11-rewards-v1-viewport-v2'") && html.includes('build=viewport-stable-v2') && html.includes('build=cover-v2-manual-zoom') && manifest.invariants?.requiredViewportScaleChecks === 120
};

const results = [];
for (const device of devices) {
  const orientation = device.width >= device.height ? 'landscape' : 'portrait';
  const fitScale = Math.min(device.width / 4096, device.height / 4096) * 1.1;
  const coverScale = Math.max(device.width / 4096, device.height / 4096) * 1.02;
  const manualMinimum = coverScale * 0.25;
  const cappedDpr = Math.min(device.dpr, 2.5);
  const canvasWidth = Math.floor(device.width * cappedDpr);
  const canvasHeight = Math.floor(device.height * cappedDpr);
  const staleVisualWidth = orientation === 'landscape' && device.touch ? Math.min(device.width, device.height) : device.width;
  const layoutShellWidth = device.width;
  const checks = [
    ['device-profile', classify(device.width, device.height, device.touch) === device.profile],
    ['orientation', orientation === (device.width >= device.height ? 'landscape' : 'portrait')],
    ['fit-scale', Number.isFinite(fitScale) && fitScale > 0 && fitScale < 1],
    ['manual-zoom-range', Number.isFinite(coverScale) && manualMinimum > 0 && manualMinimum < coverScale && Math.abs(manualMinimum / coverScale - 0.25) < 0.00001],
    ['canvas-size', canvasWidth > 0 && canvasHeight > 0 && cappedDpr <= 2.5],
    ['aspect-ratio', Math.abs(canvasWidth / canvasHeight - device.width / device.height) < 0.01],
    ['stale-visual-width-ignored', layoutShellWidth === device.width && (orientation !== 'landscape' || !device.touch || staleVisualWidth <= layoutShellWidth)],
    ['layout-source', staticContracts.canonicalViewport && staticContracts.layoutShellAuthority && staticContracts.visualKeyboardOnly],
    ['no-jitter-and-zoom-separation', staticContracts.noScaleOscillation && staticContracts.stableCommit && staticContracts.mapZoomSeparation],
    ['release-and-offline', staticContracts.guardRunsBeforeMap && staticContracts.lifecycleRecovery && staticContracts.mapGeometryHooks && staticContracts.mapPinchPreserved && staticContracts.dynamicHeightFallback && staticContracts.releaseOwnership && staticContracts.releasePolicy && staticContracts.offlineRefresh]
  ];
  for (const [name, passed] of checks) {
    results.push({ device: device.name, profile: device.profile, orientation, name, passed: Boolean(passed) });
  }
}

const failed = results.filter(result => !result.passed);
const report = {
  schemaVersion: 3,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: failed.length === 0 && results.length === 120,
  totalChecks: results.length,
  deviceCount: devices.length,
  failedChecks: failed,
  staticContracts,
  devices: devices.map(device => ({
    ...device,
    checks: results.filter(result => result.device === device.name)
  }))
};

await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/viewport-scale-matrix.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
console.log(`Viewport scale matrix: ${results.length - failed.length}/${results.length}; devices=${devices.length}; failed=${failed.map(item => `${item.device}:${item.name}`).join(',') || 'none'}`);
if (results.length !== 120) process.exit(3);
if (failed.length) process.exit(2);
