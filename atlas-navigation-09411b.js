(() => {
  'use strict';

  const VERSION = '0.9.4.12f';
  const ICON_DESIGN = 'clean-radial-09411a';
  const root = document.documentElement;
  const rail = document.querySelector('.quick-rail');
  const bottom = document.querySelector('.bottom-nav');
  const panels = ['filterPanel', 'routePanel', 'progressPanel']
    .map(id => document.getElementById(id))
    .filter(Boolean);
  const settings = document.getElementById('evidenceStudioBtn');

  const settingsIcon = `
    <svg class="atlas-control-icon atlas-settings-icon-09411a" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.25" />
      <path d="M12 2.9v2.25M12 18.85v2.25M21.1 12h-2.25M5.15 12H2.9M18.43 5.57l-1.59 1.59M7.16 16.84l-1.59 1.59M18.43 18.43l-1.59-1.59M7.16 7.16 5.57 5.57" />
    </svg>`;

  const railLiteCss = `
    html body .app-shell .quick-rail.quick-rail{
      left:max(14px,env(safe-area-inset-left,0px))!important;
      width:80px!important;
      height:384px!important;
      padding:10px 9px!important;
      display:grid!important;
      grid-template-rows:repeat(5,68px)!important;
      gap:6px!important;
      align-content:center!important;
      border:1px solid rgba(255,255,255,.16)!important;
      border-radius:27px!important;
      overflow:hidden!important;
      background:linear-gradient(155deg,rgba(255,255,255,.09),rgba(39,33,35,.78) 45%,rgba(17,16,17,.88))!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.16),0 10px 24px rgba(0,0,0,.18)!important;
      box-sizing:border-box!important;
      contain:layout paint!important;
    }
    html body .app-shell .quick-rail.quick-rail::before{display:none!important}
    html body .app-shell .quick-rail.quick-rail .rail-button{
      position:relative!important;
      width:60px!important;
      max-width:60px!important;
      height:64px!important;
      min-height:64px!important;
      margin:auto!important;
      padding:0!important;
      display:flex!important;
      flex-direction:column!important;
      align-items:center!important;
      justify-content:center!important;
      gap:5px!important;
      border:1px solid transparent!important;
      border-radius:17px!important;
      overflow:hidden!important;
      background:transparent!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
      transform:none!important;
      color:rgba(255,255,255,.58)!important;
      transition:background-color .12s ease,border-color .12s ease,color .12s ease,opacity .12s ease!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button::before{display:none!important}
    html body .app-shell .quick-rail.quick-rail .rail-button.active{
      border-color:rgba(255,255,255,.24)!important;
      background:linear-gradient(145deg,rgba(255,255,255,.24),rgba(255,237,242,.18) 54%,rgba(225,151,168,.13))!important;
      color:#f2d9df!important;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.28)!important;
      transform:none!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button :where(.rail-icon,.atlas-control-icon){
      width:24px!important;height:24px!important;color:currentColor!important;opacity:.86!important;filter:none!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button small{
      margin:0!important;font-size:10px!important;line-height:1!important;color:currentColor!important;opacity:.78!important;white-space:nowrap!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button:active{transform:scale(.97)!important}
    @media(max-width:720px){
      html body .app-shell .quick-rail.quick-rail{left:max(10px,env(safe-area-inset-left,0px))!important;width:72px!important;height:354px!important;padding:8px 7px!important;grid-template-rows:repeat(5,62px)!important;gap:6px!important;border-radius:24px!important}
      html body .app-shell .quick-rail.quick-rail .rail-button{width:56px!important;max-width:56px!important;height:58px!important;min-height:58px!important;border-radius:15px!important}
    }
  `;

  let repairFrame = 0;
  let repairCount = 0;

  function setAttributeIfChanged(node, name, value) {
    if (!node || node.getAttribute(name) === value) return false;
    node.setAttribute(name, value);
    return true;
  }

  function addAttributeIfMissing(node, name) {
    if (!node || node.hasAttribute(name)) return false;
    node.setAttribute(name, '');
    return true;
  }

  function removeAttributeIfPresent(node, name) {
    if (!node || !node.hasAttribute(name)) return false;
    node.removeAttribute(name);
    return true;
  }

  function removeInlinePropertyIfPresent(node, property) {
    if (!node || !node.style.getPropertyValue(property)) return false;
    node.style.removeProperty(property);
    return true;
  }

  function installRailLiteStyle() {
    if (document.getElementById('atlas-rail-lite-09412f')) return;
    const style = document.createElement('style');
    style.id = 'atlas-rail-lite-09412f';
    style.textContent = railLiteCss;
    document.head.appendChild(style);
    root.dataset.atlasRailDesign = VERSION;
  }

  function restoreRail() {
    if (!rail) return false;
    let changed = false;
    changed = removeAttributeIfPresent(rail, 'inert') || changed;
    changed = setAttributeIfChanged(rail, 'aria-disabled', 'false') || changed;
    changed = removeInlinePropertyIfPresent(rail, 'pointer-events') || changed;
    changed = removeInlinePropertyIfPresent(rail, 'visibility') || changed;
    changed = removeInlinePropertyIfPresent(rail, 'opacity') || changed;
    rail.querySelectorAll('button').forEach(button => {
      if (button.disabled) { button.disabled = false; changed = true; }
      changed = removeAttributeIfPresent(button, 'inert') || changed;
      changed = removeInlinePropertyIfPresent(button, 'pointer-events') || changed;
    });
    return changed;
  }

  function syncLayer(layer) {
    if (!layer) return false;
    const open = layer.classList.contains('open');
    let changed = false;
    changed = setAttributeIfChanged(layer, 'aria-hidden', open ? 'false' : 'true') || changed;
    changed = open ? removeAttributeIfPresent(layer, 'inert') || changed : addAttributeIfMissing(layer, 'inert') || changed;
    return changed;
  }

  function syncLayers() {
    let changed = false;
    panels.forEach(panel => { changed = syncLayer(panel) || changed; });
    document.querySelectorAll('.atlas-settings-overlay,.search-overlay').forEach(layer => { changed = syncLayer(layer) || changed; });
    return changed;
  }

  function installSettingsIcon() {
    if (!settings) return false;
    let changed = false;
    const icon = settings.firstElementChild;
    if (settings.children.length !== 1 || !icon?.classList.contains('atlas-settings-icon-09411a')) {
      settings.innerHTML = settingsIcon;
      changed = true;
    }
    if (!settings.classList.contains('atlas-settings-button')) {
      settings.classList.add('atlas-settings-button');
      changed = true;
    }
    changed = setAttributeIfChanged(settings, 'data-icon-design', ICON_DESIGN) || changed;
    changed = setAttributeIfChanged(settings, 'aria-label', '打开设置与数据中心') || changed;
    return changed;
  }

  function runRepair() {
    repairFrame = 0;
    repairCount += 1;
    restoreRail();
    syncLayers();
    installSettingsIcon();
    root.dataset.atlasNavigationRepairCount = String(repairCount);
  }

  function scheduleRepair() {
    if (repairFrame) return;
    repairFrame = requestAnimationFrame(runRepair);
  }

  function returnToMap() {
    panels.forEach(panel => panel.classList.remove('open'));
    document.querySelectorAll('.bottom-nav .nav-item').forEach(button => {
      button.classList.toggle('active', button.dataset.panel === 'map');
    });
    root.classList.remove('atlas-panel-open', 'atlas-nav-moving');
    scheduleRepair();
    requestAnimationFrame(() => window.AtlasLiquidNavigation?.refresh?.());
  }

  function installInteractionGuard() {
    bottom?.addEventListener('click', event => {
      const button = event.target.closest('.nav-item');
      if (!button || !bottom.contains(button)) return;
      button.dataset.panel === 'map' ? queueMicrotask(returnToMap) : scheduleRepair();
    }, true);

    panels.forEach(panel => {
      new MutationObserver(scheduleRepair).observe(panel, { attributes: true, attributeFilter: ['class'] });
    });
    document.querySelectorAll('.atlas-settings-overlay,.search-overlay').forEach(layer => {
      new MutationObserver(scheduleRepair).observe(layer, { attributes: true, attributeFilter: ['class'] });
    });
    window.addEventListener('pageshow', scheduleRepair, { passive: true });
  }

  function railNeedsRepair() {
    if (!rail) return false;
    return rail.hasAttribute('inert') || rail.getAttribute('aria-disabled') === 'true' || Boolean(rail.style.pointerEvents || rail.style.visibility || rail.style.opacity);
  }

  function audit() {
    return {
      version: VERSION,
      repairCount,
      repairScheduled: Boolean(repairFrame),
      railInteractive: !railNeedsRepair(),
      closedPanelsSafe: panels.every(panel => panel.classList.contains('open') || (panel.getAttribute('aria-hidden') === 'true' && panel.hasAttribute('inert'))),
      openLayersInteractive: [...document.querySelectorAll('.atlas-settings-overlay.open,.search-overlay.open')].every(layer => !layer.hasAttribute('inert') && layer.getAttribute('aria-hidden') === 'false'),
      settingsIconValid: Boolean(settings?.querySelector(':scope > svg.atlas-settings-icon-09411a')) && settings.children.length === 1
    };
  }

  function init() {
    installRailLiteStyle();
    installInteractionGuard();
    runRepair();
    root.dataset.atlasNavigation = VERSION;
    window.AtlasNavigationRecovery = Object.freeze({ version: VERSION, audit, restoreRail, returnToMap, scheduleRepair });
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
