import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const profiles = [
  { name: 'desktop-wide', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  { name: 'desktop-compact', viewport: { width: 1024, height: 768 }, isMobile: false, hasTouch: false },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true },
  { name: 'ipad-portrait', viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true },
  { name: 'tablet-compact', viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true },
  { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true }
];

const browser = await chromium.launch({ headless: true });
const results = [];
let failed = false;

for (const profile of profiles) {
  const context = await browser.newContext({
    viewport: profile.viewport,
    isMobile: profile.isMobile,
    hasTouch: profile.hasTouch,
    deviceScaleFactor: profile.hasTouch ? 2 : 1,
    serviceWorkers: 'allow'
  });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  page.on('requestfailed', request => errors.push(`request: ${request.url()} ${request.failure()?.errorText || ''}`));

  const checks = [];
  const check = (name, condition, detail = '') => {
    checks.push({ name, passed: Boolean(condition), detail });
    if (!condition) failed = true;
  };

  try {
    await page.goto(`${baseURL}?conflict-smoke=1&v=${manifest.version.replace(/\D/g, '')}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(minimum => Number(document.getElementById('visibleCount')?.textContent || 0) >= minimum, manifest.invariants.minimumLocationCount, { timeout: 45_000 });
    await page.waitForFunction(version => document.documentElement.dataset.atlasRelease === version, manifest.version, { timeout: 15_000 });
    await page.waitForFunction(() => document.documentElement.dataset.atlasControls && document.documentElement.dataset.atlasLiquidNav, null, { timeout: 15_000 });

    const versionText = await page.locator('.brand-copy small').textContent();
    check('release label', versionText === manifest.versionText, String(versionText));
    check('release conflict absent', await page.locator('html[data-atlas-release-conflict="1"]').count() === 0);
    check('location count', Number(await page.locator('#visibleCount').textContent()) >= manifest.invariants.minimumLocationCount);
    check('release dataset', await page.locator('html').getAttribute('data-atlas-release') === manifest.version);
    check('data guard dataset', await page.locator('html').getAttribute('data-atlas-data-guard') === manifest.version);
    check('controls dataset', await page.locator('html').getAttribute('data-atlas-controls') === manifest.version);
    check('liquid dataset', await page.locator('html').getAttribute('data-atlas-liquid-nav') === manifest.version);

    const canvas = await page.locator('#mapCanvas').evaluate(node => ({ width: node.width, height: node.height }));
    check('canvas width', canvas.width > 0, JSON.stringify(canvas));
    check('canvas height', canvas.height > 0, JSON.stringify(canvas));

    const iconState = await page.evaluate(() => {
      const inspect = (selector, hostSelector) => [...document.querySelectorAll(selector)].map(button => {
        const host = button.querySelector(hostSelector);
        return {
          svg: host?.querySelectorAll(':scope > svg.atlas-control-icon').length || 0,
          text: [...(host?.childNodes || [])].filter(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()).length
        };
      });
      return {
        bottom: inspect('.bottom-nav .nav-item', ':scope > span'),
        rail: inspect('.quick-rail .rail-button', '.rail-icon')
      };
    });
    for (const [group, entries] of Object.entries(iconState)) {
      entries.forEach((entry, index) => {
        check(`${group} icon ${index + 1} single svg`, entry.svg === manifest.invariants.navigationSvgPerButton, JSON.stringify(entry));
        check(`${group} icon ${index + 1} no legacy text`, entry.text === 0, JSON.stringify(entry));
      });
    }

    const panelMap = { filter: '#filterPanel', route: '#routePanel', progress: '#progressPanel' };
    for (const panel of ['map', 'filter', 'route', 'progress', 'favorites']) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click();
      await page.waitForTimeout(260);
      check(`bottom ${panel} active`, await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"].active`).count() === 1);
      check(`bottom ${panel} single active`, await page.locator('.bottom-nav .nav-item.active').count() === 1);
      if (panelMap[panel]) {
        const locator = page.locator(panelMap[panel]);
        check(`${panel} panel open`, await locator.evaluate(node => node.classList.contains('open') && node.getAttribute('aria-hidden') === 'false'));
      }
    }

    for (const mode of ['all', 'locations', 'collectibles', 'activities', 'favorites']) {
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click();
      await page.waitForTimeout(220);
      check(`rail ${mode} active`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`rail ${mode} single active`, await page.locator('.quick-rail .rail-button.active').count() === 1);
    }

    await page.locator('#evidenceStudioBtn').click();
    await page.waitForTimeout(120);
    check('settings opens', await page.locator('#atlasSettingsOverlay.open').count() === 1);
    check('settings aria visible', await page.locator('#atlasSettingsOverlay').getAttribute('aria-hidden') === 'false');
    await page.locator('.atlas-settings-close').click();
    check('settings closes', await page.locator('#atlasSettingsOverlay.open').count() === 0);

    const releaseScripts = await page.evaluate(() => [...document.scripts]
      .filter(script => /atlas-(?:bootstrap|analysis-import|liquid-nav-0934|controls-0938|ipad-nav-0940|data-guard-0939)\.js/.test(script.src))
      .map(script => script.src));
    const wrongScript = releaseScripts.find(url => !url.includes(`v=${manifest.version}`));
    check('release scripts use one cache version', !wrongScript, wrongScript || releaseScripts.join('\n'));
    check('bootstrap loaded once', releaseScripts.filter(url => url.includes('atlas-bootstrap.js')).length === 1, releaseScripts.join('\n'));
    check('controls loaded once', releaseScripts.filter(url => url.includes('atlas-controls-0938.js')).length === 1, releaseScripts.join('\n'));

    const registrations = await page.evaluate(async () => 'serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).map(item => item.active?.scriptURL || item.installing?.scriptURL || '') : []);
    check('service worker registration count', registrations.length <= 1, registrations.join('\n'));
    if (registrations.length) check('service worker release URL', registrations[0].includes(`v=${manifest.version}`), registrations[0]);

    if (profile.hasTouch && profile.viewport.width >= 744) {
      check('ipad class enabled', await page.locator('html.atlas-ipad').count() === 1);
    } else {
      check('ipad class not forced', await page.locator('html.atlas-ipad').count() === 0);
    }
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {
    failed = true;
    errors.push(String(error?.stack || error));
  }

  results.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
const totalChecks = results.reduce((sum, result) => sum + result.checks.length, 0);
await fs.writeFile(new URL('../data/conflict-reports/browser-matrix.json', import.meta.url), JSON.stringify({
  schemaVersion: 1,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: !failed,
  totalChecks,
  profiles: results
}, null, 2) + '\n');

for (const result of results) {
  const passed = result.checks.filter(check => check.passed).length;
  console.log(`${result.profile}: ${passed}/${result.checks.length} checks; errors=${result.errors.length}`);
}
console.log(`Browser matrix total checks: ${totalChecks}`);
if (totalChecks < 200 || totalChecks > 500) {
  console.error(`Expected 200-500 independent browser checks, got ${totalChecks}`);
  process.exit(3);
}
if (failed) process.exit(2);
