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

function rgbTriples(value) {
  return [...String(value).matchAll(/rgba?\((\d+)[, ]+(\d+)[, ]+(\d+)/g)].map(match => match.slice(1, 4).map(Number));
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
    await page.goto(`${baseURL}?visual-correction=09412c-${profile.name}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(() => Number(document.getElementById('visibleCount')?.textContent || 0) >= 3000, null, { timeout: 45_000 });
    await page.waitForTimeout(450);

    const visual = await page.evaluate(() => {
      const styleData = selector => {
        const node = document.querySelector(selector);
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
      };
      return {
        rootClass: document.documentElement.className,
        nav: styleData('.bottom-nav .nav-item.active'),
        rail: styleData('.quick-rail .rail-button.active'),
        controls: styleData('.map-controls'),
        buttons: ['#zoomIn', '#zoomOut', '#resetView'].map(styleData),
        variables: ['--atlas-red-light','--atlas-red-mid','--atlas-red-deep','--atlas-red-deeper','--atlas-red-ink'].reduce((out, key) => {
          out[key] = getComputedStyle(document.documentElement).getPropertyValue(key).trim();
          return out;
        }, {})
      };
    });

    for (const [name, state] of [['bottom selected', visual.nav], ['rail selected', visual.rail]]) {
      const stops = rgbTriples(state.backgroundImage);
      check(`${name} uses gradient`, state.backgroundImage.includes('linear-gradient'), state.backgroundImage);
      check(`${name} contains only light red stops`, stops.length >= 4 && stops.every(([r, g, b]) => r >= 230 && g >= 170 && b >= 180), JSON.stringify(stops));
      check(`${name} uses dark rose ink`, rgbTriples(state.color).some(([r, g, b]) => r < 140 && g < 90 && b < 100), state.color);
    }

    check('light-red variables are present', Object.values(visual.variables).every(Boolean), JSON.stringify(visual.variables));
    check('no legacy deep-red variables remain active', !Object.values(visual.variables).some(value => /#64131e|#3d0b12|rgb\(100[, ]+19[, ]+30\)|rgb\(61[, ]+11[, ]+18\)/i.test(value)), JSON.stringify(visual.variables));

    const transparent = state => state.backgroundColor === 'rgba(0, 0, 0, 0)' && state.backgroundImage === 'none' && state.borderTopWidth === '0px' && state.borderBottomWidth === '0px' && state.boxShadow === 'none' && state.backdropFilter === 'none';
    check('map control container is frameless transparent', transparent(visual.controls), JSON.stringify(visual.controls));
    visual.buttons.forEach((button, index) => {
      check(`map action ${index + 1} is frameless transparent`, transparent(button), JSON.stringify(button));
      check(`map action ${index + 1} remains a touch target`, button.rect.width >= 40 && button.rect.height >= 38, JSON.stringify(button.rect));
      check(`map action ${index + 1} remains interactive`, button.pointerEvents !== 'none');
    });

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
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.12c', passed: !failed, profiles: report }, null, 2));
if (failed) process.exit(1);
