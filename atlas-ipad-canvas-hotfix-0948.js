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
    typeof mapToScreen !== 'function' ||
    typeof visibleLocations !== 'function'
  ) return;

  const WORLD_SIZE = 4096;
  const MAX_CANVAS_PIXELS = 3_100_000;
  const MAX_DPR = 1.45;
  const MARKER_BUDGET_IDLE = 820;
  const MARKER_BUDGET_ACTIVE = 440;
  const viewportMeta = document.querySelector('meta[name="viewport"]');
  const shell = document.querySelector('.app-shell');
  const legacyResize = typeof resize === 'function' ? resize : null;
  const detailedMarker = typeof drawMarker === 'function' ? drawMarker : null;

  const perf = {
    version: '0.9.4.8-ipad-canvas-1',
    interacting: false,
    dpr: 1,
    cssWidth: 0,
    cssHeight: 0,
    frameTimer: 0,
    frameRaf: 0,
    lastFrameAt: 0,
    settleTimer: 0,
    resizeTimer: 0,
    resizeGeneration: 0,
    renderedMarkers: 0,
    visiblePoints: 0,
    clusterCell: 0,
    physicalClears: 0
  };

  function metrics() {
    const rect = shell?.getBoundingClientRect?.();
    const width = Math.max(
      1,
      Math.round(document.documentElement.clientWidth || 0),
      Math.round(window.innerWidth || 0),
      Math.round(rect?.width || 0)
    );
    const height = Math.max(
      1,
      Math.round(document.documentElement.clientHeight || 0),
      Math.round(window.innerHeight || 0),
      Math.round(rect?.height || 0)
    );
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

  function updateZoomLabel() {
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
    updateZoomLabel();
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
    updateZoomLabel();
    scheduleDraw();
  };

  function applyCanvasSize(refit = false) {
    const viewport = metrics();
    const dpr = calculateDpr(viewport);
    const targetWidth = Math.max(1, Math.floor(viewport.width * dpr));
    const targetHeight = Math.max(1, Math.floor(viewport.height * dpr));
    const changed = canvas.width !== targetWidth ||
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
      updateZoomLabel();
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
      if (stableSamples >= 2 || samples >= 10) {
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

  function setInteracting(value, settleDelay = 90) {
    perf.interacting = value;
    if (window.AtlasMobilePerf) window.AtlasMobilePerf.interacting = value;
    root.classList.toggle('atlas-ipad-canvas-interacting', value);
    root.classList.toggle('atlas-interacting', value);
    clearTimeout(perf.settleTimer);
    if (!value) {
      perf.settleTimer = window.setTimeout(() => scheduleDraw(), settleDelay);
    }
  }

  function pointPriority(location) {
    if (location.id === state.selected?.id) return 4;
    if (state.route.some(item => item.id === location.id)) return 3;
    if (state.favorites.has(location.id)) return 2;
    if (!state.discovered.has(location.id)) return 1;
    return 0;
  }

  function clusterPoints(points, cellSize) {
    const buckets = new Map();
    for (const point of points) {
      const key = `${Math.floor(point.x / cellSize)}:${Math.floor(point.y / cellSize)}`;
      let bucket = buckets.get(key);
      if (!bucket) {
        bucket = { x: 0, y: 0, count: 0, items: [], priority: -1 };
        buckets.set(key, bucket);
      }
      bucket.x += point.x;
      bucket.y += point.y;
      bucket.count += 1;
      const priority = pointPriority(point.location);
      if (priority > bucket.priority) {
        bucket.items.unshift(point.location);
        bucket.priority = priority;
        if (bucket.items.length > 8) bucket.items.length = 8;
      } else if (bucket.items.length < 8) {
        bucket.items.push(point.location);
      }
    }
    return [...buckets.values()].map(bucket => ({
      x: bucket.x / bucket.count,
      y: bucket.y / bucket.count,
      count: bucket.count,
      items: bucket.items
    }));
  }

  buildMarkers = function buildMarkersStable(list) {
    const viewport = metrics();
    const source = Array.isArray(list) ? list : visibleLocations();
    const margin = perf.interacting ? 24 : 42;
    const points = [];

    for (const location of source) {
      const point = mapToScreen(location);
      if (point.x < -margin || point.y < -margin || point.x > viewport.width + margin || point.y > viewport.height + margin) continue;
      points.push({ x: point.x, y: point.y, location });
    }

    perf.visiblePoints = points.length;
    const relative = state.scale / stableFitScale(viewport);
    const budget = perf.interacting ? MARKER_BUDGET_ACTIVE : MARKER_BUDGET_IDLE;
    if (!perf.interacting && relative >= 1.62 && points.length <= budget) {
      perf.clusterCell = 0;
      perf.renderedMarkers = points.length;
      return points.map(point => ({ x: point.x, y: point.y, count: 1, items: [point.location] }));
    }

    let cell = perf.interacting
      ? (relative < 0.95 ? 66 : relative < 1.3 ? 56 : 48)
      : (relative < 0.95 ? 54 : relative < 1.25 ? 47 : relative < 1.55 ? 40 : 34);
    let clusters = clusterPoints(points, cell);
    while (clusters.length > budget && cell < 96) {
      cell = Math.ceil(cell * 1.14);
      clusters = clusterPoints(points, cell);
    }
    perf.clusterCell = cell;
    perf.renderedMarkers = clusters.length;
    return clusters;
  };

  function markerColor(location) {
    const category = state.categoryMap.get(location.category_id)?.title || '';
    return AtlasIcons.color(iconType(category));
  }

  function drawCluster(cluster) {
    const location = cluster.items[0];
    if (!location) return;
    const selected = cluster.items.some(item => item.id === state.selected?.id);
    const radius = selected ? 16 : Math.min(15, 9 + Math.log2(cluster.count + 1) * 1.55);
    ctx.save();
    ctx.globalAlpha = perf.interacting ? 0.9 : 1;
    ctx.beginPath();
    ctx.arc(cluster.x, cluster.y, radius + 2, 0, Math.PI * 2);
    ctx.fillStyle = selected ? '#fff0f2' : 'rgba(18,16,15,.9)';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cluster.x, cluster.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = selected ? '#b8202d' : markerColor(location);
    ctx.fill();
    ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeStyle = selected ? '#fff7f8' : 'rgba(255,244,226,.72)';
    ctx.stroke();
    if (!perf.interacting || selected) {
      const label = cluster.count > 99 ? '99+' : String(cluster.count);
      ctx.fillStyle = '#fff';
      ctx.font = `800 ${label.length > 2 ? 9 : 10}px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cluster.x, cluster.y + 0.4);
    }
    ctx.restore();
  }

  function drawLightMarker(cluster, relative) {
    const location = cluster.items[0];
    if (!location) return;
    const selected = location.id === state.selected?.id;
    const discovered = state.discovered.has(location.id);
    const category = state.categoryMap.get(location.category_id)?.title || '';
    const icon = iconType(category);
    const radius = selected ? 10 : Math.max(5.8, Math.min(8, 5.5 + relative * 1.3));
    ctx.save();
    ctx.globalAlpha = discovered && !selected ? 0.34 : 1;
    ctx.beginPath();
    ctx.arc(cluster.x, cluster.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = AtlasIcons.color(icon);
    ctx.fill();
    ctx.lineWidth = selected ? 1.8 : 0.9;
    ctx.strokeStyle = selected ? '#fff7f8' : 'rgba(255,244,226,.66)';
    ctx.stroke();
    if (selected || relative > 1.05) {
      AtlasIcons.draw(ctx, icon, cluster.x, cluster.y, selected ? 15 : Math.max(8, radius * 1.1), { alpha: 1 });
    }
    ctx.restore();
  }

  drawMarker = function drawMarkerStable(cluster, relative) {
    if (cluster.count > 1) {
      drawCluster(cluster);
      return;
    }
    if (!perf.interacting && detailedMarker && state.markers.length <= 720) {
      detailedMarker(cluster, relative);
      return;
    }
    drawLightMarker(cluster, relative);
  };

  drawRoute = function drawRouteStable() {
    if (state.route.length < 2) return;
    const points = state.route.map(mapToScreen);
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = 'rgba(19,14,11,.82)';
    ctx.lineWidth = perf.interacting ? 5 : 7;
    ctx.stroke();
    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = '#e6bd70';
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.restore();
  };

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

  draw = function drawStable() {
    const viewport = metrics();
    physicalClear();
    if (state.imageReady) {
      ctx.save();
      ctx.globalAlpha = 0.92;
      ctx.imageSmoothingEnabled = true;
      ctx.imageSmoothingQuality = perf.interacting ? 'medium' : 'high';
      ctx.drawImage(state.image, state.offsetX, state.offsetY, WORLD_SIZE * state.scale, WORLD_SIZE * state.scale);
      ctx.restore();
    }
    drawRoute();
    const list = visibleLocations();
    const relative = state.scale / stableFitScale(viewport);
    state.markers = buildMarkers(list);
    for (const marker of state.markers) drawMarker(marker, relative);
    const count = document.getElementById('visibleCount');
    if (count) count.textContent = String(list.length);
  };

  scheduleDraw = function scheduleDrawStable() {
    if (state.framePending || document.hidden) return;
    const now = performance.now();
    const minimumGap = perf.interacting ? 33.4 : 16.7;
    const wait = Math.max(0, minimumGap - (now - perf.lastFrameAt));
    state.framePending = true;
    clearTimeout(perf.frameTimer);
    perf.frameTimer = window.setTimeout(() => {
      perf.frameRaf = requestAnimationFrame(() => {
        state.framePending = false;
        perf.lastFrameAt = performance.now();
        draw();
      });
    }, wait);
  };

  function endInteraction() {
    setInteracting(false, 100);
  }

  canvas.addEventListener('pointerdown', () => setInteracting(true), { capture: true, passive: true });
  canvas.addEventListener('pointerup', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('pointercancel', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('touchend', endInteraction, { capture: true, passive: true });
  canvas.addEventListener('wheel', () => {
    setInteracting(true);
    clearTimeout(perf.settleTimer);
    perf.settleTimer = window.setTimeout(endInteraction, 150);
  }, { capture: true, passive: true });

  if (legacyResize) removeEventListener('resize', legacyResize);
  addEventListener('resize', () => settleResize(false), { passive: true });
  addEventListener('orientationchange', () => settleResize(true), { passive: true });
  window.visualViewport?.addEventListener('resize', () => settleResize(false), { passive: true });
  window.visualViewport?.addEventListener('scroll', () => settleResize(false), { passive: true });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(perf.frameTimer);
      cancelAnimationFrame(perf.frameRaf);
      state.framePending = false;
    } else {
      setInteracting(false, 0);
      settleResize(false);
    }
  }, { passive: true });

  addEventListener('pageshow', event => {
    setInteracting(false, 0);
    settleResize(Boolean(event.persisted));
  }, { passive: true });

  const canonicalViewport = 'width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no,interactive-widget=resizes-content';
  if (viewportMeta && viewportMeta.getAttribute('content') !== canonicalViewport) {
    viewportMeta.setAttribute('content', canonicalViewport);
  }

  const zoomInButton = document.getElementById('zoomIn');
  const zoomOutButton = document.getElementById('zoomOut');
  const resetButtons = ['resetView', 'locateBtn', 'brandBtn'];
  if (zoomInButton) zoomInButton.onclick = () => zoomAt(1.25);
  if (zoomOutButton) zoomOutButton.onclick = () => zoomAt(0.8);
  resetButtons.forEach(id => {
    const button = document.getElementById(id);
    if (button) button.onclick = () => { fitMap(); scheduleDraw(); };
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
      clusterCell: perf.clusterCell,
      physicalClears: perf.physicalClears,
      markerBudgetIdle: MARKER_BUDGET_IDLE,
      markerBudgetActive: MARKER_BUDGET_ACTIVE
    })
  });

  applyCanvasSize(true);
  window.setTimeout(() => applyCanvasSize(false), 420);
  window.setTimeout(() => applyCanvasSize(false), 900);
  scheduleDraw();
})();