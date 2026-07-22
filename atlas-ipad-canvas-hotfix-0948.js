(() => {
  'use strict';

  const root = document.documentElement;
  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isLargeTouch = navigator.maxTouchPoints > 1 && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isLargeTouch) return;

  if (
    typeof canvas === 'undefined' ||
    typeof ctx === 'undefined' ||
    typeof state === 'undefined' ||
    typeof visibleLocations !== 'function' ||
    typeof buildMarkers !== 'function' ||
    typeof drawMarker !== 'function' ||
    typeof drawRoute !== 'function'
  ) return;

  const WORLD_SIZE = 4096;
  const MAX_CANVAS_PIXELS = 3_100_000;
  const MAX_DPR = 1.45;
  const FIXED_MARKER_RELATIVE = 1;
  const shell = document.querySelector('.app-shell');
  const viewportMeta = document.querySelector('meta[name="viewport"]');
  const originalBuildMarkers = buildMarkers;
  const originalDrawMarker = drawMarker;
  const originalDrawRoute = drawRoute;
  const legacyResize = typeof resize === 'function' ? resize : null;

  const perf = {
    version: '0.9.4.8-ipad-canvas-3',
    interacting: false,
    dpr: 1,
    cssWidth: 0,
    cssHeight: 0,
    frameRaf: 0,
    resizeTimer: 0,
    resizeGeneration: 0,
    renderedMarkers: 0,
    visiblePoints: 0,
    physicalClears: 0
  };

  function metrics() {
    const rect = shell?.getBoundingClientRect?.();
    const doc = document.documentElement;
    const width = Math.max(1, Math.round(rect?.width || doc.clientWidth || window.innerWidth || 1));
    const height = Math.max(1, Math.round(rect?.height || doc.clientHeight || window.innerHeight || 1));
    return { width, height };
  }

  function stableFitScale(viewport = metrics()) {
    return Math.min(viewport.width / WORLD_SIZE, viewport.height / WORLD_SIZE) * 1.1;
  }

  function stableMinScale(viewport = metrics()) {
    return stableFitScale(viewport) * 0.28;
  }

  function calculateDpr(viewport) {
    const area = Math.max(1, viewport.width * viewport.height);
    const pixelLimited = Math.sqrt(MAX_CANVAS_PIXELS / area);
    const hardware = window.devicePixelRatio || 1;
    return Math.round(Math.max(1, Math.min(hardware, pixelLimited, MAX_DPR)) * 20) / 20;
  }

  function updateZoomLabelStable() {
    const label = document.getElementById('zoomLabel');
    if (!label) return;
    const ratio = state.scale / stableFitScale();
    label.textContent = `×${ratio.toFixed(ratio < 10 ? 2 : 0)}`;
  }

  fitMap = function fitMapStable() {
    const viewport = metrics();
    const scale = stableFitScale(viewport);
    state.scale = scale;
    state.offsetX = (viewport.width - WORLD_SIZE * scale) / 2;
    state.offsetY = (viewport.height - WORLD_SIZE * scale) / 2;
    updateZoomLabelStable();
  };

  zoomAt = function zoomAtStable(factor, x, y) {
    const viewport = metrics();
    const anchorX = Number.isFinite(x) ? x : viewport.width / 2;
    const anchorY = Number.isFinite(y) ? y : viewport.height / 2;
    const oldScale = Math.max(0.0001, state.scale);
    const nextScale = Math.max(stableMinScale(viewport), Math.min(state.maxScale, oldScale * factor));
    const mapX = (anchorX - state.offsetX) / oldScale;
    const mapY = (anchorY - state.offsetY) / oldScale;
    state.scale = nextScale;
    state.offsetX = anchorX - mapX * nextScale;
    state.offsetY = anchorY - mapY * nextScale;
    updateZoomLabelStable();
    scheduleDraw();
  };

  function applyCanvasSize(refit = false) {
    const viewport = metrics();
    const dpr = calculateDpr(viewport);
    const targetWidth = Math.max(1, Math.floor(viewport.width * dpr));
    const targetHeight = Math.max(1, Math.floor(viewport.height * dpr));
    const changed =
      canvas.width !== targetWidth ||
      canvas.height !== targetHeight ||
      perf.cssWidth !== viewport.width ||
      perf.cssHeight !== viewport.height ||
      Math.abs(perf.dpr - dpr) > 0.001;

    if (!changed && !refit) return false;

    const hadViewport = perf.cssWidth > 0 && perf.cssHeight > 0 && Number.isFinite(state.scale) && state.scale > 0;
    const worldCenterX = hadViewport ? (perf.cssWidth / 2 - state.offsetX) / state.scale : WORLD_SIZE / 2;
    const worldCenterY = hadViewport ? (perf.cssHeight / 2 - state.offsetY) / state.scale : WORLD_SIZE / 2;

    canvas.width = targetWidth;
    canvas.height = targetHeight;
    canvas.style.width = `${viewport.width}px`;
    canvas.style.height = `${viewport.height}px`;
    perf.cssWidth = viewport.width;
    perf.cssHeight = viewport.height;
    perf.dpr = dpr;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    if (!hadViewport || refit || !Number.isFinite(state.offsetX) || !Number.isFinite(state.offsetY)) {
      fitMap();
    } else {
      state.scale = Math.max(state.scale, stableMinScale(viewport));
      state.offsetX = viewport.width / 2 - worldCenterX * state.scale;
      state.offsetY = viewport.height / 2 - worldCenterY * state.scale;
      updateZoomLabelStable();
    }

    state.framePending = false;
    scheduleDraw();
    return true;
  }

  function settleResize(refit = false) {
    const generation = ++perf.resizeGeneration;
    clearTimeout(perf.resizeTimer);
    let previous = null;
    let stableSamples = 0;
    let samples = 0;

    const sample = () => {
      if (generation !== perf.resizeGeneration) return;
      const current = metrics();
      samples += 1;
      if (previous && Math.abs(current.width - previous.width) <= 1 && Math.abs(current.height - previous.height) <= 1) {
        stableSamples += 1;
      } else {
        stableSamples = 0;
      }
      previous = current;
      if (stableSamples >= 2 || samples >= 8) {
        applyCanvasSize(refit);
        return;
      }
      perf.resizeTimer = window.setTimeout(sample, 48);
    };

    requestAnimationFrame(sample);
  }

  resize = function resizeStable() {
    settleResize(false);
  };

  function setInteracting(value) {
    perf.interacting = value;
    root.classList.toggle('atlas-ipad-canvas-interacting', value);
    root.classList.toggle('atlas-interacting', value);
    if (!value) scheduleDraw();
  }

  function physicalClear() {
    ctx.save();
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.globalAlpha = 1;
    ctx.globalCompositeOperation = 'copy';
    ctx.fillStyle = '#070707';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.restore();
    ctx.setTransform(perf.dpr, 0, 0, perf.dpr, 0, 0);
    perf.physicalClears += 1;
  }

  draw = function drawStableFixedMarkerSize() {
    physicalClear();

    if (state.imageReady) {
      ctx.save();
      ctx.globalAlpha = 0.92;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = perf.interacting ? 'low' : 'high';
      ctx.drawImage(state.image, state.offsetX, state.offsetY, WORLD_SIZE * state.scale, WORLD_SIZE * state.scale);
      ctx.restore();
    }

    originalDrawRoute();
    const list = visibleLocations();
    state.markers = originalBuildMarkers(list);
    for (const marker of state.markers) originalDrawMarker(marker, FIXED_MARKER_RELATIVE);

    perf.visiblePoints = state.markers.length;
    perf.renderedMarkers = state.markers.length;
    const count = document.getElementById('visibleCount');
    if (count) count.textContent = String(list.length);
  };

  scheduleDraw = function scheduleDrawUnlocked() {
    if (state.framePending || document.hidden) return;
    state.framePending = true;
    perf.frameRaf = requestAnimationFrame(() => {
      state.framePending = false;
      draw();
    });
  };

  const endInteraction = () => setInteracting(false);
  canvas.addEventListener('pointerdown', () => setInteracting(true), { capture: true, passive: true });
  canvas.addEventListener('pointerup', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('pointercancel', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('touchend', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('wheel', () => setInteracting(true), { capture: true, passive: true });

  if (legacyResize) removeEventListener('resize', legacyResize);
  addEventListener('resize', () => settleResize(false), { passive: true });
  addEventListener('orientationchange', () => settleResize(true), { passive: true });
  window.visualViewport?.addEventListener('resize', () => {
    if ((window.visualViewport?.scale || 1) > 1.01) return;
    settleResize(false);
  }, { passive: true });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      cancelAnimationFrame(perf.frameRaf);
      state.framePending = false;
    } else {
      setInteracting(false);
      settleResize(false);
    }
  }, { passive: true });

  addEventListener('pageshow', event => {
    setInteracting(false);
    settleResize(Boolean(event.persisted));
  }, { passive: true });

  const canonicalViewport = 'width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no,interactive-widget=resizes-content';
  if (viewportMeta && viewportMeta.getAttribute('content') !== canonicalViewport) viewportMeta.setAttribute('content', canonicalViewport);

  const zoomInButton = document.getElementById('zoomIn');
  const zoomOutButton = document.getElementById('zoomOut');
  if (zoomInButton) zoomInButton.onclick = () => zoomAt(1.25);
  if (zoomOutButton) zoomOutButton.onclick = () => zoomAt(0.8);
  ['resetView', 'locateBtn', 'brandBtn'].forEach(id => {
    const button = document.getElementById(id);
    if (button) button.onclick = () => {
      fitMap();
      scheduleDraw();
    };
  });

  root.classList.add('atlas-ipad-canvas-hotfix');
  root.dataset.atlasIpadCanvasHotfix = perf.version;
  window.AtlasIpadCanvasHotfix = Object.freeze({
    version: perf.version,
    audit: () => ({
      version: perf.version,
      active: root.classList.contains('atlas-ipad-canvas-hotfix'),
      interacting: perf.interacting,
      width: perf.cssWidth,
      height: perf.cssHeight,
      backingWidth: canvas.width,
      backingHeight: canvas.height,
      dpr: perf.dpr,
      visiblePoints: perf.visiblePoints,
      renderedMarkers: perf.renderedMarkers,
      physicalClears: perf.physicalClears,
      markerRenderer: 'app.js-original-fixed-screen-size',
      markerAggregation: false,
      markerRelative: FIXED_MARKER_RELATIVE,
      frameLimiter: false
    })
  });

  applyCanvasSize(true);
  window.setTimeout(() => applyCanvasSize(false), 420);
  window.setTimeout(() => applyCanvasSize(false), 900);
  scheduleDraw();
})();
