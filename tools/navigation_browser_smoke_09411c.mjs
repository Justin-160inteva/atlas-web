import { chromium } from 'playwright';

const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const ipadUA = 'Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const iphoneUA = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const profiles = [
  { name: 'desktop-wide', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false, maxBlur: 16 },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true, userAgent: ipadUA, maxBlur: 14 },
  { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent: iphoneUA, maxBlur: 12 }
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
    await page.goto(`${baseURL}?navigation-smoke=09412d-${profile.name}`, { waitUntil: 'domcontentloaded', timeout: 45_000 });
    await page.waitForFunction(() => Number(document.getElementById('visibleCount')?.textContent || 0) >= 3000, null, { timeout: 45_000 });
    await page.waitForFunction(() => window.AtlasNavigationRecovery?.version === '0.9.4.11b', null, { timeout: 15_000 });
    await page.waitForFunction(() => window.AtlasMarkerDesign?.version === '0.9.4.12b-1', null, { timeout: 15_000 });
    await page.waitForTimeout(450);

    const geometry = await page.evaluate(() => {
      const read = selector => {
        const node = document.querySelector(selector);
        const rect = node.getBoundingClientRect();
        const style = getComputedStyle(node);
        const matrix = new DOMMatrixReadOnly(style.transform === 'none' ? 'matrix(1,0,0,1,0,0)' : style.transform);
        return {
          left: rect.left, right: rect.right, top: rect.top, bottom: rect.bottom,
          width: rect.width, height: rect.height, transformX: matrix.e,
          pointerEvents: style.pointerEvents, visibility: style.visibility,
          opacity: Number.parseFloat(style.opacity)
        };
      };
      return {
        bottom: read('.bottom-nav'), rail: read('.quick-rail'),
        viewport: { width: innerWidth, height: innerHeight },
        audit: window.AtlasNavigationRecovery.audit(), markerAudit: window.AtlasMarkerDesign.audit()
      };
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

    check('marker runtime version is current', geometry.markerAudit.version === '0.9.4.12b-1', JSON.stringify(geometry.markerAudit));
    check('marker uses anchored long-tail droplet', geometry.markerAudit.shape === 'anchored-long-tail-droplet' && geometry.markerAudit.anchor === 'bottom-tip', JSON.stringify(geometry.markerAudit));
    check('marker selection is scale only', geometry.markerAudit.selectionFeedback === 'scale-only' && geometry.markerAudit.selectionRing === false && geometry.markerAudit.selectionBorder === false, JSON.stringify(geometry.markerAudit));
    check('marker selection scale is 1.28', geometry.markerAudit.selectedScale === 1.28, JSON.stringify(geometry.markerAudit));
    check('marker selection duration is 190ms', geometry.markerAudit.durationMs === 190, JSON.stringify(geometry.markerAudit));

    const glassState = await page.evaluate(() => {
      const blurValue = value => Number((String(value).match(/blur\((\d+(?:\.\d+)?)px\)/) || [])[1] || 0);
      const inspect = selector => {
        const node = document.querySelector(selector);
        if (!node) return null;
        const style = getComputedStyle(node);
        return {
          selector, background: style.backgroundImage,
          backdrop: style.backdropFilter || style.webkitBackdropFilter || 'none',
          blur: blurValue(style.backdropFilter || style.webkitBackdropFilter),
          border: Number.parseFloat(style.borderTopWidth) || 0,
          radius: Number.parseFloat(style.borderTopLeftRadius) || 0,
          shadow: style.boxShadow, transition: style.transitionDuration
        };
      };
      const root = getComputedStyle(document.documentElement);
      const selectors = ['.top-bar','.quick-rail','.bottom-nav','.status-pill','#filterPanel','.settings-panel','.search-modal','#detailSheet'];
      const nested = ['.filter-summary','.evidence-section','.data-center-tabs'].map(inspect).filter(Boolean);
      return {
        tokens: {
          surface: root.getPropertyValue('--atlas-glass-surface').trim(),
          light: root.getPropertyValue('--atlas-red-light').trim(),
          mid: root.getPropertyValue('--atlas-red-mid').trim(),
          deep: root.getPropertyValue('--atlas-red-deep').trim(),
          deeper: root.getPropertyValue('--atlas-red-deeper').trim(),
          ink: root.getPropertyValue('--atlas-red-ink').trim(),
          blur: root.getPropertyValue('--atlas-glass-blur').trim()
        },
        surfaces: selectors.map(inspect).filter(Boolean), nested,
        active: inspect('.bottom-nav .nav-item.active'),
        primary: inspect('.route-actions .primary'),
        mapControls: inspect('.map-controls'), mapAction: inspect('.map-controls button')
      };
    });

    const translucentToken = value => /^rgba\(/.test(value) && /,\s*0?\.[0-9]+\)$/.test(value);
    check('glass token is installed', glassState.tokens.surface.includes('linear-gradient'), JSON.stringify(glassState.tokens));
    check('ultra-light red token is translucent', translucentToken(glassState.tokens.light), JSON.stringify(glassState.tokens));
    check('mist-pink token is translucent', translucentToken(glassState.tokens.mid), JSON.stringify(glassState.tokens));
    check('light-rose tokens are translucent', translucentToken(glassState.tokens.deep) && translucentToken(glassState.tokens.deeper), JSON.stringify(glassState.tokens));
    check('dark rose ink token is installed', glassState.tokens.ink === 'var(--atlas-glass-active-ink)' || glassState.tokens.ink === '#6b2b37', JSON.stringify(glassState.tokens));
    check('representative surfaces exist', glassState.surfaces.length === 8, JSON.stringify(glassState.surfaces));
    for (const surface of glassState.surfaces) {
      check(`${surface.selector} uses glass gradient`, surface.background !== 'none' && surface.background.includes('linear-gradient'), JSON.stringify(surface));
      check(`${surface.selector} blur stays within budget`, surface.blur >= 0 && surface.blur <= profile.maxBlur + .1, JSON.stringify(surface));
      check(`${surface.selector} keeps border and radius`, surface.border >= .75 && surface.radius >= 12, JSON.stringify(surface));
      check(`${surface.selector} keeps bounded shadow`, surface.shadow !== 'none', JSON.stringify(surface));
    }
    for (const nested of glassState.nested) check(`${nested.selector} avoids nested blur`, nested.blur === 0, JSON.stringify(nested));
    check('map control container is frameless transparent', glassState.mapControls?.background === 'none' && glassState.mapControls.blur === 0 && glassState.mapControls.border === 0 && glassState.mapControls.radius === 0 && glassState.mapControls.shadow === 'none', JSON.stringify(glassState.mapControls));
    check('map action is frameless transparent', glassState.mapAction?.background === 'none' && glassState.mapAction.blur === 0 && glassState.mapAction.border === 0 && glassState.mapAction.shadow === 'none', JSON.stringify(glassState.mapAction));
    check('active control uses translucent glass gradient', glassState.active?.background.includes('linear-gradient') && glassState.active.background.includes('rgba'), JSON.stringify(glassState.active));
    check('primary control uses translucent glass gradient', glassState.primary?.background.includes('linear-gradient') && glassState.primary.background.includes('rgba'), JSON.stringify(glassState.primary));

    const selectedMarker = await page.evaluate(() => {
      const marker = state.markers.find(item => item.items?.[0]);
      if (!marker) return null;
      selectLocation(marker.items[0]);
      return marker.items[0].id;
    });
    check('visible marker can be selected', Boolean(selectedMarker), String(selectedMarker));
    await page.waitForTimeout(70);
    const markerMidAudit = await page.evaluate(() => window.AtlasMarkerDesign.audit());
    check('marker animation starts on selection', markerMidAudit.selectedId === selectedMarker && markerMidAudit.activeAnimations >= 1, JSON.stringify(markerMidAudit));
    await page.waitForFunction(() => window.AtlasMarkerDesign?.audit().activeAnimations === 0, null, { timeout: 1000 });
    const markerEndAudit = await page.evaluate(() => window.AtlasMarkerDesign.audit());
    check('marker animation settles after 190ms', markerEndAudit.selectedId === selectedMarker && markerEndAudit.activeAnimations === 0, JSON.stringify(markerEndAudit));
    await page.evaluate(() => window.closeSheet());
    await page.waitForTimeout(210);

    await page.locator('#evidenceStudioBtn').click({ timeout: 5000 });
    await page.waitForTimeout(180);
    check('settings panel opens over global glass', await page.locator('.settings-panel.open').count() === 1);
    check('settings panel remains interactive', await page.locator('.settings-panel.open').evaluate(node => getComputedStyle(node).pointerEvents !== 'none'));
    await page.locator('.settings-close').click({ timeout: 5000 });

    await page.locator('#searchTrigger').click({ timeout: 5000 });
    await page.waitForTimeout(120);
    check('search glass opens', await page.locator('#searchOverlay.open .search-modal').count() === 1);
    await page.locator('#closeSearch').click({ timeout: 5000 });

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

    const returnCases = [['filter','locations','#filterPanel'],['route','collectibles','#routePanel'],['progress','activities','#progressPanel']];
    for (const [panel, mode, selector] of returnCases) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click({ timeout: 5000 });
      await page.locator('.bottom-nav .nav-item[data-panel="map"]').click({ timeout: 5000 });
      await page.waitForTimeout(100);
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click({ timeout: 5000 });
      check(`${panel} return restores rail ${mode}`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`${panel} return closes panel safely`, await page.locator(selector).evaluate(node => node.getAttribute('aria-hidden') === 'true' && node.hasAttribute('inert') && getComputedStyle(node).pointerEvents === 'none'));
    }

    const finalAudit = await page.evaluate(() => ({ navigation: window.AtlasNavigationRecovery.audit(), marker: window.AtlasMarkerDesign.audit() }));
    check('final rail audit passes', finalAudit.navigation.railInteractive, JSON.stringify(finalAudit.navigation));
    check('final closed-panel audit passes', finalAudit.navigation.closedPanelsSafe, JSON.stringify(finalAudit.navigation));
    check('final marker audit remains scale only', finalAudit.marker.selectionFeedback === 'scale-only' && finalAudit.marker.selectionRing === false && finalAudit.marker.selectionBorder === false, JSON.stringify(finalAudit.marker));
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {
    failed = true;
    errors.push(String(error?.stack || error));
  }

  report.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
for (const result of report) {
  const passed = result.checks.filter(item => item.passed).length;
  console.log(`${result.profile}: ${passed}/${result.checks.length}; errors=${result.errors.length}`);
}
console.log(JSON.stringify({ schemaVersion: 1, version: '0.9.4.12d', passed: !failed, profiles: report }, null, 2));
if (failed) process.exit(1);
