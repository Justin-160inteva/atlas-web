(() => {
  'use strict';

  const VERSION = '0.9.4.12i';
  const ICON_DESIGN = 'clean-radial-09411a';
  const root = document.documentElement;
  const rail = document.querySelector('.quick-rail');
  const panels = ['filterPanel', 'routePanel', 'progressPanel']
    .map(id => document.getElementById(id))
    .filter(Boolean);
  const settings = document.getElementById('evidenceStudioBtn');

  const settingsIcon = `
    <svg class="atlas-control-icon atlas-settings-icon-09411a" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.25" />
      <path d="M12 2.9v2.25M12 18.85v2.25M21.1 12h-2.25M5.15 12H2.9M18.43 5.57l-1.59 1.59M7.16 16.84l-1.59 1.59M18.43 18.43l-1.59-1.59M7.16 7.16 5.57 5.57" />
    </svg>`;

  const navigationCss = `
    :root{
      --atlas-nav-medium-size:88px;
      --atlas-nav-surface:linear-gradient(180deg,rgba(47,41,43,.88),rgba(24,22,23,.9));
      --atlas-nav-border:rgba(255,255,255,.13);
      --atlas-nav-active:rgba(248,248,249,.96);
      --atlas-nav-muted:rgba(220,220,223,.56);
    }

    html body .app-shell .quick-rail.quick-rail,
    html.atlas-ipad body .app-shell .quick-rail.quick-rail,
    html.atlas-ipad-ultra body .app-shell .quick-rail.quick-rail{
      left:max(14px,env(safe-area-inset-left,0px))!important;
      right:auto!important;
      top:50%!important;
      bottom:auto!important;
      width:var(--atlas-nav-medium-size)!important;
      height:auto!important;
      min-height:0!important;
      padding:8px!important;
      display:flex!important;
      flex-direction:column!important;
      gap:4px!important;
      border:1px solid var(--atlas-nav-border)!important;
      border-radius:26px!important;
      overflow:hidden!important;
      background:var(--atlas-nav-surface)!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
      transform:translateY(-50%)!important;
      translate:none!important;
      contain:layout paint!important;
      isolation:isolate!important;
    }

    html body .app-shell .quick-rail.quick-rail::before,
    html body .app-shell .quick-rail.quick-rail::after,
    html body .app-shell .quick-rail.quick-rail .rail-button::before,
    html body .app-shell .quick-rail.quick-rail .rail-button::after{
      display:none!important;
      content:none!important;
    }

    html body .app-shell .quick-rail.quick-rail .rail-button{
      flex:0 0 68px!important;
      width:72px!important;
      height:68px!important;
      min-height:68px!important;
      margin:0!important;
      padding:0!important;
      display:flex!important;
      flex-direction:column!important;
      align-items:center!important;
      justify-content:center!important;
      gap:5px!important;
      border:0!important;
      border-radius:18px!important;
      overflow:hidden!important;
      background:transparent!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
      transform:none!important;
      translate:none!important;
      color:var(--atlas-nav-muted)!important;
      opacity:1!important;
      transition:none!important;
      contain:layout paint!important;
    }

    html body .app-shell .quick-rail.quick-rail .rail-button.active{
      border:0!important;
      background:transparent!important;
      color:var(--atlas-nav-active)!important;
      box-shadow:none!important;
      transform:none!important;
      translate:none!important;
    }

    html body .app-shell .quick-rail.quick-rail .rail-button :where(.rail-icon,.atlas-control-icon){
      width:25px!important;
      height:25px!important;
      color:currentColor!important;
      opacity:.92!important;
      filter:none!important;
    }

    html body .app-shell .quick-rail.quick-rail .rail-button small{
      margin:0!important;
      font-size:10px!important;
      line-height:1!important;
      color:currentColor!important;
      opacity:.84!important;
      white-space:nowrap!important;
    }

    html body .app-shell .bottom-nav.bottom-nav,
    html.atlas-ipad body .app-shell .bottom-nav.bottom-nav,
    html.atlas-ipad-ultra body .app-shell .bottom-nav.bottom-nav{
      left:0!important;
      right:0!important;
      bottom:max(8px,env(safe-area-inset-bottom,0px))!important;
      width:min(520px,calc(100% - 24px))!important;
      height:var(--atlas-nav-medium-size)!important;
      margin-left:auto!important;
      margin-right:auto!important;
      padding:8px!important;
      display:grid!important;
      grid-template-columns:repeat(5,minmax(0,1fr))!important;
      gap:0!important;
      border:1px solid var(--atlas-nav-border)!important;
      border-radius:26px!important;
      overflow:hidden!important;
      background:var(--atlas-nav-surface)!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
      transform:none!important;
      translate:none!important;
      contain:layout paint!important;
      isolation:isolate!important;
      box-sizing:border-box!important;
    }

    html body .app-shell .bottom-nav.bottom-nav::before,
    html body .app-shell .bottom-nav.bottom-nav::after,
    html body .app-shell .bottom-nav.bottom-nav .nav-item::before,
    html body .app-shell .bottom-nav.bottom-nav .nav-item::after{
      display:none!important;
      content:none!important;
    }

    html body .app-shell .bottom-nav.bottom-nav .nav-item{
      min-width:0!important;
      width:100%!important;
      height:72px!important;
      margin:0!important;
      padding:0!important;
      border:0!important;
      border-radius:18px!important;
      overflow:hidden!important;
      background:transparent!important;
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
      transform:none!important;
      translate:none!important;
      color:var(--atlas-nav-muted)!important;
      opacity:1!important;
      transition:none!important;
      contain:layout paint!important;
    }

    html body .app-shell .bottom-nav.bottom-nav .nav-item.active{
      border:0!important;
      background:transparent!important;
      color:var(--atlas-nav-active)!important;
      box-shadow:none!important;
      transform:none!important;
      translate:none!important;
    }

    html body .app-shell .bottom-nav.bottom-nav .nav-item :where(.atlas-control-icon,span){
      color:currentColor!important;
      filter:none!important;
    }

    html body .app-shell .bottom-nav.bottom-nav .nav-item small{
      color:currentColor!important;
      opacity:.84!important;
    }

    html.atlas-ipad body :where(.top-bar,.search-trigger,.icon-button,.profile-button,.status-pill,.quick-rail,.bottom-nav),
    html.atlas-ipad-ultra body :where(.top-bar,.search-trigger,.icon-button,.profile-button,.status-pill,.quick-rail,.bottom-nav){
      -webkit-backdrop-filter:none!important;
      backdrop-filter:none!important;
      box-shadow:none!important;
    }

    html.atlas-ipad body .vignette,
    html.atlas-ipad-ultra body .vignette{display:none!important}

    @media(max-width:720px){
      :root{--atlas-nav-medium-size:80px}
      html body .app-shell .quick-rail.quick-rail{
        left:max(10px,env(safe-area-inset-left,0px))!important;
        width:var(--atlas-nav-medium-size)!important;
        padding:7px!important;
        border-radius:23px!important;
      }
      html body .app-shell .quick-rail.quick-rail .rail-button{
        flex-basis:64px!important;
        width:66px!important;
        height:64px!important;
        min-height:64px!important;
      }
      html body .app-shell .bottom-nav.bottom-nav{
        width:calc(100% - 20px)!important;
        height:var(--atlas-nav-medium-size)!important;
        padding:7px!important;
        border-radius:23px!important;
      }
      html body .app-shell .bottom-nav.bottom-nav .nav-item{height:66px!important}
    }
  `;

  let repairFrame = 0;

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

  function installNavigationStyle() {
    document.getElementById('atlas-navigation-lite-09412g')?.remove();
    document.getElementById('atlas-navigation-lite-09412h')?.remove();
    if (document.getElementById('atlas-navigation-lite-09412i')) return;
    const style = document.createElement('style');
    style.id = 'atlas-navigation-lite-09412i';
    style.textContent = navigationCss;
    document.head.appendChild(style);
  }

  function restoreRail() {
    if (!rail) return false;
    let changed = false;
    changed = removeAttributeIfPresent(rail, 'inert') || changed;
    changed = setAttributeIfChanged(rail, 'aria-disabled', 'false') || changed;
    if (rail.style.pointerEvents) { rail.style.removeProperty('pointer-events'); changed = true; }
    if (rail.style.visibility) { rail.style.removeProperty('visibility'); changed = true; }
    if (rail.style.opacity) { rail.style.removeProperty('opacity'); changed = true; }
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
    panels.forEach(syncLayer);
    document.querySelectorAll('.atlas-settings-overlay,.search-overlay').forEach(syncLayer);
  }

  function installSettingsIcon() {
    if (!settings) return;
    const icon = settings.firstElementChild;
    if (settings.children.length !== 1 || !icon?.classList.contains('atlas-settings-icon-09411a')) settings.innerHTML = settingsIcon;
    settings.classList.add('atlas-settings-button');
    setAttributeIfChanged(settings, 'data-icon-design', ICON_DESIGN);
    setAttributeIfChanged(settings, 'aria-label', '打开设置与数据中心');
  }

  function runRepair() {
    repairFrame = 0;
    restoreRail();
    syncLayers();
    installSettingsIcon();
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
  }

  function installInteractionHandlers() {
    document.addEventListener('click', event => {
      const navButton = event.target.closest('.bottom-nav .nav-item');
      if (navButton?.dataset.panel === 'map') queueMicrotask(returnToMap);
      else if (navButton || event.target.closest('.close-panel,.close-route,.close-progress,#closeSearch,#closeEvidenceStudio,#searchTrigger,#evidenceStudioBtn')) queueMicrotask(scheduleRepair);
    }, true);
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape' || ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k')) queueMicrotask(scheduleRepair);
    }, { passive: true });
    window.addEventListener('pageshow', scheduleRepair, { passive: true });
  }

  function init() {
    installNavigationStyle();
    installInteractionHandlers();
    runRepair();
    root.dataset.atlasNavigation = VERSION;
    window.AtlasNavigationRecovery = Object.freeze({ version: VERSION, restoreRail, returnToMap, scheduleRepair });
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
