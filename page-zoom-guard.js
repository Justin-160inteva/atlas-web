(() => {
  'use strict';

  const root = document.documentElement;
  const viewport = document.querySelector('meta[name="viewport"]');
  const visual = window.visualViewport;
  const canonicalViewport = 'width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no,interactive-widget=resizes-content';
  const scaleTolerance = 0.015;
  const dimensionTolerance = 2;
  let lastWidth = 0;
  let lastHeight = 0;
  let lastOrientation = '';
  let lastProfile = '';
  let frame = 0;
  let settleTimer = 0;
  let interacted = false;
  let resettingScale = false;

  function preventNativeZoom(event) {
    if (event.cancelable) event.preventDefault();
  }

  function orientationName(width, height) {
    return width >= height ? 'landscape' : 'portrait';
  }

  function profileName(width, height) {
    const shortSide = Math.min(width, height);
    const longSide = Math.max(width, height);
    if (shortSide <= 360) return 'compact-phone';
    if (shortSide < 600) return longSide >= 844 ? 'large-phone' : 'phone';
    if (shortSide < 900) return 'tablet';
    if (shortSide < 1180 && navigator.maxTouchPoints > 0) return 'large-tablet';
    return 'desktop';
  }

  function readViewport() {
    const scale = Number(visual?.scale || 1);
    const width = Math.max(1, Math.round(visual?.width || root.clientWidth || window.innerWidth));
    const height = Math.max(1, Math.round(visual?.height || root.clientHeight || window.innerHeight));
    return {
      width,
      height,
      scale,
      left: Math.round(visual?.offsetLeft || 0),
      top: Math.round(visual?.offsetTop || 0),
      orientation: orientationName(width, height),
      profile: profileName(width, height)
    };
  }

  function writeViewportMetrics(metrics, reason) {
    root.style.setProperty('--atlas-viewport-width', `${metrics.width}px`);
    root.style.setProperty('--atlas-viewport-height', `${metrics.height}px`);
    root.style.setProperty('--atlas-viewport-left', `${metrics.left}px`);
    root.style.setProperty('--atlas-viewport-top', `${metrics.top}px`);
    root.style.setProperty('--atlas-page-scale', String(metrics.scale));
    root.dataset.atlasViewportProfile = metrics.profile;
    root.dataset.atlasViewportOrientation = metrics.orientation;
    root.dataset.atlasViewportReady = 'true';
    root.classList.toggle('atlas-compact-phone', metrics.profile === 'compact-phone');
    root.classList.toggle('atlas-phone', metrics.profile === 'phone' || metrics.profile === 'large-phone' || metrics.profile === 'compact-phone');
    root.classList.toggle('atlas-tablet', metrics.profile === 'tablet' || metrics.profile === 'large-tablet');
    root.dispatchEvent(new CustomEvent('atlas:viewportchange', {
      detail: { ...metrics, reason }
    }));
  }

  function requestAppResize(refit) {
    window.dispatchEvent(new Event('resize'));
    if (refit && typeof window.fitMap === 'function') {
      requestAnimationFrame(() => {
        if (!interacted || lastOrientation !== readViewport().orientation) {
          window.fitMap();
          if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
        }
      });
    }
  }

  function normalizePageScale(force = false) {
    if (!viewport) return false;
    if (viewport.getAttribute('content') !== canonicalViewport) {
      viewport.setAttribute('content', canonicalViewport);
    }
    const scale = Number(visual?.scale || 1);
    if (!force || resettingScale || Math.abs(scale - 1) <= scaleTolerance) return false;
    resettingScale = true;
    viewport.setAttribute('content', canonicalViewport.replace('initial-scale=1', 'initial-scale=1.0001'));
    requestAnimationFrame(() => {
      viewport.setAttribute('content', canonicalViewport);
      window.scrollTo(0, 0);
      resettingScale = false;
      scheduleViewportUpdate('page-scale-reset', true, 2);
    });
    return true;
  }

  function applyViewport(reason, refit = false) {
    const metrics = readViewport();
    const dimensionsChanged = Math.abs(metrics.width - lastWidth) > dimensionTolerance || Math.abs(metrics.height - lastHeight) > dimensionTolerance;
    const orientationChanged = Boolean(lastOrientation && metrics.orientation !== lastOrientation);
    const profileChanged = Boolean(lastProfile && metrics.profile !== lastProfile);
    writeViewportMetrics(metrics, reason);
    const shouldRefit = refit || orientationChanged || profileChanged;
    lastWidth = metrics.width;
    lastHeight = metrics.height;
    lastOrientation = metrics.orientation;
    lastProfile = metrics.profile;
    if (dimensionsChanged || shouldRefit) requestAppResize(shouldRefit);
  }

  function scheduleViewportUpdate(reason, refit = false, passes = 1) {
    cancelAnimationFrame(frame);
    clearTimeout(settleTimer);
    frame = requestAnimationFrame(() => {
      applyViewport(reason, refit);
      if (passes > 1) {
        settleTimer = window.setTimeout(() => scheduleViewportUpdate(`${reason}-settled`, refit && !interacted, passes - 1), 90);
      }
    });
  }

  function stabilizeStartup(reason) {
    normalizePageScale(true);
    interacted = false;
    scheduleViewportUpdate(reason, true, 4);
    window.setTimeout(() => scheduleViewportUpdate(`${reason}-late`, !interacted, 2), 420);
  }

  if (viewport) viewport.setAttribute('content', canonicalViewport);

  document.addEventListener('dblclick', preventNativeZoom, { capture: true, passive: false });
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
    document.addEventListener(type, preventNativeZoom, { capture: true, passive: false });
  });
  document.addEventListener('touchstart', event => {
    if (event.touches.length > 1) preventNativeZoom(event);
    interacted = true;
  }, { capture: true, passive: false });
  document.addEventListener('pointerdown', () => { interacted = true; }, { capture: true, passive: true });
  document.addEventListener('wheel', () => { interacted = true; }, { capture: true, passive: true });

  const style = document.createElement('style');
  style.textContent = `
    :root {
      --atlas-viewport-width: 100vw;
      --atlas-viewport-height: 100dvh;
      --atlas-viewport-left: 0px;
      --atlas-viewport-top: 0px;
    }
    html, body {
      position: fixed;
      inset: 0;
      width: 100%;
      height: 100%;
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      -webkit-text-size-adjust: 100%;
      text-size-adjust: 100%;
      overscroll-behavior: none;
    }
    .app-shell {
      position: fixed;
      left: var(--atlas-viewport-left);
      top: var(--atlas-viewport-top);
      width: var(--atlas-viewport-width);
      height: var(--atlas-viewport-height);
      min-width: 0;
      min-height: 0;
      overflow: hidden;
      transform: none !important;
      zoom: 1 !important;
    }
    input, select, textarea { font-size: max(16px, 1em); }
    button, .map-controls, .map-controls button { touch-action: manipulation; }
    #mapCanvas { touch-action: none; }
    .map-controls button { -webkit-user-select: none; user-select: none; }
  `;
  document.head.appendChild(style);

  const controls = document.querySelector('.map-controls');
  if (controls) {
    controls.addEventListener('dblclick', preventNativeZoom, { capture: true, passive: false });
    controls.querySelectorAll('button').forEach(button => {
      button.addEventListener('touchend', event => {
        if (event.cancelable) event.preventDefault();
        event.stopPropagation();
        button.click();
      }, { capture: true, passive: false });
    });
  }

  visual?.addEventListener('resize', () => {
    if (Math.abs(Number(visual.scale || 1) - 1) > scaleTolerance) normalizePageScale(true);
    scheduleViewportUpdate('visual-viewport-resize', false, 2);
  }, { passive: true });
  visual?.addEventListener('scroll', () => scheduleViewportUpdate('visual-viewport-scroll'), { passive: true });
  window.addEventListener('orientationchange', () => {
    interacted = false;
    window.setTimeout(() => stabilizeStartup('orientation-change'), 80);
  }, { passive: true });
  window.addEventListener('pageshow', event => stabilizeStartup(event.persisted ? 'bfcache-restore' : 'page-show'), { passive: true });
  window.addEventListener('load', () => stabilizeStartup('window-load'), { once: true, passive: true });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') stabilizeStartup('visibility-restore');
  });

  root.dataset.atlasViewportController = window.AtlasRelease?.version || '0.9.4.9';
  stabilizeStartup('initial');
})();
