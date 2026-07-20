import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const profiles = [
  {
    name: 'mobile-390x844',
    viewport: { width: 390, height: 844 },
    userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
  },
  {
    name: 'ipad-820x1180',
    viewport: { width: 820, height: 1180 },
    userAgent: 'Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1'
  }
];

const browser = await chromium.launch({ headless: true });
const results = [];
let failed = false;

for (const profile of profiles) {
  const context = await browser.newContext({
    viewport: profile.viewport,
    userAgent: profile.userAgent,
    isMobile: true,
    hasTouch: true,
    deviceScaleFactor: 2,
    serviceWorkers: 'allow'
  });
  const page = await context.newPage();
  const checks = [];
  const errors = [];
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });
  const check = (name, condition, detail = '') => {
    checks.push({ name, passed: Boolean(condition), detail });
    if (!condition) failed = true;
  };

  try {
    await page.goto(`${baseURL}?reward-search-smoke=1&v=${manifest.version}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(minimum => Number(document.getElementById('visibleCount')?.textContent || 0) >= minimum, manifest.invariants.minimumLocationCount, { timeout: 45_000 });
    await page.waitForFunction(() => window.AtlasSearchOwner === 'reward-aware-bilingual-search-v2' && window.AtlasRewards?.ready === true, null, { timeout: 20_000 });

    check('search owner', await page.evaluate(() => window.AtlasSearchOwner) === 'reward-aware-bilingual-search-v2');
    check('search owner dataset', await page.locator('html').getAttribute('data-atlas-search-owner') === 'reward-aware-bilingual-search-v2');

    await page.locator('#searchTrigger').click();
    const input = page.locator('#searchInput');
    await input.fill("Minogame's Protection");
    const first = page.locator('.result-item').first();
    await first.waitFor({ state: 'visible', timeout: 10_000 });
    const exactState = await first.evaluate(node => ({
      id: node.dataset.id,
      kind: node.dataset.searchKind,
      badge: node.querySelector('.atlas-search-match')?.textContent || '',
      hint: node.querySelector('.atlas-search-reward')?.textContent || ''
    }));
    check('english reward exact first', exactState.kind === 'reward-exact', JSON.stringify(exactState));
    check('english reward badge', exactState.badge === '奖励精确匹配', exactState.badge);
    check('matched reward only', exactState.hint.includes("Minogame's Protection") && !exactState.hint.includes('经验值') && !exactState.hint.includes('技能点'), exactState.hint);

    await input.fill('经验值');
    await page.locator('.result-item').first().waitFor({ state: 'visible', timeout: 10_000 });
    const chineseState = await page.locator('.result-item').first().evaluate(node => ({
      kind: node.dataset.searchKind,
      hint: node.querySelector('.atlas-search-reward')?.textContent || ''
    }));
    check('chinese reward exact first', chineseState.kind === 'reward-exact', JSON.stringify(chineseState));
    check('chinese matched reward only', chineseState.hint.includes('经验值') && !chineseState.hint.includes('技能点'), chineseState.hint);

    await input.fill("Minogame's Protection");
    await page.locator('.result-item').first().waitFor({ state: 'visible', timeout: 10_000 });
    const selectedId = await page.locator('.result-item').first().getAttribute('data-id');
    await page.locator('.result-item').first().click();
    await page.waitForFunction(id => String(state.selected?.id || '') === String(id) && document.getElementById('detailSheet')?.classList.contains('open'), selectedId, { timeout: 3_000 });

    const focusState = await page.evaluate(() => {
      const point = mapToScreen(state.selected);
      const width = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--atlas-viewport-width')) || innerWidth;
      const height = parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--atlas-viewport-height')) || innerHeight;
      return {
        overlayOpen: document.getElementById('searchOverlay')?.classList.contains('open'),
        inputFocused: document.activeElement === document.getElementById('searchInput'),
        scale: Number(window.visualViewport?.scale || 1),
        dx: Math.abs(point.x - width / 2),
        dy: Math.abs(point.y - height / 2)
      };
    });
    check('search closes before focus', !focusState.overlayOpen && !focusState.inputFocused, JSON.stringify(focusState));
    check('page scale normalized', Math.abs(focusState.scale - 1) <= .02, String(focusState.scale));
    check('selected location centered', focusState.dx <= 4 && focusState.dy <= 4, JSON.stringify(focusState));
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {
    failed = true;
    errors.push(String(error?.stack || error));
  }

  results.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
const totalChecks = results.reduce((sum, result) => sum + result.checks.length, 0);
const passedChecks = results.reduce((sum, result) => sum + result.checks.filter(check => check.passed).length, 0);
const report = {
  schemaVersion: 1,
  release: manifest.version,
  generatedAt: new Date().toISOString(),
  passed: !failed && passedChecks === totalChecks,
  totalChecks,
  profiles: results
};
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
await fs.writeFile(new URL('../data/conflict-reports/reward-search-browser.json', import.meta.url), JSON.stringify(report, null, 2) + '\n');
console.log(`Reward search browser: ${passedChecks}/${totalChecks}; profiles=${profiles.length}`);
if (!report.passed) process.exit(2);
