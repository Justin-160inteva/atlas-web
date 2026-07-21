(() => {
  'use strict';

  const VERSION = '0.9.4.11b';
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
      <circle cx="12" cy="12" r="7.05" opacity=".34" />
    </svg>`;

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
    restoreRail();
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
    return {
      version: VERSION,
      repairCount,
      repairScheduled: Boolean(repairFrame),
      railInteractive: !railNeedsRepair(),
      closedPanelsSafe,
      settingsIconValid: Boolean(settings?.querySelector(':scope > svg.atlas-settings-icon-09411a')) && settings.children.length === 1
    };
  }

  function init() {
    installInteractionGuard();
    runRepair();
    root.dataset.atlasNavigation = VERSION;
    window.AtlasNavigationRecovery = Object.freeze({ version: VERSION, audit, restoreRail, returnToMap, scheduleRepair });
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
