(() => {
  'use strict';

  const VERSION = '0.9.4.13a';
  const WORLD_SIZE = 4096;
  const root = document.documentElement;
  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isTablet = matchMedia('(pointer:coarse)').matches && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isTablet) return;

  const canvas = document.getElementById('mapCanvas');
  if (!canvas || typeof draw !== 'function' || typeof mapToScreen !== 'function') return;

  root.classList.add('atlas-ipad-ultra', 'atlas-solid-glass');

  const nativeDetailedMarker = window.AtlasMarkerDesign?.render || drawMarker;
  const mobilePerf = window.AtlasMobilePerf || {};
  const perf = {
    version: VERSION,
    interacting: false,
    lastFrame: 0,
    timer: 0,
    raf: 0,
    settleTimer: 0,
    resizeTimer: 0,
    maxCanvasPixels: 2_400_000,
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

  function zoomOverviewAt(factor, x = innerWidth / 2, y = innerHeight / 2) {
    const oldScale = state.scale;
    const minimum = overviewScale();
    const nextScale = clampValue(oldScale * factor, minimum, state.maxScale);
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

  window.minScale = overviewScale;
  window.fitMap = fitOverview;
  window.updateZoomLabel = updateLabel;
  window.zoomAt = zoomOverviewAt;

  function setInteracting(value, settle = 90) {
    perf.interacting = value;
    mobilePerf.interacting = value;
    root.classList.toggle('atlas-ultra-interacting', value);
    root.classList.toggle('atlas-interacting', value);
    clearTimeout(perf.settleTimer);
    if (!value) perf.settleTimer = setTimeout(scheduleDraw, settle);
  }

  canvas.addEventListener('pointerdown', () => setInteracting(true), { capture: true, passive: true });
  canvas.addEventListener('pointerup', () => setInteracting(false, 70), { capture: true, passive: true });
  canvas.addEventListener('pointercancel', () => setInteracting(false, 70), { capture: true, passive: true });
  canvas.addEventListener('touchend', () => setInteracting(false, 70), { capture: true, passive: true });
  canvas.addEventListener('wheel', () => {
    setInteracting(true);
    clearTimeout(perf.settleTimer);
    perf.settleTimer = setTimeout(() => setInteracting(false, 60), 130);
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
    const margin = perf.interacting ? 18 : 30;
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

  function drawEdgeExtension(destinationX, destinationY, destinationWidth, destinationHeight) {
    if (!state.imageReady) return;
    const strip = 112;
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
    ctx.globalAlpha = perf.interacting ? .24 : .32;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'low';

    if (leftGap > .5) ctx.drawImage(state.image, 0, 0, strip, WORLD_SIZE, 0, 0, Math.ceil(leftGap), innerHeight);
    if (rightGap > .5) ctx.drawImage(state.image, WORLD_SIZE - strip, 0, strip, WORLD_SIZE, Math.floor(mapRight), 0, Math.ceil(rightGap), innerHeight);
    if (topGap > .5) ctx.drawImage(state.image, 0, 0, WORLD_SIZE, strip, 0, 0, innerWidth, Math.ceil(topGap));
    if (bottomGap > .5) ctx.drawImage(state.image, 0, WORLD_SIZE - strip, WORLD_SIZE, strip, 0, Math.floor(mapBottom), innerWidth, Math.ceil(bottomGap));

    ctx.globalAlpha = 1;
    ctx.fillStyle = 'rgba(8,7,8,.46)';
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

    const screenX = Math.round(state.offsetX + sourceX * scale);
    const screenY = Math.round(state.offsetY + sourceY * scale);
    const screenWidth = Math.ceil(sourceWidth * scale);
    const screenHeight = Math.ceil(sourceHeight * scale);

    ctx.save();
    ctx.globalAlpha = .94;
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = perf.interacting ? 'low' : 'high';
    ctx.drawImage(
      state.image,
      Math.floor(sourceX), Math.floor(sourceY), Math.ceil(sourceWidth), Math.ceil(sourceHeight),
      screenX, screenY, screenWidth, screenHeight
    );
    ctx.restore();
  }

  function drawPointBatches(markers, relative) {
    const radius = perf.interacting ? 1.55 : relative < 1.05 ? 2.15 : 2.65;
    const paths = new Map();
    const fallback = typeof Path2D !== 'function';

    if (fallback) {
      let previousColor = '';
      for (const marker of markers) {
        const location = marker.items[0];
        const color = markerColor(location);
        if (color !== previousColor) {
          previousColor = color;
          ctx.fillStyle = color;
        }
        const size = location.id === state.selected?.id ? radius * 3 : radius * 2;
        ctx.globalAlpha = state.discovered.has(location.id) ? .45 : .9;
        ctx.fillRect(Math.round(marker.x - size / 2), Math.round(marker.y - size / 2), Math.ceil(size), Math.ceil(size));
      }
      ctx.globalAlpha = 1;
      return;
    }

    for (const marker of markers) {
      const location = marker.items[0];
      const discovered = state.discovered.has(location.id);
      const selected = location.id === state.selected?.id;
      const key = `${markerColor(location)}|${discovered ? 1 : 0}|${selected ? 1 : 0}`;
      let entry = paths.get(key);
      if (!entry) {
        entry = {
          color: markerColor(location),
          alpha: discovered ? .45 : .9,
          path: new Path2D()
        };
        paths.set(key, entry);
      }
      const pointRadius = selected ? radius * 1.65 : radius;
      entry.path.arc(Math.round(marker.x), Math.round(marker.y), pointRadius, 0, Math.PI * 2);
    }

    ctx.save();
    for (const entry of paths.values()) {
      ctx.globalAlpha = entry.alpha;
      ctx.fillStyle = entry.color;
      ctx.fill(entry.path);
    }
    ctx.restore();
  }

  function drawSimpleMarker(marker, relative) {
    const location = marker.items[0];
    if (!location) return;
    const selected = location.id === state.selected?.id;
    const discovered = state.discovered.has(location.id);
    const radius = selected ? 9.5 : clampValue(5.6 + relative * 1.05, 6, 8);
    const centerY = marker.y - radius * 1.02;
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
    ctx.fillStyle = color;
    ctx.fill();
    ctx.lineWidth = 1;
    ctx.strokeStyle = 'rgba(255,247,244,.62)';
    ctx.stroke();
    if (!perf.interacting && state.markers.length < 560) {
      const category = state.categoryMap.get(location.category_id)?.title || '';
      AtlasIcons.draw(ctx, iconType(category), marker.x, centerY, selected ? 12 : 9.5, { alpha: 1 });
    }
    ctx.restore();
  }

  drawMarker = function drawIpadMarker(marker, relative) {
    if (!perf.interacting && relative > 1.55 && state.markers.length < 420) {
      nativeDetailedMarker(marker, relative);
      return;
    }
    drawSimpleMarker(marker, relative);
  };

  drawRoute = function drawIpadRoute() {
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
  };

  draw = function drawIpadOptimized() {
    drawBaseMap();
    drawRoute();

    const list = visibleLocations();
    const relative = state.scale / overviewScale();
    state.markers = buildMarkers(list);

    if (relative < 1.28 || state.markers.length > 1450) {
      perf.lastLod = 'overview-all-points';
      drawPointBatches(state.markers, relative);
    } else if (relative < 1.7 || state.markers.length > 760) {
      perf.lastLod = 'mid-all-points';
      drawPointBatches(state.markers, relative);
    } else {
      perf.lastLod = 'detail-markers';
      for (const marker of state.markers) drawMarker(marker, relative);
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
    const target = Math.max(1, Math.min(hardwareDpr, pixelLimitedDpr, 1.3));
    const dpr = Math.round(target * 20) / 20;
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
  root.dataset.atlasPointRepresentation = 'all-points-lod';
  tuneCanvas(true);
  setTimeout(() => tuneCanvas(false), 320);
})();
