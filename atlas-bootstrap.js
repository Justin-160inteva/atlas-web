(() => {
  'use strict';

  const release = Object.freeze({
    version: '0.9.4.8',
    versionText: "ASSASSIN'S CREED SHADOWS · ALPHA 0.9.4.8",
    cacheNamespace: 'atlas-alpha-0948-pages-v1-monitor-v11-ipad-canvas-1',
    owner: 'atlas-bootstrap.js'
  });

  window.AtlasRelease = release;
  document.documentElement.dataset.atlasRelease = release.version;

  let brandObserver = null;
  let registrationPromise = null;
  const nativeRegister = 'serviceWorker' in navigator
    ? navigator.serviceWorker.register.bind(navigator.serviceWorker)
    : null;

  function stampVersion() {
    const label = document.querySelector('.brand-copy small');
    if (label && label.textContent !== release.versionText) label.textContent = release.versionText;
  }

  function ownVersionLabel() {
    stampVersion();
    const label = document.querySelector('.brand-copy small');
    if (!label || brandObserver) return;
    brandObserver = new MutationObserver(stampVersion);
    brandObserver.observe(label, { childList: true, characterData: true, subtree: true });
  }

  async function verifyManifest() {
    try {
      const response = await fetch(`release-manifest.json?v=${encodeURIComponent(release.version)}`, { cache: 'no-store' });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      const manifest = await response.json();
      if (manifest.version !== release.version || manifest.releaseOwner !== release.owner || manifest.cacheNamespace !== release.cacheNamespace) {
        console.error('[Atlas release conflict]', { bootstrap: release, manifest });
        document.documentElement.dataset.atlasReleaseConflict = '1';
      }
    } catch (error) {
      console.warn('[Atlas release manifest unavailable]', error);
    }
  }

  function getReleaseRegistration() {
    if (!nativeRegister) return Promise.resolve(null);
    if (!registrationPromise) {
      registrationPromise = nativeRegister(`sw.js?v=${encodeURIComponent(release.version)}&cache=${encodeURIComponent(release.cacheNamespace)}`, { updateViaCache: 'none' });
    }
    return registrationPromise;
  }

  function installRegistrationDelegate() {
    if (!nativeRegister) return;
    navigator.serviceWorker.register = function registerAtlasServiceWorker(url, options) {
      const target = String(url || '');
      if (/^(?:\.\/)?sw\.js(?:\?|$)/.test(target)) return getReleaseRegistration();
      return nativeRegister(url, options);
    };
  }

  async function registerServiceWorker() {
    if (!nativeRegister) return;
    try {
      const registration = await getReleaseRegistration();
      await registration.update();
      if (registration.waiting) registration.waiting.postMessage({ type: 'SKIP_WAITING' });
      navigator.serviceWorker.addEventListener('controllerchange', () => {
        const key = `atlas.controllerReload.${release.cacheNamespace}`;
        if (sessionStorage.getItem(key)) return;
        sessionStorage.setItem(key, '1');
        location.reload();
      });
    } catch (error) {
      console.warn('[Atlas service worker registration failed]', error);
    }
  }

  function init() {
    ownVersionLabel();
    verifyManifest();
    registerServiceWorker();
  }

  installRegistrationDelegate();
  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', init, { once: true })
    : init();
})();