import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const profiles = [
  { name: 'desktop', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true },
  { name: 'ipad-portrait', viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true }
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
  page.on('console', message => {
    if (message.type() === 'error') errors.push(`console: ${message.text()}`);
  });
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

    const versionText = await page.locator('.brand-copy small').textContent();
    check('release label', versionText === manifest.versionText, String(versionText));
    check('release conflict absent', await page.locator('html[data-atlas-release-conflict="1"]').count() === 0);
    check('location count', Number(await page.locator('#visibleCount').textContent()) >= manifest.invariants.minimumLocationCount);

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
      if (panelMap[panel]) {
        const locator = page.locator(panelMap[panel]);
        check(`${panel} panel open`, await locator.evaluate(node => node.classList.contains('open') && node.getAttribute('aria-hidden') === 'false'));
      }
    }

    for (const mode of ['all', 'locations', 'collectibles', 'activities', 'favorites']) {
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click();
      await page.waitForTimeout(220);
      check(`rail ${mode} active`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
    }

    const releaseScripts = await page.evaluate(() => [...document.scripts]
      .filter(script => /atlas-(?:bootstrap|analysis-import|liquid-nav-0934|controls-0938|ipad-nav-0940)\.js/.test(script.src))
      .map(script => script.src));
    const wrongScript = releaseScripts.find(url => !url.includes(`v=${manifest.version}`));
    check('release scripts use one cache version', !wrongScript, wrongScript || releaseScripts.join('\n'));
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
await fs.writeFile(new URL('../data/conflict-reports/browser-matrix.json', import.meta.url), JSON.stringify({
  schemaVersion: 1,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: !failed,
  profiles: results
}, null, 2) + '\n');

for (const result of results) {
  const passed = result.checks.filter(check => check.passed).length;
  console.log(`${result.profile}: ${passed}/${result.checks.length} checks; errors=${result.errors.length}`);
}
if (failed) process.exit(2);
