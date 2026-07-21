(() => {
  'use strict';
  const root = document.documentElement;
  const rail = document.querySelector('.quick-rail');
  const bottom = document.querySelector('.bottom-nav');
  const panels = ['filterPanel', 'routePanel', 'progressPanel'].map(id => document.getElementById(id)).filter(Boolean);
  const settings = document.getElementById('evidenceStudioBtn');

  const settingsIcon = `
    <svg class="atlas-control-icon atlas-settings-icon-09411a" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="3.25" />
      <path d="M12 2.9v2.25M12 18.85v2.25M21.1 12h-2.25M5.15 12H2.9M18.43 5.57l-1.59 1.59M7.16 16.84l-1.59 1.59M18.43 18.43l-1.59-1.59M7.16 7.16 5.57 5.57" />
      <circle cx="12" cy="12" r="7.05" opacity=".34" />
    </svg>`;

  function restoreRail() {
    if (!rail) return;
    rail.removeAttribute('inert');
    rail.setAttribute('aria-disabled', 'false');
    rail.style.removeProperty('pointer-events');
    rail.style.removeProperty('visibility');
    rail.style.removeProperty('opacity');
    rail.querySelectorAll('button').forEach(button => {
      button.disabled = false;
      button.removeAttribute('inert');
      button.style.removeProperty('pointer-events');
    });
  }

  function closeDetachedLayers() {
    panels.forEach(panel => {
      if (!panel.classList.contains('open')) {
        panel.setAttribute('aria-hidden', 'true');
        panel.setAttribute('inert', '');
      }
    });
    document.querySelectorAll('.atlas-settings-overlay:not(.open),.search-overlay:not(.open)').forEach(layer => {
      layer.setAttribute('aria-hidden', 'true');
      layer.setAttribute('inert', '');
    });
  }

  function returnToMap() {
    panels.forEach(panel => {
      panel.classList.remove('open');
      panel.setAttribute('aria-hidden', 'true');
      panel.setAttribute('inert', '');
    });
    document.querySelectorAll('.bottom-nav .nav-item').forEach(button => {
      button.classList.toggle('active', button.dataset.panel === 'map');
    });
    root.classList.remove('atlas-panel-open', 'atlas-nav-moving');
    restoreRail();
    closeDetachedLayers();
    window.AtlasLiquidNavigation?.refresh?.();
  }

  function installSettingsIcon() {
    if (!settings) return;
    if (!settings.querySelector('.atlas-settings-icon-09411a') || settings.children.length !== 1) {
      settings.innerHTML = settingsIcon;
    }
    settings.classList.add('atlas-settings-button');
    settings.dataset.iconDesign = 'clean-radial-09411a';
    settings.setAttribute('aria-label', '打开设置与数据中心');
  }

  function installInteractionGuard() {
    bottom?.addEventListener('click', event => {
      const button = event.target.closest('.nav-item');
      if (!button) return;
      if (button.dataset.panel === 'map') {
        queueMicrotask(returnToMap);
        requestAnimationFrame(returnToMap);
      } else {
        requestAnimationFrame(() => {
          restoreRail();
          closeDetachedLayers();
        });
      }
    }, true);

    panels.forEach(panel => {
      new MutationObserver(() => {
        if (!panel.classList.contains('open')) {
          panel.setAttribute('aria-hidden', 'true');
          panel.setAttribute('inert', '');
          restoreRail();
        }
      }).observe(panel, { attributes: true, attributeFilter: ['class', 'aria-hidden'] });
    });

    if (rail) {
      new MutationObserver(restoreRail).observe(rail, {
        attributes: true,
        attributeFilter: ['inert', 'aria-disabled', 'style', 'class']
      });
    }

    if (settings) {
      new MutationObserver(installSettingsIcon).observe(settings, {
        childList: true,
        attributes: true,
        attributeFilter: ['data-icon-design']
      });
    }

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) {
        restoreRail();
        closeDetachedLayers();
        installSettingsIcon();
      }
    }, { passive: true });
    window.addEventListener('pageshow', () => {
      restoreRail();
      closeDetachedLayers();
      installSettingsIcon();
    }, { passive: true });
  }

  function init() {
    installSettingsIcon();
    installInteractionGuard();
    restoreRail();
    closeDetachedLayers();
    root.dataset.atlasNavigation = '0.9.4.11a';
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();
