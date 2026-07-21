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

try {
  await page.goto(`${baseURL}?ipad-landscape-viewport-smoke=1&v=${manifest.version}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
  await page.waitForFunction(minimum => Number(document.getElementById('visibleCount')?.textContent || 0) >= minimum, manifest.invariants.minimumLocationCount, { timeout: 45_000 });
  await page.waitForFunction(() => document.documentElement.dataset.atlasViewportReady === 'true' && window.AtlasViewport?.measure, null, { timeout: 15_000 });
  await page.waitForTimeout(700);

  const portrait = await page.evaluate(() => {
    const shell = document.querySelector('.app-shell').getBoundingClientRect();
    const canvas = document.getElementById('mapCanvas').getBoundingClientRect();
    return {
      innerWidth,
      innerHeight,
      shell: { left: shell.left, top: shell.top, right: shell.right, bottom: shell.bottom, width: shell.width, height: shell.height },
      canvas: { left: canvas.left, top: canvas.top, right: canvas.right, bottom: canvas.bottom, width: canvas.width, height: canvas.height },
      measured: window.AtlasViewport.measure(),
      stats: window.AtlasViewport.stats?.()
    };
  });
  check('portrait shell fills width', Math.abs(portrait.shell.width - portrait.innerWidth) <= 2, JSON.stringify(portrait));
  check('portrait shell fills height', Math.abs(portrait.shell.height - portrait.innerHeight) <= 2, JSON.stringify(portrait));

  await page.setViewportSize({ width: 1180, height: 820 });
  await page.evaluate(() => window.dispatchEvent(new Event('orientationchange')));
  await page.waitForFunction(() => document.documentElement.dataset.atlasViewportOrientation === 'landscape' && document.documentElement.dataset.atlasViewportSettling === 'false', null, { timeout: 5_000 });
  await page.waitForTimeout(250);

  const samples = [];
  for (let index = 0; index < 7; index += 1) {
    samples.push(await page.evaluate(() => {
      const shell = document.querySelector('.app-shell').getBoundingClientRect();
      const canvas = document.getElementById('mapCanvas').getBoundingClientRect();
      return {
        innerWidth,
        innerHeight,
        shellWidth: shell.width,
        shellHeight: shell.height,
        shellRight: shell.right,
        shellBottom: shell.bottom,
        canvasWidth: canvas.width,
        canvasHeight: canvas.height,
        canvasRight: canvas.right,
        canvasBottom: canvas.bottom,
        measured: window.AtlasViewport.measure(),
        stats: window.AtlasViewport.stats?.(),
        source: document.documentElement.dataset.atlasViewportSource,
        commitCount: Number(document.documentElement.dataset.atlasViewportCommitCount || 0)
      };
    }));
    await page.waitForTimeout(120);
  }

  const first = samples[0];
  const last = samples.at(-1);
  const sizesStable = samples.every(sample =>
    Math.abs(sample.shellWidth - first.shellWidth) <= 1 &&
    Math.abs(sample.shellHeight - first.shellHeight) <= 1 &&
    Math.abs(sample.canvasWidth - first.canvasWidth) <= 1 &&
    Math.abs(sample.canvasHeight - first.canvasHeight) <= 1
  );
  const commitsStable = samples.every(sample => sample.commitCount === first.commitCount);

  check('landscape source is layout shell', first.source === 'layout-shell' && first.measured.source === 'layout-shell', JSON.stringify(first));
  check('landscape shell fills width', Math.abs(first.shellWidth - first.innerWidth) <= 2 && Math.abs(first.shellRight - first.innerWidth) <= 2, JSON.stringify(first));
  check('landscape shell fills height', Math.abs(first.shellHeight - first.innerHeight) <= 2 && Math.abs(first.shellBottom - first.innerHeight) <= 2, JSON.stringify(first));
  check('landscape canvas fills width', Math.abs(first.canvasWidth - first.innerWidth) <= 2 && Math.abs(first.canvasRight - first.innerWidth) <= 2, JSON.stringify(first));
  check('landscape canvas fills height', Math.abs(first.canvasHeight - first.innerHeight) <= 2 && Math.abs(first.canvasBottom - first.innerHeight) <= 2, JSON.stringify(first));
  check('measured layout matches browser', Math.abs(first.measured.width - first.innerWidth) <= 2 && Math.abs(first.measured.height - first.innerHeight) <= 2, JSON.stringify(first));
  check('no post-rotation size jitter', sizesStable, JSON.stringify(samples));
  check('no post-rotation commit loop', commitsStable && first.commitCount <= manifest.invariants.viewportMaximumStartupCommits, JSON.stringify(samples));
  check('viewport remains stable after observation', last.stats?.settling === false, JSON.stringify(last));
  check('no runtime errors', errors.length === 0, errors.join('\n'));
} catch (error) {
  failed = true;
  errors.push(String(error?.stack || error));
}

await context.close();
await browser.close();
const passedChecks = checks.filter(item => item.passed).length;
const report = {
  schemaVersion: 1,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: !failed && passedChecks === checks.length,
  totalChecks: checks.length,
  checks,
  errors
};
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/ipad-landscape-viewport.json', import.meta.url), `${JSON.stringify(report, null, 2)}\n`);
console.log(`iPad landscape viewport: ${passedChecks}/${checks.length}; errors=${errors.length}`);
if (!report.passed) process.exit(2);
