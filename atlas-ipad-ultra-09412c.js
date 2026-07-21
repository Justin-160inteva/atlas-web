(() => {
  'use strict';

  const VERSION = '0.9.4.13b';
  const WORLD_SIZE = 4096;
  const root = document.documentElement;
  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isTablet = matchMedia('(pointer:coarse)').matches && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isTablet) return;

  const canvas = document.getElementById('mapCanvas');
  if (!canvas || typeof draw !== 'function' || typeof mapToScreen !== 'function') return;

  root.classList.add('atlas-ipad-ultra', 'atlas-solid-glass');
  window.AtlasPerf092?.setQuality?.(2);

  const perf = {
    version: VERSION,
    interacting: false,
    lastFrame: 0,
    timer: 0,
    raf: 0,
    settleTimer: 0,
    resizeTimer: 0,
    maxCanvasPixels: 2_200_000,
    dpr: 1,
    gridSize: 64,
    grid: null,
    gridSource: null,
    visibleKey: '',
    visibleCache: [],
    lastVisiblePoints: 0,
    lastRenderedMarkers: 0,
    lastLod: 'overview-all-points',
    overviewScale: 0,
    edgeFill: false
  };

  const clampValue = (value, minimum, maximum) => Math.max(minimum, Math.min(maximum, value));

  function viewportSize() {
    const measured = window.AtlasViewport?.measure?.();
    return {
      width: Math.max(1, Math.round(Number(measured?.width || innerWidth || 1))),
      height: Math.max(1, Math.round(Number(measured?.height || innerHeight || 1)))
    };
  }

  function overviewScale() {
    const viewport = viewportSize();
    return Math.min(viewport.width / WORLD_SIZE, viewport.height / WORLD_SIZE);
  }

  function updateLabel() {
    const label = document.getElementById('zoomLabel');
    if (!label) return;
    const base = overviewScale();
    const ratio = base > 0 ? state.scale / base : 1;
    label.textContent = `×${ratio.toFixed(ratio < 10 ? 2 : 0)}`;
  }

  function fitOverview() {
    const viewport = viewportSize();
    const scale = overviewScale();
    state.scale = scale;
    state.offsetX = (viewport.width - WORLD_SIZE * scale) / 2;
    state.offsetY = (viewport.height - WORLD_SIZE * scale) / 2;
    perf.overviewScale = scale;
    updateLabel();
    scheduleDraw();
    root.dataset.atlasMapFit = 'full-overview';
  }

  function clampToOverview(anchorX = innerWidth / 2, anchorY = innerHeight / 2) {
    const minimum = overviewScale();
    if (!Number.isFinite(state.scale) || state.scale >= minimum) return false;
    const oldScale = Math.max(state.scale, 0.000001);
    const mapX = (anchorX - state.offsetX) / oldScale;
    const mapY = (anchorY - state.offsetY) / oldScale;
    state.scale = minimum;
    state.offsetX = anchorX - mapX * minimum;
    state.offsetY = anchorY - mapY * minimum;
    updateLabel();
    return true;
  }

  function zoomOverviewAt(factor, x = innerWidth / 2, y = innerHeight / 2) {
    const oldScale = Math.max(state.scale, overviewScale());
    const nextScale = clampValue(oldScale * factor, overviewScale(), state.maxScale);
    if (Math.abs(nextScale - oldScale) < 1e-8) {
      updateLabel();
      return;
    }
    const mapX = (x - state.offsetX) / oldScale;
    const mapY = (y - state.offsetY) / oldScale;
    state.scale = nextScale;
    state.offsetX = x - mapX * nextScale;
    state.offsetY = y - mapY * nextScale;
    updateLabel();
    scheduleDraw();
  }

  window.fitMap = fitOverview;
  window.updateZoomLabel = updateLabel;
  window.zoomAt = zoomOverviewAt;

  function setInteracting(value, settle = 80) {
    perf.interacting = value;
    if (window.AtlasMobilePerf) window.AtlasMobilePerf.interacting = value;
    root.classList.toggle('atlas-ultra-interacting', value);
    root.classList.toggle('atlas-interacting', value);
    clearTimeout(perf.settleTimer);
    if (!value) perf.settleTimer = setTimeout(scheduleDraw, settle);
  }

  canvas.addEventListener('pointerdown', () => setInteracting(true), { capture: true, passive: true });
  canvas.addEventListener('pointerup', () => setInteracting(false, 60), { capture: true, passive: true });
  canvas.addEventListener('pointercancel', () => setInteracting(false, 60), { capture: true, passive: true });
  canvas.addEventListener('touchend', () => {
    clampToOverview();
    setInteracting(false, 60);
  }, { capture: true, passive: true });
  canvas.addEventListener('pointermove', event => {
    if (state.pointers?.size === 2 && clampToOverview(event.clientX, event.clientY)) scheduleDraw();
  }, { capture: true, passive: true });
  canvas.addEventListener('wheel', event => {
    setInteracting(true);
    if (clampToOverview(event.clientX, event.clientY)) scheduleDraw();
    clearTimeout(perf.settleTimer);
    perf.settleTimer = setTimeout(() => setInteracting(false, 50), 120);
  }, { capture: true, passive: true });
  addEventListener('blur', () => setInteracting(false, 0), { passive: true });

  scheduleDraw = function scheduleIpadDraw() {
    if (state.framePending || document.hidden) return;
    const now = performance.now();
    const minimumGap = perf.interacting ? 33.4 : 16.7;
    const wait = Math.max(0, minimumGap - (now - perf.lastFrame));
    state.framePending = true;
    clearTimeout(perf.timer);
    perf.timer = setTimeout(() => {
      perf.raf = requestAnimationFrame(() => {
        state.framePending = false;
        perf.lastFrame = performance.now();
        draw();
      });
    }, wait);
  };

  const originalVisibleLocations = visibleLocations;
  visibleLocations = function visibleLocationsCached() {
    const enabled = [...state.enabled].join('|');
    const favorites = state.mode === 'favorites' ? [...state.favorites].join('|') : '';
    const key = `${state.locations.length};${state.mode};${enabled};${favorites}`;
    if (key !== perf.visibleKey) {
      perf.visibleKey = key;
      perf.visibleCache = originalVisibleLocations();
    }
    return perf.visibleCache;
  };

  function buildGrid() {
    if (perf.gridSource === state.locations && perf.grid) return;
    const size = perf.gridSize;
    const grid = Array.from({ length: size * size }, () => []);
    for (const location of state.locations) {
      const x = clampValue(Math.floor(location.atlas_x * size), 0, size - 1);
      const y = clampValue(Math.floor(location.atlas_y * size), 0, size - 1);
      grid[y * size + x].push(location);
    }
    perf.grid = grid;
    perf.gridSource = state.locations;
  }

  function eligible(location) {
    if (!state.enabled.has(location.category_id)) return false;
    if (state.mode === 'all') return true;
    if (state.mode === 'favorites') return state.favorites.has(location.id);
    return categoryGroup(state.categoryMap.get(location.category_id)?.title) === state.mode;
  }

  buildMarkers = function buildAllVisibleMarkers() {
    buildGrid();
    const size = perf.gridSize;
    const margin = perf.interacting ? 16 : 28;
    const left = (-margin - state.offsetX) / (WORLD_SIZE * state.scale);
    const right = (innerWidth + margin - state.offsetX) / (WORLD_SIZE * state.scale);
    const top = (-margin - state.offsetY) / (WORLD_SIZE * state.scale);
    const bottom = (innerHeight + margin - state.offsetY) / (WORLD_SIZE * state.scale);
    const x0 = clampValue(Math.floor(Math.min(left, right) * size), 0, size - 1);
    const x1 = clampValue(Math.floor(Math.max(left, right) * size), 0, size - 1);
    const y0 = clampValue(Math.floor(Math.min(top, bottom) * size), 0, size - 1);
    const y1 = clampValue(Math.floor(Math.max(top, bottom) * size), 0, size - 1);
    const output = [];

    for (let y = y0; y <= y1; y += 1) {
      for (let x = x0; x <= x1; x += 1) {
        for (const location of perf.grid[y * size + x]) {
          if (!eligible(location)) continue;
          const point = mapToScreen(location);
          if (point.x < -margin || point.y < -margin || point.x > innerWidth + margin || point.y > innerHeight + margin) continue;
          output.push({ x: point.x, y: point.y, count: 1, items: [location] });
        }
      }
    }

    perf.lastVisiblePoints = output.length;
    perf.lastRenderedMarkers = output.length;
    return output;
  };

  function markerColor(location) {
    const category = state.categoryMap.get(location.category_id)?.title || '';
    return AtlasIcons.color(iconType(category));
  }

  function drawEdgeExtension() {
    if (!state.imageReady) return;
    const strip = 96;
    const mapWidth = WORLD_SIZE * state.scale;
    const mapHeight = WORLD_SIZE * state.scale;
    const mapLeft = state.offsetX;
    const mapTop = state.offsetY;
    const mapRight = mapLeft + mapWidth;
    const mapBottom = mapTop + mapHeight;
    const leftGap = Math.max(0, mapLeft);
    const rightGap = Math.max(0, innerWidth - mapRight);
    const topGap = Math.max(0, mapTop);
    const bottomGap = Math.max(0, innerHeight - mapBottom);

    perf.edgeFill = leftGap > .5 || rightGap > .5 || topGap > .5 || bottomGap > .5;
    if (!perf.edgeFill) return;

    ctx.save();
    ctx.globalAlpha = .26;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'low';
    if (leftGap > .5) ctx.drawImage(state.image, 0, 0, strip, WORLD_SIZE, 0, 0, Math.ceil(leftGap), innerHeight);
    if (rightGap > .5) ctx.drawImage(state.image, WORLD_SIZE - strip, 0, strip, WORLD_SIZE, Math.floor(mapRight), 0, Math.ceil(rightGap), innerHeight);
    if (topGap > .5) ctx.drawImage(state.image, 0, 0, WORLD_SIZE, strip, 0, 0, innerWidth, Math.ceil(topGap));
    if (bottomGap > .5) ctx.drawImage(state.image, 0, WORLD_SIZE - strip, WORLD_SIZE, strip, 0, Math.floor(mapBottom), innerWidth, Math.ceil(bottomGap));
    ctx.fillStyle = 'rgba(12,10,11,.5)';
    if (leftGap > .5) ctx.fillRect(0, 0, Math.ceil(leftGap), innerHeight);
    if (rightGap > .5) ctx.fillRect(Math.floor(mapRight), 0, Math.ceil(rightGap), innerHeight);
    if (topGap > .5) ctx.fillRect(0, 0, innerWidth, Math.ceil(topGap));
    if (bottomGap > .5) ctx.fillRect(0, Math.floor(mapBottom), innerWidth, Math.ceil(bottomGap));
    ctx.restore();
  }

  function drawBaseMap() {
    ctx.fillStyle = '#171415';
    ctx.fillRect(0, 0, innerWidth, innerHeight);
    if (!state.imageReady) return;
    drawEdgeExtension();

    const scale = state.scale;
    const sourceX = clampValue((-state.offsetX) / scale, 0, WORLD_SIZE);
    const sourceY = clampValue((-state.offsetY) / scale, 0, WORLD_SIZE);
    const sourceRight = clampValue((innerWidth - state.offsetX) / scale, 0, WORLD_SIZE);
    const sourceBottom = clampValue((innerHeight - state.offsetY) / scale, 0, WORLD_SIZE);
    const sourceWidth = sourceRight - sourceX;
    const sourceHeight = sourceBottom - sourceY;
    if (sourceWidth <= 0 || sourceHeight <= 0) return;

    ctx.save();
    ctx.globalAlpha = .94;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = perf.interacting ? 'low' : 'medium';
    ctx.drawImage(
      state.image,
      Math.floor(sourceX), Math.floor(sourceY), Math.ceil(sourceWidth), Math.ceil(sourceHeight),
      Math.round(state.offsetX + sourceX * scale), Math.round(state.offsetY + sourceY * scale),
      Math.ceil(sourceWidth * scale), Math.ceil(sourceHeight * scale)
    );
    ctx.restore();
  }

  function drawPointBatches(markers, relative) {
    const baseRadius = perf.interacting ? 1.45 : relative < 1.05 ? 2.05 : 2.5;
    const groups = new Map();

    for (const marker of markers) {
      const location = marker.items[0];
      const discovered = state.discovered.has(location.id);
      const selected = location.id === state.selected?.id;
      const color = markerColor(location);
      const key = `${color}|${discovered ? 1 : 0}|${selected ? 1 : 0}`;
      let group = groups.get(key);
      if (!group) {
        group = { color, alpha: discovered ? .45 : .9, selected, markers: [] };
        groups.set(key, group);
      }
      group.markers.push(marker);
    }

    ctx.save();
    for (const group of groups.values()) {
      ctx.beginPath();
      const radius = group.selected ? baseRadius * 1.75 : baseRadius;
      for (const marker of group.markers) {
        const x = Math.round(marker.x);
        const y = Math.round(marker.y);
        ctx.moveTo(x + radius, y);
        ctx.arc(x, y, radius, 0, Math.PI * 2);
      }
      ctx.globalAlpha = group.alpha;
      ctx.fillStyle = group.color;
      ctx.fill();
      if (group.selected) {
        ctx.globalAlpha = 1;
        ctx.lineWidth = 1.5;
        ctx.strokeStyle = 'rgba(255,255,255,.9)';
        ctx.stroke();
      }
    }
    ctx.restore();
  }

  function drawSimpleMarker(marker, relative) {
    const location = marker.items[0];
    if (!location) return;
    const selected = location.id === state.selected?.id;
    const discovered = state.discovered.has(location.id);
    const radius = selected ? 9.5 : clampValue(5.5 + relative, 6, 8);
    const centerY = marker.y - radius;
    const color = markerColor(location);

    ctx.save();
    ctx.globalAlpha = discovered && !selected ? .43 : 1;
    ctx.beginPath();
    ctx.moveTo(marker.x, marker.y + 1);
    ctx.lineTo(marker.x - radius * .48, centerY + radius * .45);
    ctx.lineTo(marker.x + radius * .48, centerY + radius * .45);
    ctx.closePath();
    ctx.fillStyle = color;
    ctx.fill();
    ctx.beginPath();
    ctx.arc(marker.x, centerY, radius, 0, Math.PI * 2);
    ctx.fill();
    ctx.lineWidth = selected ? 1.6 : 1;
    ctx.strokeStyle = selected ? 'rgba(255,255,255,.92)' : 'rgba(255,247,244,.62)';
    ctx.stroke();
    if (!perf.interacting && state.markers.length < 520) {
      const category = state.categoryMap.get(location.category_id)?.title || '';
      AtlasIcons.draw(ctx, iconType(category), marker.x, centerY, selected ? 12 : 9.25, { alpha: 1 });
    }
    ctx.restore();
  }

  function drawStaticRoute() {
    if (state.route.length < 2) return;
    const points = state.route.map(mapToScreen);
    ctx.save();
    ctx.lineCap = 'round';
    ctx.lineJoin = 'round';
    ctx.beginPath();
    points.forEach((point, index) => index ? ctx.lineTo(point.x, point.y) : ctx.moveTo(point.x, point.y));
    ctx.strokeStyle = 'rgba(16,12,13,.84)';
    ctx.lineWidth = perf.interacting ? 5 : 7;
    ctx.stroke();
    ctx.strokeStyle = '#e6bd70';
    ctx.lineWidth = 2.5;
    ctx.stroke();
    ctx.restore();
  }

  draw = function drawIpadOptimized() {
    clampToOverview();
    drawBaseMap();
    drawStaticRoute();

    const list = visibleLocations();
    const relative = state.scale / overviewScale();
    state.markers = buildMarkers(list);

    if (relative < 1.35 || state.markers.length > 1200) {
      perf.lastLod = 'overview-all-points';
      drawPointBatches(state.markers, relative);
    } else if (relative < 1.75 || state.markers.length > 700) {
      perf.lastLod = 'mid-simple-markers';
      for (const marker of state.markers) drawSimpleMarker(marker, relative);
    } else {
      perf.lastLod = 'detail-simple-markers';
      for (const marker of state.markers) drawSimpleMarker(marker, relative);
    }

    const count = document.getElementById('visibleCount');
    if (count && count.textContent !== String(list.length)) count.textContent = String(list.length);
  };

  function tuneCanvas(refit = false) {
    const viewport = viewportSize();
    const previousOverview = perf.overviewScale || overviewScale();
    const wasOverview = state.scale <= previousOverview * 1.025;
    const area = Math.max(1, viewport.width * viewport.height);
    const hardwareDpr = devicePixelRatio || 1;
    const pixelLimitedDpr = Math.sqrt(perf.maxCanvasPixels / area);
    const dpr = Math.round(Math.max(1, Math.min(hardwareDpr, pixelLimitedDpr, 1.25)) * 20) / 20;
    const width = Math.floor(viewport.width * dpr);
    const height = Math.floor(viewport.height * dpr);
    perf.dpr = dpr;
    perf.overviewScale = overviewScale();

    if (canvas.width !== width || canvas.height !== height) {
      canvas.width = width;
      canvas.height = height;
      canvas.style.width = `${viewport.width}px`;
      canvas.style.height = `${viewport.height}px`;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      state.framePending = false;
    }

    if (refit || wasOverview) fitOverview();
    else scheduleDraw();
  }

  document.addEventListener('click', event => {
    const button = event.target.closest('#zoomIn,#zoomOut,#resetView,#brandBtn,#locateBtn');
    if (!button) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    if (button.id === 'zoomIn') zoomOverviewAt(1.25);
    else if (button.id === 'zoomOut') zoomOverviewAt(.8);
    else fitOverview();
  }, true);

  addEventListener('resize', () => {
    clearTimeout(perf.resizeTimer);
    perf.resizeTimer = setTimeout(() => tuneCanvas(false), 100);
  }, { passive: true });

  root.addEventListener('atlas:viewportchange', () => {
    clearTimeout(perf.resizeTimer);
    perf.resizeTimer = setTimeout(() => tuneCanvas(false), 70);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(perf.timer);
      cancelAnimationFrame(perf.raf);
      state.framePending = false;
    } else {
      tuneCanvas(false);
    }
  }, { passive: true });

  window.AtlasIpadUltra = Object.freeze({
    version: VERSION,
    fitOverview,
    overviewScale,
    audit: () => ({
      version: VERSION,
      active: root.classList.contains('atlas-ipad-ultra'),
      interacting: perf.interacting,
      dpr: perf.dpr,
      visiblePoints: perf.lastVisiblePoints,
      renderedMarkers: perf.lastRenderedMarkers,
      representationComplete: perf.lastVisiblePoints === perf.lastRenderedMarkers,
      lod: perf.lastLod,
      edgeFill: perf.edgeFill,
      minimumZoomMode: 'full-map-overview',
      canvasPixelBudget: perf.maxCanvasPixels,
      backdropMode: 'solid-no-backdrop-filter'
    })
  });

  root.dataset.atlasIpadUltra = VERSION;
  root.dataset.atlasPointRepresentation = 'all-points-safe-batching';
  tuneCanvas(true);
  setTimeout(() => tuneCanvas(false), 420);
  setTimeout(() => tuneCanvas(false), 820);
  setTimeout(() => tuneCanvas(false), 1500);
})();
