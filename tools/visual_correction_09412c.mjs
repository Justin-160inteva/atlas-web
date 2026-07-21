import { chromium } from 'playwright';

const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const profiles = [
  { name: 'desktop', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1' },
  { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1' }
];

const browser = await chromium.launch({ headless: true });
const report = [];
let failed = false;

function rgbaStops(value) {
  return [...String(value).matchAll(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)(?:[, /]+([\d.]+))?/g)].map(match => ({
    r: Number(match[1]), g: Number(match[2]), b: Number(match[3]), a: match[4] == null ? 1 : Number(match[4])
  }));
}

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
  const check = (name, condition, detail = '') => {
    const passed = Boolean(condition);
    checks.push({ name, passed, detail });
    if (!passed) failed = true;
  };
  page.on('pageerror', error => errors.push(`pageerror: ${error.message}`));
  page.on('console', message => { if (message.type() === 'error') errors.push(`console: ${message.text()}`); });

  try {
    await page.goto(`${baseURL}?visual-correction=09412d-${profile.name}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(() => Number(document.getElementById('visibleCount')?.textContent || 0) >= 3000, null, { timeout: 45_000 });
    await page.waitForTimeout(450);

    const styleData = async selector => page.locator(selector).evaluate(node => {
      const style = getComputedStyle(node);
      const rect = node.getBoundingClientRect();
      return {
        backgroundColor: style.backgroundColor,
        backgroundImage: style.backgroundImage,
        borderTopWidth: style.borderTopWidth,
        borderBottomWidth: style.borderBottomWidth,
        boxShadow: style.boxShadow,
        backdropFilter: style.backdropFilter || style.webkitBackdropFilter || 'none',
        color: style.color,
        pointerEvents: style.pointerEvents,
        rect: { left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom, width: rect.width, height: rect.height }
      };
    });

    const nav = await styleData('.bottom-nav .nav-item.active');
    const rail = await styleData('.quick-rail .rail-button.active');
    const search = await styleData('.search-trigger');
    const locate = await styleData('#locateBtn');
    const settings = await styleData('#evidenceStudioBtn');
    const controls = await styleData('.map-controls');
    const buttons = await Promise.all(['#zoomIn', '#zoomOut', '#resetView'].map(styleData));

    await page.locator('#evidenceStudioBtn').click({ timeout: 5000 });
    await page.waitForTimeout(180);
    const dataTab = await styleData('.data-center-tabs button.active');

    const variables = await page.evaluate(() => ['--atlas-glass-active-bg','--atlas-glass-floating-bg','--atlas-glass-active-line','--atlas-glass-active-ink'].reduce((out, key) => {
      out[key] = getComputedStyle(document.documentElement).getPropertyValue(key).trim();
      return out;
    }, {}));

    for (const [name, state] of [['bottom selected', nav], ['rail selected', rail], ['database tab', dataTab]]) {
      const stops = rgbaStops(state.backgroundImage);
      check(`${name} uses translucent gradient`, state.backgroundImage.includes('linear-gradient') && stops.length >= 4, state.backgroundImage);
      check(`${name} contains translucent alpha`, stops.some(stop => stop.a > 0 && stop.a < .6), JSON.stringify(stops));
      check(`${name} remains ultra-light pink`, stops.every(({ r, g, b }) => r >= 230 && g >= 170 && b >= 180), JSON.stringify(stops));
      check(`${name} uses rose ink`, rgbaStops(state.color).some(({ r, g, b }) => r < 140 && g < 90 && b < 100), state.color);
      if (!profile.name.startsWith('ipad')) check(`${name} uses live glass blur`, state.backdropFilter.includes('blur('), state.backdropFilter);
    }

    for (const [name, state] of [['search', search], ['locate', locate], ['settings', settings]]) {
      const stops = rgbaStops(state.backgroundImage);
      check(`${name} uses floating translucent glass`, state.backgroundImage.includes('linear-gradient') && stops.some(stop => stop.a > 0 && stop.a < .25), state.backgroundImage);
      check(`${name} keeps subtle border`, Number.parseFloat(state.borderTopWidth) >= .75, state.borderTopWidth);
      check(`${name} keeps bounded shadow`, state.boxShadow !== 'none', state.boxShadow);
    }

    check('glass tokens are installed', Object.values(variables).every(Boolean), JSON.stringify(variables));
    check('active token uses alpha channels', /rgba\(/.test(variables['--atlas-glass-active-bg']), variables['--atlas-glass-active-bg']);

    const transparent = state => state.backgroundColor === 'rgba(0, 0, 0, 0)' && state.backgroundImage === 'none' && state.borderTopWidth === '0px' && state.borderBottomWidth === '0px' && state.boxShadow === 'none' && state.backdropFilter === 'none';
    check('map control container stays frameless transparent', transparent(controls), JSON.stringify(controls));
    buttons.forEach((button, index) => {
      check(`map action ${index + 1} stays frameless transparent`, transparent(button), JSON.stringify(button));
      check(`map action ${index + 1} remains a touch target`, button.rect.width >= 40 && button.rect.height >= 38, JSON.stringify(button.rect));
      check(`map action ${index + 1} remains interactive`, button.pointerEvents !== 'none');
    });

    await page.locator('.settings-close').click({ timeout: 5000 });
    const before = await page.locator('#zoomLabel').textContent();
    await page.locator('#zoomIn').click({ timeout: 5000 });
    await page.waitForTimeout(120);
    const afterIn = await page.locator('#zoomLabel').textContent();
    check('zoom in still works', before !== afterIn, `${before} -> ${afterIn}`);
    await page.locator('#zoomOut').click({ timeout: 5000 });
    await page.locator('#resetView').click({ timeout: 5000 });
    check('reset remains clickable', true);
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {
    failed = true;
    errors.push(String(error?.stack || error));
  }

  report.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.12d', passed: !failed, profiles: report }, null, 2));
if (failed) process.exit(1);
