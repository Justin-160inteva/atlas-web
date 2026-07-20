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
  let mapHooksInstalled = false;
  let previousCanvasWidth = 0;
  let previousCanvasHeight = 0;

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
    const scale = Math.max(0.1, Number(visual?.scale || 1));
    const rawWidth = Number(visual?.width || root.clientWidth || window.innerWidth || 1);
    const rawHeight = Number(visual?.height || root.clientHeight || window.innerHeight || 1);
    const normalizeFactor = Math.abs(scale - 1) > scaleTolerance ? scale : 1;
    const width = Math.max(1, Math.round(rawWidth * normalizeFactor));
    const height = Math.max(1, Math.round(rawHeight * normalizeFactor));
    return {
      width,
      height,
      scale,
      left: 0,
      top: 0,
      orientation: orientationName(width, height),
      profile: profileName(width, height)
    };
  }

  function viewportFitScale(metrics = readViewport()) {
    return Math.min(metrics.width / 4096, metrics.height / 4096) * 1.1;
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
    root.classList.toggle('atlas-phone', ['compact-phone', 'phone', 'large-phone'].includes(metrics.profile));
    root.classList.toggle('atlas-tablet', ['tablet', 'large-tablet'].includes(metrics.profile));
    root.dispatchEvent(new CustomEvent('atlas:viewportchange', {
      detail: { ...metrics, reason }
    }));
  }

  function installMapViewportHooks() {
    if (mapHooksInstalled) return true;
    if (
      typeof window.fitMap !== 'function' ||
      typeof window.resize !== 'function' ||
      typeof window.zoomAt !== 'function' ||
      typeof window.focusLocation !== 'function' ||
      typeof window.focusRoute !== 'function' ||
      typeof window.buildMarkers !== 'function' ||
      typeof window.updateZoomLabel !== 'function' ||
      typeof state === 'undefined' ||
      typeof canvas === 'undefined' ||
      typeof ctx === 'undefined'
    ) {
      window.setTimeout(installMapViewportHooks, 30);
      return false;
    }

    const originalResize = window.resize;

    function viewportUpdateZoomLabel() {
      const label = document.getElementById('zoomLabel');
      if (!label) return;
      const fit = viewportFitScale();
      const ratio = fit > 0 ? state.scale / fit : 1;
      label.textContent = `×${ratio.toFixed(ratio < 10 ? 2 : 0)}`;
    }

    function viewportFitMap() {
      const metrics = readViewport();
      const nextScale = viewportFitScale(metrics);
      state.scale = nextScale;
      state.offsetX = (metrics.width - 4096 * nextScale) / 2;
      state.offsetY = (metrics.height - 4096 * nextScale) / 2;
      viewportUpdateZoomLabel();
    }

    function viewportResize() {
      const metrics = readViewport();
      const dpr = Math.min(window.devicePixelRatio || 1, 2.5);
      const hadViewport = previousCanvasWidth > 0 && previousCanvasHeight > 0 && Number.isFinite(state.scale) && state.scale > 0;
      const worldCenterX = hadViewport ? (previousCanvasWidth / 2 - state.offsetX) / state.scale : 0;
      const worldCenterY = hadViewport ? (previousCanvasHeight / 2 - state.offsetY) / state.scale : 0;
      canvas.width = Math.max(1, Math.floor(metrics.width * dpr));
      canvas.height = Math.max(1, Math.floor(metrics.height * dpr));
      canvas.style.width = `${metrics.width}px`;
      canvas.style.height = `${metrics.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      if (!hadViewport || (!state.offsetX && !state.offsetY)) {
        viewportFitMap();
      } else {
        state.scale = Math.max(state.scale, viewportFitScale(metrics) * 0.28);
        state.offsetX = metrics.width / 2 - worldCenterX * state.scale;
        state.offsetY = metrics.height / 2 - worldCenterY * state.scale;
        viewportUpdateZoomLabel();
      }
      previousCanvasWidth = metrics.width;
      previousCanvasHeight = metrics.height;
      if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
    }

    function viewportZoomAt(factor, x, y) {
      const metrics = readViewport();
      const pointX = Number.isFinite(x) ? x : metrics.width / 2;
      const pointY = Number.isFinite(y) ? y : metrics.height / 2;
      const oldScale = state.scale;
      const minimum = viewportFitScale(metrics) * 0.28;
      const nextScale = Math.max(minimum, Math.min(state.maxScale, oldScale * factor));
      const mapX = (pointX - state.offsetX) / oldScale;
      const mapY = (pointY - state.offsetY) / oldScale;
      state.scale = nextScale;
      state.offsetX = pointX - mapX * nextScale;
      state.offsetY = pointY - mapY * nextScale;
      viewportUpdateZoomLabel();
      if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
    }

    function viewportFocusLocation(location, scale = 0.85) {
      if (!location) return;
      const metrics = readViewport();
      state.scale = Math.max(state.scale, scale);
      const point = window.mapToScreen(location);
      state.offsetX += metrics.width / 2 - point.x;
      state.offsetY += metrics.height / 2 - point.y;
      window.selectLocation(location);
    }

    function viewportFocusRoute() {
      if (!state.route.length) {
        if (typeof window.toast === 'function') window.toast('路线还是空的');
        return;
      }
      const metrics = readViewport();
      const xs = state.route.map(item => item.atlas_x * 4096);
      const ys = state.route.map(item => item.atlas_y * 4096);
      const minX = Math.min(...xs);
      const maxX = Math.max(...xs);
      const minY = Math.min(...ys);
      const maxY = Math.max(...ys);
      const padding = metrics.profile.includes('phone') ? 76 : 120;
      const width = Math.max(260, maxX - minX);
      const height = Math.max(260, maxY - minY);
      state.scale = Math.max(
        viewportFitScale(metrics) * 0.28,
        Math.min(state.maxScale, Math.min((metrics.width - padding * 2) / width, (metrics.height - padding * 2) / height))
      );
      state.offsetX = metrics.width / 2 - ((minX + maxX) / 2) * state.scale;
      state.offsetY = metrics.height / 2 - ((minY + maxY) / 2) * state.scale;
      viewportUpdateZoomLabel();
      if (typeof window.closePanels === 'function') window.closePanels();
      if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
    }

    function viewportBuildMarkers(list) {
      const metrics = readViewport();
      const output = [];
      for (const location of list) {
        const point = window.mapToScreen(location);
        if (point.x < -40 || point.y < -40 || point.x > metrics.width + 40 || point.y > metrics.height + 40) continue;
        output.push({ x: point.x, y: point.y, count: 1, items: [location] });
      }
      return output;
    }

    window.removeEventListener('resize', originalResize);
    window.resize = viewportResize;
    window.fitMap = viewportFitMap;
    window.zoomAt = viewportZoomAt;
    window.focusLocation = viewportFocusLocation;
    window.focusRoute = viewportFocusRoute;
    window.buildMarkers = viewportBuildMarkers;
    window.updateZoomLabel = viewportUpdateZoomLabel;
    window.addEventListener('resize', viewportResize, { passive: true });
    const focusRouteButton = document.getElementById('focusRoute');
    if (focusRouteButton) focusRouteButton.onclick = viewportFocusRoute;
    mapHooksInstalled = true;
    root.dataset.atlasMapViewportHooks = 'true';
    viewportResize();
    return true;
  }

  function requestAppResize(refit) {
    installMapViewportHooks();
    window.dispatchEvent(new Event('resize'));
    if (refit && typeof window.fitMap === 'function') {
      requestAnimationFrame(() => {
        window.fitMap();
        if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
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
      scheduleViewportUpdate('page-scale-reset', true, 3);
    });
    return true;
  }

  function applyViewport(reason, refit = false) {
    const metrics = readViewport();
    const dimensionsChanged = Math.abs(metrics.width - lastWidth) > dimensionTolerance || Math.abs(metrics.height - lastHeight) > dimensionTolerance;
    const orientationChanged = Boolean(lastOrientation && metrics.orientation !== lastOrientation);
    const profileChanged = Boolean(lastProfile && metrics.profile !== lastProfile);
    const shouldRefit = refit || orientationChanged || profileChanged;
    writeViewportMetrics(metrics, reason);
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

  function stabilizeViewport(reason, forceRefit = true, resetInteraction = false) {
    const scaleWasReset = normalizePageScale(true);
    if (resetInteraction) interacted = false;
    scheduleViewportUpdate(reason, forceRefit || scaleWasReset, 4);
    window.setTimeout(() => scheduleViewportUpdate(`${reason}-late`, (forceRefit || scaleWasReset) && !interacted, 2), 420);
  }

  if (viewport) viewport.setAttribute('content', canonicalViewport);

  document.addEventListener('dblclick', preventNativeZoom, { capture: true, passive: false });
  ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
    document.addEventListener(type, preventNativeZoom, { capture: true, passive: false });
  });
  document.addEventListener('touchstart', () => { interacted = true; }, { capture: true, passive: true });
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
      left: 0;
      top: 0;
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
    :root[data-atlas-viewport-profile="compact-phone"] .top-bar {
      left: 8px;
      right: 8px;
      height: 56px;
      gap: 7px;
      padding: 6px 7px;
      border-radius: 18px;
    }
    :root[data-atlas-viewport-profile="compact-phone"] .brand-mark { width: 38px; height: 38px; }
    :root[data-atlas-viewport-profile="compact-phone"] .search-trigger { height: 40px; padding: 0 10px; font-size: 12px; }
    :root[data-atlas-viewport-profile="compact-phone"] .quick-rail { left: 8px; top: 76px; width: 56px; padding: 6px; }
    :root[data-atlas-viewport-profile="compact-phone"] .rail-button { height: 50px; }
    :root[data-atlas-viewport-profile="compact-phone"] .map-controls { right: 8px; top: 78px; }
    :root[data-atlas-viewport-profile="compact-phone"] .map-controls button { width: 40px; height: 38px; }
    :root[data-atlas-viewport-profile="compact-phone"] .status-pill { left: 72px; bottom: calc(var(--safe-bottom) + 66px); }
    :root[data-atlas-viewport-profile="compact-phone"] .bottom-nav { width: calc(100% - 12px); height: 58px; bottom: max(6px, env(safe-area-inset-bottom)); }
    :root[data-atlas-viewport-orientation="landscape"].atlas-phone .top-bar { top: max(6px, env(safe-area-inset-top)); height: 52px; }
    :root[data-atlas-viewport-orientation="landscape"].atlas-phone .quick-rail { top: 66px; }
    :root[data-atlas-viewport-orientation="landscape"].atlas-phone .map-controls { top: 68px; }
    :root[data-atlas-viewport-orientation="landscape"].atlas-phone .bottom-nav { height: 56px; }
    :root[data-atlas-viewport-orientation="landscape"].atlas-phone .status-pill { bottom: calc(var(--safe-bottom) + 62px); }
    :root[data-atlas-viewport-profile="tablet"] .top-bar,
    :root[data-atlas-viewport-profile="large-tablet"] .top-bar { left: 14px; right: 14px; }
    :root[data-atlas-viewport-profile="tablet"] .quick-rail,
    :root[data-atlas-viewport-profile="large-tablet"] .quick-rail { left: 14px; }
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
    window.setTimeout(() => stabilizeViewport('orientation-change', true, true), 80);
  }, { passive: true });
  window.addEventListener('pageshow', event => stabilizeViewport(event.persisted ? 'bfcache-restore' : 'page-show', true, true), { passive: true });
  window.addEventListener('load', () => stabilizeViewport('window-load', true, true), { once: true, passive: true });
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') stabilizeViewport('visibility-restore', false, false);
  });

  window.AtlasViewport = {
    measure: readViewport,
    refresh: (reason = 'manual') => scheduleViewportUpdate(reason, false, 2),
    normalizeScale: () => normalizePageScale(true),
    profile: () => readViewport().profile,
    orientation: () => readViewport().orientation
  };
  root.dataset.atlasViewportController = window.AtlasRelease?.version || '0.9.4.9';
  installMapViewportHooks();
  stabilizeViewport('initial', true, true);
})();
