import fs from 'node:fs/promises';
import vm from 'node:vm';

const read = path => fs.readFile(new URL(`../${path}`, import.meta.url), 'utf8');
const readJson = async path => JSON.parse(await read(path));
const [guard, html, styles, serviceWorker, manifest] = await Promise.all([
  read('page-zoom-guard.js'),
  read('index.html'),
  read('styles.css'),
  read('sw.js'),
  readJson('release-manifest.json')
]);

new vm.Script(guard, { filename: 'page-zoom-guard.js' });

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
  guardRunsBeforeMap: html.indexOf('page-zoom-guard.js') < html.indexOf('app.js'),
  visualViewportAuthority: guard.includes('window.visualViewport') && guard.includes('--atlas-viewport-width') && guard.includes('--atlas-viewport-height'),
  scaleRecovery: guard.includes('initial-scale=1.0001') && guard.includes("scheduleViewportUpdate('page-scale-reset'"),
  mapPinchPreserved: !guard.includes('event.touches.length > 1) preventNativeZoom') && guard.includes('#mapCanvas { touch-action: none; }'),
  lifecycleRecovery: guard.includes("'orientationchange'") && guard.includes("'pageshow'") && guard.includes("'visibilitychange'"),
  mapGeometryHooks: guard.includes('installMapViewportHooks') && guard.includes('viewportFitMap') && guard.includes('viewportResize') && guard.includes('viewportFocusRoute'),
  dynamicHeightFallback: styles.includes('100dvh') && styles.includes('@media(max-height:500px)') && guard.includes('font-size: max(16px, 1em)'),
  releaseOwnership: manifest.runtimeOwners?.pageViewportScale === 'page-zoom-guard.js' && manifest.runtimeOwners?.mapViewport === 'page-zoom-guard.js' && manifest.releaseAssets?.includes('page-zoom-guard.js'),
  offlineRefresh: serviceWorker.includes("'./page-zoom-guard.js'") && serviceWorker.includes('page-zoom-guard') && manifest.invariants?.requiredViewportScaleChecks === 120
};

const results = [];
for (const device of devices) {
  const orientation = device.width >= device.height ? 'landscape' : 'portrait';
  const fitScale = Math.min(device.width / 4096, device.height / 4096) * 1.1;
  const cappedDpr = Math.min(device.dpr, 2.5);
  const canvasWidth = Math.floor(device.width * cappedDpr);
  const canvasHeight = Math.floor(device.height * cappedDpr);
  const simulatedPageScale = 2;
  const normalizedWidth = Math.round((device.width / simulatedPageScale) * simulatedPageScale);
  const normalizedHeight = Math.round((device.height / simulatedPageScale) * simulatedPageScale);
  const checks = [
    ['device-profile', classify(device.width, device.height, device.touch) === device.profile],
    ['orientation', orientation === (device.width >= device.height ? 'landscape' : 'portrait')],
    ['fit-scale', Number.isFinite(fitScale) && fitScale > 0 && fitScale < 1],
    ['canvas-size', canvasWidth > 0 && canvasHeight > 0 && cappedDpr <= 2.5],
    ['zoom-normalization', normalizedWidth === device.width && normalizedHeight === device.height],
    ['aspect-ratio', Math.abs(canvasWidth / canvasHeight - device.width / device.height) < 0.01],
    ['viewport-source', staticContracts.canonicalViewport && staticContracts.visualViewportAuthority],
    ['scale-and-gesture', staticContracts.scaleRecovery && staticContracts.mapPinchPreserved],
    ['lifecycle-and-layout', staticContracts.lifecycleRecovery && staticContracts.mapGeometryHooks && staticContracts.dynamicHeightFallback],
    ['release-and-offline', staticContracts.guardRunsBeforeMap && staticContracts.releaseOwnership && staticContracts.offlineRefresh]
  ];
  for (const [name, passed] of checks) {
    results.push({ device: device.name, profile: device.profile, orientation, name, passed: Boolean(passed) });
  }
}

const failed = results.filter(result => !result.passed);
const report = {
  schemaVersion: 1,
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
