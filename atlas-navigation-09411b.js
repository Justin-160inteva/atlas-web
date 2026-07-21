(() => {
  'use strict';

  const VERSION = '0.9.4.11b';
  const RAIL_DESIGN_VERSION = '0.9.4.12e';
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

  const railStyleText = `
    html body .app-shell .quick-rail.quick-rail{
      left:max(14px,env(safe-area-inset-left,0px))!important;
      width:82px!important;
      height:360px!important;
      padding:10px 9px!important;
      display:grid!important;
      grid-template-rows:repeat(5,60px)!important;
      gap:7px!important;
      align-content:center!important;
      border:1px solid rgba(255,255,255,.17)!important;
      border-radius:28px!important;
      overflow:hidden!important;
      background:linear-gradient(155deg,rgba(255,255,255,.11),rgba(58,46,50,.52) 38%,rgba(18,16,17,.76) 100%)!important;
      -webkit-backdrop-filter:blur(18px) saturate(138%)!important;
      backdrop-filter:blur(18px) saturate(138%)!important;
      box-shadow:inset 0 1px 0 rgba(255,255,255,.2),inset 0 -1px 0 rgba(255,255,255,.025),0 16px 34px rgba(0,0,0,.24)!important;
      box-sizing:border-box!important;
    }
    html body .app-shell .quick-rail.quick-rail::before{
      inset:2px 12px auto!important;
      height:19%!important;
      border-radius:999px!important;
      background:linear-gradient(180deg,rgba(255,255,255,.13),transparent)!important;
      opacity:.68!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button{
      position:relative!important;
      width:62px!important;
      max-width:62px!important;
      height:60px!important;
      min-height:60px!important;
      margin:0 auto!important;
      padding:0!important;
      display:flex!important;
      flex-direction:column!important;
      align-items:center!important;
      justify-content:center!important;
      gap:4px!important;
      border:0!important;
      border-radius:19px!important;
      overflow:hidden!important;
      background:transparent!important;
      box-shadow:none!important;
      transform:none!important;
      isolation:isolate!important;
      contain:layout paint style!important;
      color:rgba(255,255,255,.62)!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button::before{
      content:"";
      position:absolute;
      z-index:0;
      inset:4px 3px;
      border:1px solid transparent;
      border-radius:16px;
      background:transparent;
      -webkit-backdrop-filter:none;
      backdrop-filter:none;
      box-shadow:none;
      opacity:0;
      pointer-events:none;
      transition:opacity .17s ease,background .17s ease,border-color .17s ease;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button.active{
      border:0!important;
      background:transparent!important;
      box-shadow:none!important;
      color:#713440!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button.active::before{
      border-color:rgba(255,255,255,.28);
      background:linear-gradient(145deg,rgba(255,255,255,.3),rgba(255,242,246,.23) 48%,rgba(232,166,181,.17));
      -webkit-backdrop-filter:blur(12px) saturate(142%);
      backdrop-filter:blur(12px) saturate(142%);
      box-shadow:inset 0 1px 0 rgba(255,255,255,.4),inset 0 -1px 0 rgba(120,55,68,.055);
      opacity:1;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button > *{
      position:relative!important;
      z-index:1!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button :where(.rail-icon,.atlas-control-icon){
      width:24px!important;
      height:24px!important;
      color:currentColor!important;
      opacity:.82!important;
      filter:none!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button small{
      margin:0!important;
      font-size:10px!important;
      line-height:1!important;
      letter-spacing:.01em!important;
      color:currentColor!important;
      opacity:.72!important;
      white-space:nowrap!important;
    }
    html body .app-shell .quick-rail.quick-rail .rail-button.active :where(.rail-icon,.atlas-control-icon){opacity:.96!important}
    html body .app-shell .quick-rail.quick-rail .rail-button.active small{opacity:.9!important}
    html body .app-shell .quick-rail.quick-rail .rail-button:active{transform:scale(.965)!important}
    @media(max-width:720px){
      html body .app-shell .quick-rail.quick-rail{
        left:max(10px,env(safe-area-inset-left,0px))!important;
        width:74px!important;
        height:340px!important;
        padding:8px 7px!important;
        grid-template-rows:repeat(5,56px)!important;
        gap:6px!important;
        border-radius:25px!important;
      }
      html body .app-shell .quick-rail.quick-rail .rail-button{
        width:58px!important;
        max-width:58px!important;
        height:56px!important;
        min-height:56px!important;
        border-radius:17px!important;
      }
      html body .app-shell .quick-rail.quick-rail .rail-button::before{inset:3px;border-radius:14px}
    }
    @media(prefers-reduced-transparency:reduce){
      html body .app-shell .quick-rail.quick-rail .rail-button.active::before{
        -webkit-backdrop-filter:none;
        backdrop-filter:none;
        background:rgba(248,221,228,.9);
      }
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

  function installRailDesign() {
    let style = document.getElementById('atlas-rail-design-09412e');
    if (!style) {
      style = document.createElement('style');
      style.id = 'atlas-rail-design-09412e';
      document.head.appendChild(style);
    }
    if (style.textContent !== railStyleText) style.textContent = railStyleText;
    root.dataset.atlasRailDesign = RAIL_DESIGN_VERSION;
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
      if (button.disabled) {
        button.disabled = false;
        changed = true;
      }
      changed = removeAttributeIfPresent(button, 'inert') || changed;
      changed = removeInlinePropertyIfPresent(button, 'pointer-events') || changed;
    });
    return changed;
  }

  function closeLayerIfInactive(layer) {
    if (!layer || layer.classList.contains('open')) return false;
    let changed = false;
    changed = setAttributeIfChanged(layer, 'aria-hidden', 'true') || changed;
    changed = addAttributeIfMissing(layer, 'inert') || changed;
    return changed;
  }

  function restoreLayerIfOpen(layer) {
    if (!layer || !layer.classList.contains('open')) return false;
    let changed = false;
    changed = removeAttributeIfPresent(layer, 'inert') || changed;
    changed = setAttributeIfChanged(layer, 'aria-hidden', 'false') || changed;
    return changed;
  }

  function restoreOpenLayers() {
    let changed = false;
    document.querySelectorAll('.atlas-settings-overlay.open,.search-overlay.open')
      .forEach(layer => { changed = restoreLayerIfOpen(layer) || changed; });
    return changed;
  }

  function closeDetachedLayers() {
    let changed = false;
    panels.forEach(panel => { changed = closeLayerIfInactive(panel) || changed; });
    document.querySelectorAll('.atlas-settings-overlay:not(.open),.search-overlay:not(.open)')
      .forEach(layer => { changed = closeLayerIfInactive(layer) || changed; });
    return changed;
  }

  function installSettingsIcon() {
    if (!settings) return false;
    let changed = false;
    const icon = settings.firstElementChild;
    const correctIcon = settings.children.length === 1 && icon?.classList.contains('atlas-settings-icon-09411a');
    if (!correctIcon) {
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
    installRailDesign();
    restoreRail();
    restoreOpenLayers();
    closeDetachedLayers();
    installSettingsIcon();
    root.dataset.atlasNavigationRepairCount = String(repairCount);
  }

  function scheduleRepair() {
    if (repairFrame) return;
    repairFrame = requestAnimationFrame(runRepair);
  }

  function returnToMap() {
    panels.forEach(panel => {
      panel.classList.remove('open');
      setAttributeIfChanged(panel, 'aria-hidden', 'true');
      addAttributeIfMissing(panel, 'inert');
    });
    document.querySelectorAll('.bottom-nav .nav-item').forEach(button => {
      button.classList.toggle('active', button.dataset.panel === 'map');
    });
    root.classList.remove('atlas-panel-open', 'atlas-nav-moving');
    scheduleRepair();
    requestAnimationFrame(() => window.AtlasLiquidNavigation?.refresh?.());
  }

  function railNeedsRepair() {
    if (!rail) return false;
    return rail.hasAttribute('inert') ||
      rail.getAttribute('aria-disabled') === 'true' ||
      Boolean(rail.style.pointerEvents || rail.style.visibility || rail.style.opacity) ||
      [...rail.querySelectorAll('button')].some(button => button.disabled || button.hasAttribute('inert') || Boolean(button.style.pointerEvents));
  }

  function installInteractionGuard() {
    bottom?.addEventListener('click', event => {
      const button = event.target.closest('.nav-item');
      if (!button || !bottom.contains(button)) return;
      if (button.dataset.panel === 'map') {
        queueMicrotask(returnToMap);
      } else {
        scheduleRepair();
      }
    }, true);

    panels.forEach(panel => {
      new MutationObserver(() => {
        if (!panel.classList.contains('open')) scheduleRepair();
      }).observe(panel, { attributes: true, attributeFilter: ['class'] });
    });

    document.querySelectorAll('.atlas-settings-overlay,.search-overlay').forEach(layer => {
      new MutationObserver(scheduleRepair)
        .observe(layer, { attributes: true, attributeFilter: ['class'] });
    });

    if (rail) {
      new MutationObserver(() => {
        if (railNeedsRepair()) scheduleRepair();
      }).observe(rail, {
        attributes: true,
        subtree: true,
        attributeFilter: ['inert', 'aria-disabled', 'style', 'disabled']
      });
    }

    if (settings) {
      new MutationObserver(() => {
        const icon = settings.firstElementChild;
        if (settings.children.length !== 1 || !icon?.classList.contains('atlas-settings-icon-09411a')) scheduleRepair();
      }).observe(settings, { childList: true });
    }

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) scheduleRepair();
    }, { passive: true });
    window.addEventListener('pageshow', scheduleRepair, { passive: true });
  }

  function audit() {
    const closedPanelsSafe = panels.every(panel => panel.classList.contains('open') || (
      panel.getAttribute('aria-hidden') === 'true' && panel.hasAttribute('inert')
    ));
    const openLayersInteractive = [...document.querySelectorAll('.atlas-settings-overlay.open,.search-overlay.open')]
      .every(layer => !layer.hasAttribute('inert') && layer.getAttribute('aria-hidden') === 'false');
    return {
      version: VERSION,
      railDesignVersion: RAIL_DESIGN_VERSION,
      repairCount,
      repairScheduled: Boolean(repairFrame),
      railInteractive: !railNeedsRepair(),
      closedPanelsSafe,
      openLayersInteractive,
      settingsIconValid: Boolean(settings?.querySelector(':scope > svg.atlas-settings-icon-09411a')) && settings.children.length === 1
    };
  }

  function init() {
    installRailDesign();
    installInteractionGuard();
    runRepair();
    root.dataset.atlasNavigation = VERSION;
    window.AtlasNavigationRecovery = Object.freeze({ version: VERSION, railDesignVersion: RAIL_DESIGN_VERSION, audit, restoreRail, returnToMap, scheduleRepair });
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
