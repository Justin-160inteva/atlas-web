import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const ipadUA = 'Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({
  viewport: { width: 820, height: 1180 },
  userAgent: ipadUA,
  isMobile: true,
  hasTouch: true,
  deviceScaleFactor: 2,
  serviceWorkers: 'allow'
});
const page = await context.newPage();
const checks = [];
const errors = [];
let failed = false;
const check = (name, condition, detail = '') => {
  checks.push({ name, passed: Boolean(condition), detail });
  if (!condition) failed = true;
};
page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });

const inspect = () => page.evaluate(() => {
  const shell = document.querySelector('.app-shell').getBoundingClientRect();
  const canvas = document.getElementById('mapCanvas').getBoundingClientRect();
  const scale = Number(state?.scale || 0);
  const offsetX = Number(state?.offsetX || 0);
  const offsetY = Number(state?.offsetY || 0);
  const mapSize = 4096 * scale;
  const coverScale = Number(window.AtlasMapCover?.coverScale?.() || 0);
  const manualMinimumScale = Number(window.AtlasMapCover?.manualMinimumScale?.() || 0);
  return {
    innerWidth,
    innerHeight,
    shell: { left: shell.left, top: shell.top, right: shell.right, bottom: shell.bottom, width: shell.width, height: shell.height },
    canvas: { left: canvas.left, top: canvas.top, right: canvas.right, bottom: canvas.bottom, width: canvas.width, height: canvas.height },
    map: {
      scale,
      ratio: coverScale > 0 ? scale / coverScale : 0,
      left: offsetX,
      top: offsetY,
      right: offsetX + mapSize,
      bottom: offsetY + mapSize,
      centerX: offsetX + mapSize / 2,
      centerY: offsetY + mapSize / 2,
      coverScale,
      manualMinimumScale,
      manualMinimumRatio: Number(window.AtlasMapCover?.manualMinimumRatio || 0),
      zoomLabel: document.getElementById('zoomLabel')?.textContent || ''
    },
    measured: window.AtlasViewport.measure(),
    stats: window.AtlasViewport.stats?.(),
    source: document.documentElement.dataset.atlasViewportSource,
    commitCount: Number(document.documentElement.dataset.atlasViewportCommitCount || 0),
    coverReady: window.AtlasMapCover?.ready?.() === true && document.documentElement.dataset.atlasMapCoverReady === 'true'
  };
});

function mapCoversViewport(sample) {
  return sample.map.left <= 1 && sample.map.top <= 1 && sample.map.right >= sample.innerWidth - 1 && sample.map.bottom >= sample.innerHeight - 1;
}

function mapCentered(sample) {
  return Math.abs(sample.map.centerX - sample.innerWidth / 2) <= 2 && Math.abs(sample.map.centerY - sample.innerHeight / 2) <= 2;
}

try {
  await page.goto(`${baseURL}?ipad-landscape-viewport-smoke=1&v=${manifest.version}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  await page.waitForFunction(minimum => Number(document.getElementById('visibleCount')?.textContent || 0) >= minimum, manifest.invariants.minimumLocationCount, { timeout: 45_000 });
  await page.waitForFunction(() => document.documentElement.dataset.atlasViewportReady === 'true' && window.AtlasViewport?.measure && window.AtlasMapCover?.ready?.(), null, { timeout: 15_000 });
  await page.waitForTimeout(700);

  const portrait = await inspect();
  check('portrait shell fills width', Math.abs(portrait.shell.width - portrait.innerWidth) <= 2, JSON.stringify(portrait));
  check('portrait shell fills height', Math.abs(portrait.shell.height - portrait.innerHeight) <= 2, JSON.stringify(portrait));
  check('portrait map cover ready', portrait.coverReady, JSON.stringify(portrait));
  check('portrait world map covers viewport', mapCoversViewport(portrait), JSON.stringify(portrait));
  check('portrait world map is centered', mapCentered(portrait), JSON.stringify(portrait));

  await page.setViewportSize({ width: 1180, height: 820 });
  await page.evaluate(() => window.dispatchEvent(new Event('orientationchange')));
  await page.waitForFunction(() => document.documentElement.dataset.atlasViewportOrientation === 'landscape' && document.documentElement.dataset.atlasViewportSettling === 'false' && document.documentElement.dataset.atlasMapCoverReady === 'true', null, { timeout: 5_000 });
  await page.waitForTimeout(300);

  const samples = [];
  for (let index = 0; index < 7; index += 1) {
    samples.push(await inspect());
    await page.waitForTimeout(120);
  }

  const first = samples[0];
  const last = samples.at(-1);
  const sizesStable = samples.every(sample =>
    Math.abs(sample.shell.width - first.shell.width) <= 1 &&
    Math.abs(sample.shell.height - first.shell.height) <= 1 &&
    Math.abs(sample.canvas.width - first.canvas.width) <= 1 &&
    Math.abs(sample.canvas.height - first.canvas.height) <= 1 &&
    Math.abs(sample.map.scale - first.map.scale) <= 0.00001 &&
    Math.abs(sample.map.left - first.map.left) <= 1 &&
    Math.abs(sample.map.top - first.map.top) <= 1
  );
  const commitsStable = samples.every(sample => sample.commitCount === first.commitCount);

  check('landscape source is layout shell', first.source === 'layout-shell' && first.measured.source === 'layout-shell', JSON.stringify(first));
  check('landscape shell fills width', Math.abs(first.shell.width - first.innerWidth) <= 2 && Math.abs(first.shell.right - first.innerWidth) <= 2, JSON.stringify(first));
  check('landscape shell fills height', Math.abs(first.shell.height - first.innerHeight) <= 2 && Math.abs(first.shell.bottom - first.innerHeight) <= 2, JSON.stringify(first));
  check('landscape canvas fills width', Math.abs(first.canvas.width - first.innerWidth) <= 2 && Math.abs(first.canvas.right - first.innerWidth) <= 2, JSON.stringify(first));
  check('landscape canvas fills height', Math.abs(first.canvas.height - first.innerHeight) <= 2 && Math.abs(first.canvas.bottom - first.innerHeight) <= 2, JSON.stringify(first));
  check('landscape automatic fit covers viewport', mapCoversViewport(first) && first.map.scale + 0.00001 >= first.map.coverScale, JSON.stringify(first));
  check('landscape automatic fit is centered', mapCentered(first), JSON.stringify(first));
  check('manual minimum is below automatic cover', first.map.manualMinimumScale > 0 && first.map.manualMinimumScale < first.map.coverScale && Math.abs(first.map.manualMinimumRatio - 0.25) <= 0.00001, JSON.stringify(first));
  check('measured layout matches browser', Math.abs(first.measured.width - first.innerWidth) <= 2 && Math.abs(first.measured.height - first.innerHeight) <= 2, JSON.stringify(first));
  check('no post-rotation size or map jitter', sizesStable, JSON.stringify(samples));
  check('no post-rotation commit loop', commitsStable && first.commitCount <= manifest.invariants.viewportMaximumStartupCommits, JSON.stringify(samples));
  check('viewport remains stable after observation', last.stats?.settling === false, JSON.stringify(last));

  for (let index = 0; index < 12; index += 1) {
    await page.click('#zoomOut');
    await page.waitForTimeout(90);
  }
  const manualZoom = await inspect();
  check('manual zoom can go below 1.0x cover', manualZoom.map.ratio < 0.95 && manualZoom.map.zoomLabel !== '×1.00', JSON.stringify(manualZoom));
  check('manual zoom reaches configured minimum', manualZoom.map.ratio <= 0.27 && manualZoom.map.ratio >= 0.249 && manualZoom.map.scale + 0.00001 >= manualZoom.map.manualMinimumScale, JSON.stringify(manualZoom));

  await page.click('#resetView');
  await page.waitForTimeout(250);
  const reset = await inspect();
  check('reset returns to 1.0x cover', Math.abs(reset.map.ratio - 1) <= 0.01 && reset.map.zoomLabel === '×1.00', JSON.stringify(reset));
  check('reset restores full map cover', mapCoversViewport(reset) && mapCentered(reset), JSON.stringify(reset));
  check('no runtime errors', errors.length === 0, errors.join('\n'));
} catch (error) {
  failed = true;
  errors.push(String(error?.stack || error));
}

await context.close();
await browser.close();
const passedChecks = checks.filter(item => item.passed).length;
const report = {
  schemaVersion: 3,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: !failed && passedChecks === checks.length,
  totalChecks: checks.length,
  checks,
  errors
};
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/ipad-landscape-viewport.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
console.log(`iPad map cover and manual zoom: ${passedChecks}/${checks.length}; errors=${errors.length}`);
if (!report.passed) process.exit(2);
