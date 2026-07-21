import { chromium } from 'playwright';

const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const ipadUA = 'Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const iphoneUA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const profiles = [
  { name: 'desktop-wide', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true, userAgent: ipadUA },
  { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent: iphoneUA }
];

const browser = await chromium.launch({ headless: true });
const report = [];
let failed = false;

for (const profile of profiles) {
  const context = await browser.newContext({
    viewport: profile.viewport,
    isMobile: profile.isMobile,
    hasTouch: profile.hasTouch,
    userAgent: profile.userAgent,
    deviceScaleFactor: profile.hasTouch ? 2 : 1,
    serviceWorkers: 'block'
  });
  const page = await context.newPage();
  const checks = [];
  const errors = [];
  const check = (name, value, detail = '') => {
    const passed = Boolean(value);
    checks.push({ name, passed, detail });
    if (!passed) failed = true;
  };
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });

  try {
    await page.goto(`${baseURL}?navigation-smoke=09411c-${profile.name}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(() => Number(document.getElementById('visibleCount')?.textContent || 0) >= 3000, null, { timeout: 45_000 });
    await page.waitForFunction(() => window.AtlasNavigationRecovery?.version === '0.9.4.11b', null, { timeout: 15_000 });
    await page.waitForTimeout(450);

    const geometry = await page.evaluate(() => {
      const read = selector => {
        const node = document.querySelector(selector);
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        const matrix = new DOMMatrixReadOnly(style.transform === 'none' ? 'matrix(1,0,0,1,0,0)' : style.transform);
        return { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height, transformX: matrix.e, pointerEvents: style.pointerEvents, visibility: style.visibility, opacity: Number.parseFloat(style.opacity) };
      };
      return { bottom: read('.bottom-nav'), rail: read('.quick-rail'), viewport: { width: innerWidth, height: innerHeight }, audit: window.AtlasNavigationRecovery.audit() };
    });

    const inset = 8;
    check('bottom left fully visible', geometry.bottom.left >= inset - .75, JSON.stringify(geometry.bottom));
    check('bottom right fully visible', geometry.bottom.right <= geometry.viewport.width - inset + .75, JSON.stringify(geometry.bottom));
    check('bottom lower edge fully visible', geometry.bottom.bottom <= geometry.viewport.height - inset + .75, JSON.stringify(geometry.bottom));
    check('bottom physically centred', Math.abs((geometry.bottom.left + geometry.bottom.right) / 2 - geometry.viewport.width / 2) <= 1.25, JSON.stringify(geometry.bottom));
    check('bottom has neutral transform matrix', Math.abs(geometry.bottom.transformX) <= .5, String(geometry.bottom.transformX));
    check('bottom is interactive', geometry.bottom.pointerEvents !== 'none' && geometry.bottom.visibility === 'visible' && geometry.bottom.opacity > .9, JSON.stringify(geometry.bottom));
    check('rail left fully visible', geometry.rail.left >= inset - .75, JSON.stringify(geometry.rail));
    check('rail right fully visible', geometry.rail.right <= geometry.viewport.width - inset + .75, JSON.stringify(geometry.rail));
    check('rail is interactive', geometry.audit.railInteractive && geometry.rail.pointerEvents !== 'none', JSON.stringify(geometry.audit));
    check('closed panels are safe', geometry.audit.closedPanelsSafe, JSON.stringify(geometry.audit));
    check('settings icon is valid', geometry.audit.settingsIconValid, JSON.stringify(geometry.audit));

    for (const panel of ['map', 'filter', 'route', 'progress', 'favorites']) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click({ timeout: 5000 });
      await page.waitForTimeout(100);
      check(`bottom ${panel} activates`, await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"].active`).count() === 1);
      check(`bottom ${panel} keeps one active`, await page.locator('.bottom-nav .nav-item.active').count() === 1);
    }

    for (const mode of ['all', 'locations', 'collectibles', 'activities', 'favorites']) {
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click({ timeout: 5000 });
      await page.waitForTimeout(90);
      check(`rail ${mode} activates`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`rail ${mode} keeps one active`, await page.locator('.quick-rail .rail-button.active').count() === 1);
    }

    const returnCases = [['filter', 'locations', '#filterPanel'], ['route', 'collectibles', '#routePanel'], ['progress', 'activities', '#progressPanel']];
    for (const [panel, mode, selector] of returnCases) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click({ timeout: 5000 });
      await page.locator('.bottom-nav .nav-item[data-panel="map"]').click({ timeout: 5000 });
      await page.waitForTimeout(100);
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click({ timeout: 5000 });
      check(`${panel} return restores rail ${mode}`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`${panel} return closes panel safely`, await page.locator(selector).evaluate(node => node.getAttribute('aria-hidden') === 'true' && node.hasAttribute('inert') && getComputedStyle(node).pointerEvents === 'none'));
    }

    const finalAudit = await page.evaluate(() => window.AtlasNavigationRecovery.audit());
    check('final rail audit passes', finalAudit.railInteractive, JSON.stringify(finalAudit));
    check('final closed-panel audit passes', finalAudit.closedPanelsSafe, JSON.stringify(finalAudit));
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {
    failed = true;
    errors.push(String(error?.stack || error));
  }

  report.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
for (const result of report) console.log(`${result.profile}: ${result.checks.filter(item => item.passed).length}/${result.checks.length}; errors=${result.errors.length}`);
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.11c', passed: !failed, profiles: report }, null, 2));
if (failed) process.exit(1);
