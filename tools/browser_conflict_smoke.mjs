import fs from 'node:fs/promises';
import process from 'node:process';
import { chromium } from 'playwright';

const manifest = JSON.parse(await fs.readFile(new URL('../release-manifest.json', import.meta.url), 'utf8'));
const baseURL = process.env.ATLAS_URL || 'http://127.0.0.1:4173/';
const ipadUA='Mozilla/5.0 (iPad; CPU OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const iphoneUA='Mozilla/5.0 (iPhone; CPU iPhone OS 18_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.5 Mobile/15E148 Safari/604.1';
const profiles = [
  { name: 'desktop-wide', viewport: { width: 1440, height: 900 }, isMobile: false, hasTouch: false },
  { name: 'desktop-compact', viewport: { width: 1024, height: 768 }, isMobile: false, hasTouch: false },
  { name: 'ipad-landscape', viewport: { width: 1180, height: 820 }, isMobile: true, hasTouch: true, userAgent:ipadUA },
  { name: 'ipad-portrait', viewport: { width: 820, height: 1180 }, isMobile: true, hasTouch: true, userAgent:ipadUA },
  { name: 'tablet-compact', viewport: { width: 768, height: 1024 }, isMobile: true, hasTouch: true, userAgent:ipadUA },
  { name: 'mobile', viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, userAgent:iphoneUA }
];

const browser = await chromium.launch({ headless: true });
const results = [];
let failed = false;

for (const [profileIndex, profile] of profiles.entries()) {
  const context = await browser.newContext({
    viewport: profile.viewport,
    isMobile: profile.isMobile,
    hasTouch: profile.hasTouch,
    userAgent:profile.userAgent,
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
        return {svg: host?.querySelectorAll(':scope > svg.atlas-control-icon').length || 0,text: [...(host?.childNodes || [])].filter(node => node.nodeType === Node.TEXT_NODE && node.textContent.trim()).length};
      });
      return {bottom: inspect('.bottom-nav .nav-item', ':scope > span'),rail: inspect('.quick-rail .rail-button', '.rail-icon')};
    });
    for (const [group, entries] of Object.entries(iconState)) entries.forEach((entry, index) => {check(`${group} icon ${index + 1} single svg`, entry.svg === manifest.invariants.navigationSvgPerButton, JSON.stringify(entry));check(`${group} icon ${index + 1} no legacy text`, entry.text === 0, JSON.stringify(entry));});

    const navigationGeometry = await page.evaluate(() => {
      const read = selector => {
        const node=document.querySelector(selector),rect=node.getBoundingClientRect(),style=getComputedStyle(node);
        const matrix=new DOMMatrixReadOnly(style.transform==='none'?'matrix(1,0,0,1,0,0)':style.transform);
        return {left:rect.left,right:rect.right,top:rect.top,bottom:rect.bottom,width:rect.width,height:rect.height,background:style.backgroundImage,borderTop:Number.parseFloat(style.borderTopWidth)||0,radiusTopLeft:Number.parseFloat(style.borderTopLeftRadius)||0,radiusBottomLeft:Number.parseFloat(style.borderBottomLeftRadius)||0,pointerEvents:style.pointerEvents,transformX:matrix.e};
      };
      return {bottom:read('.bottom-nav'),rail:read('.quick-rail'),viewport:{width:innerWidth,height:innerHeight}};
    });
    const minInset=Number(manifest.invariants.navigationMinimumVisibleInsetPixels||4);
    check('bottom fully visible left', navigationGeometry.bottom.left >= minInset-.75, JSON.stringify(navigationGeometry.bottom));
    check('bottom fully visible right', navigationGeometry.bottom.right <= navigationGeometry.viewport.width-minInset+.75, JSON.stringify(navigationGeometry.bottom));
    check('bottom fully visible lower edge', navigationGeometry.bottom.bottom <= navigationGeometry.viewport.height-minInset+.75, JSON.stringify(navigationGeometry.bottom));
    check('bottom horizontally centered', Math.abs((navigationGeometry.bottom.left+navigationGeometry.bottom.right)/2-navigationGeometry.viewport.width/2) <= 1.5, JSON.stringify(navigationGeometry.bottom));
    check('bottom has no horizontal translation drift', Math.abs(navigationGeometry.bottom.transformX) <= .5, String(navigationGeometry.bottom.transformX));
    check('bottom complete rounded medium', navigationGeometry.bottom.radiusTopLeft >= 18 && navigationGeometry.bottom.radiusBottomLeft >= 18, JSON.stringify(navigationGeometry.bottom));
    check('bottom visible border', navigationGeometry.bottom.borderTop >= .75, JSON.stringify(navigationGeometry.bottom));
    check('bottom material background', navigationGeometry.bottom.background !== 'none', navigationGeometry.bottom.background);
    check('rail fully visible left', navigationGeometry.rail.left >= minInset-.75, JSON.stringify(navigationGeometry.rail));
    check('rail fully visible right', navigationGeometry.rail.right <= navigationGeometry.viewport.width-minInset+.75, JSON.stringify(navigationGeometry.rail));
    check('rail fully visible top', navigationGeometry.rail.top >= 0, JSON.stringify(navigationGeometry.rail));
    check('rail fully visible bottom', navigationGeometry.rail.bottom <= navigationGeometry.viewport.height+.75, JSON.stringify(navigationGeometry.rail));
    check('rail complete rounded medium', navigationGeometry.rail.radiusTopLeft >= 18 && navigationGeometry.rail.radiusBottomLeft >= 18, JSON.stringify(navigationGeometry.rail));
    check('rail visible border', navigationGeometry.rail.borderTop >= .75, JSON.stringify(navigationGeometry.rail));
    check('rail material background', navigationGeometry.rail.background !== 'none', navigationGeometry.rail.background);

    const panelMap = { filter: '#filterPanel', route: '#routePanel', progress: '#progressPanel' };
    for (const panel of ['map', 'filter', 'route', 'progress', 'favorites']) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click();await page.waitForTimeout(260);
      check(`bottom ${panel} active`, await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"].active`).count() === 1);
      check(`bottom ${panel} single active`, await page.locator('.bottom-nav .nav-item.active').count() === 1);
      if (panelMap[panel]) {const locator = page.locator(panelMap[panel]);check(`${panel} panel open`, await locator.evaluate(node => node.classList.contains('open') && node.getAttribute('aria-hidden') === 'false'));}
    }

    for (const mode of ['all', 'locations', 'collectibles', 'activities', 'favorites']) {
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click();await page.waitForTimeout(220);
      check(`rail ${mode} active`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`rail ${mode} single active`, await page.locator('.quick-rail .rail-button.active').count() === 1);
    }

    const returnCases=[['filter','locations','#filterPanel'],['route','collectibles','#routePanel'],['progress','activities','#progressPanel']];
    for (const [panel,mode,selector] of returnCases) {
      await page.locator(`.bottom-nav .nav-item[data-panel="${panel}"]`).click();await page.waitForTimeout(90);
      await page.locator('.bottom-nav .nav-item[data-panel="map"]').click();await page.waitForTimeout(90);
      await page.locator(`.quick-rail .rail-button[data-mode="${mode}"]`).click();await page.waitForTimeout(90);
      check(`${panel} return keeps rail ${mode} interactive`, await page.locator(`.quick-rail .rail-button[data-mode="${mode}"].active`).count() === 1);
      check(`${panel} closed panel inert`, await page.locator(selector).evaluate(node => node.hasAttribute('inert') && getComputedStyle(node).pointerEvents === 'none' && node.getAttribute('aria-hidden') === 'true'));
    }
    const navigationInteraction = await page.evaluate(() => ({rail:getComputedStyle(document.querySelector('.quick-rail')).pointerEvents,closed:[...document.querySelectorAll('#filterPanel,#routePanel,#progressPanel')].every(node=>node.hasAttribute('inert')&&getComputedStyle(node).pointerEvents==='none')}));
    check('map return leaves only rail interactive', navigationInteraction.rail !== 'none' && navigationInteraction.closed, JSON.stringify(navigationInteraction));

    if(profileIndex===0){
      check('bottom maximum width contract', navigationGeometry.bottom.width <= 431, String(navigationGeometry.bottom.width));
      check('navigation guard release contract', await page.evaluate(version => window.AtlasLiquidNavigation?.version === version, manifest.version));
    }

    await page.locator('#evidenceStudioBtn').click();await page.waitForTimeout(120);
    check('settings opens', await page.locator('#atlasSettingsOverlay.open').count() === 1);
    check('settings aria visible', await page.locator('#atlasSettingsOverlay').getAttribute('aria-hidden') === 'false');
    await page.locator('.atlas-settings-close').click();check('settings closes', await page.locator('#atlasSettingsOverlay.open').count() === 0);

    const releaseScripts = await page.evaluate(() => [...document.scripts].filter(script => /atlas-(?:bootstrap|analysis-import|liquid-nav-0934|controls-0938|ipad-nav-0940|data-guard-0939)\.js/.test(script.src)).map(script => script.src));
    const wrongScript = releaseScripts.find(url => !url.includes(`v=${manifest.version}`));
    check('release scripts use one cache version', !wrongScript, wrongScript || releaseScripts.join('\n'));
    check('bootstrap loaded once', releaseScripts.filter(url => url.includes('atlas-bootstrap.js')).length === 1, releaseScripts.join('\n'));
    check('controls loaded once', releaseScripts.filter(url => url.includes('atlas-controls-0938.js')).length === 1, releaseScripts.join('\n'));

    const registrations = await page.evaluate(async () => 'serviceWorker' in navigator ? (await navigator.serviceWorker.getRegistrations()).map(item => item.active?.scriptURL || item.installing?.scriptURL || '') : []);
    check('service worker registration count', registrations.length <= 1, registrations.join('\n'));
    check('service worker release URL', !registrations.length || registrations[0].includes(`v=${manifest.version}`), registrations.join('\n'));

    if (profile.userAgent===ipadUA) check('ipad class enabled', await page.locator('html.atlas-ipad').count() === 1);else check('ipad class not forced', await page.locator('html.atlas-ipad').count() === 0);
    check('no runtime errors', errors.length === 0, errors.join('\n'));
  } catch (error) {failed = true;errors.push(String(error?.stack || error));}

  results.push({ profile: profile.name, checks, errors });
  await context.close();
}

await browser.close();
await fs.mkdir(new URL('../data/conflict-reports/', import.meta.url), { recursive: true });
const totalChecks = results.reduce((sum, result) => sum + result.checks.length, 0);
await fs.writeFile(new URL('../data/conflict-reports/browser-matrix.json', import.meta.url), JSON.stringify({schemaVersion: 2,release: manifest.version,generatedAt: new Date().toISOString(),passed: !failed,totalChecks,profiles: results}, null, 2) + '\n');
for (const result of results) {const passed = result.checks.filter(check => check.passed).length;console.log(`${result.profile}: ${passed}/${result.checks.length} checks; errors=${result.errors.length}`);}
console.log(`Browser matrix total checks: ${totalChecks}`);
const required=Number(manifest.invariants.requiredBrowserMatrixChecks||500);
if (totalChecks !== required) {console.error(`Expected exactly ${required} independent browser checks, got ${totalChecks}`);process.exit(3);}
if (failed) process.exit(2);
