(() => {
  'use strict';

  const root = document.documentElement;
  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isTablet = matchMedia('(pointer:coarse)').matches && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isTablet) return;

  const canvas = document.getElementById('mapCanvas');
  if (!canvas || typeof draw !== 'function' || typeof mapToScreen !== 'function') return;

  root.classList.add('atlas-ipad-ultra', 'atlas-solid-glass');

  const mobilePerf = window.AtlasMobilePerf || {};
  const perf = {
    version: '0.9.4.12c',
    interacting: false,
    lastFrame: 0,
    timer: 0,
    raf: 0,
    settleTimer: 0,
    resizeTimer: 0,
    markerBudgetIdle: 780,
    markerBudgetActive: 460,
    maxCanvasPixels: 3_100_000,
    dpr: 1,
    lastVisiblePoints: 0,
    lastRenderedMarkers: 0,
    lastClusterCell: 0
  };

  const detailedMarker = window.AtlasMarkerDesign?.render || drawMarker;

  function setInteracting(value, settle = 100) {
    perf.interacting = value;
    mobilePerf.interacting = value;
    root.classList.toggle('atlas-ultra-interacting', value);
    root.classList.toggle('atlas-interacting', value);
    clearTimeout(perf.settleTimer);
    if (!value) {
      perf.settleTimer = setTimeout(() => scheduleDraw(), settle);
    }
  }

  canvas.addEventListener('pointerdown', () => setInteracting(true), { capture: true, passive: true });
  canvas.addEventListener('pointerup', () => setInteracting(false, 80), { capture: true, passive: true });
  canvas.addEventListener('pointercancel', () => setInteracting(false, 80), { capture: true, passive: true });
  canvas.addEventListener('touchend', () => setInteracting(false, 80), { capture: true, passive: true });
  canvas.addEventListener('wheel', () => {
    setInteracting(true);
    clearTimeout(perf.settleTimer);
    perf.settleTimer = setTimeout(() => setInteracting(false, 80), 150);
  }, { capture: true, passive: true });
  addEventListener('blur', () => setInteracting(false, 0), { passive: true });

  scheduleDraw = function scheduleIpadDraw() {
    if (state.framePending || document.hidden) return;
    const now = performance.now();
    const minGap = perf.interacting ? 33.4 : 16.7;
    const wait = Math.max(0, minGap - (now - perf.lastFrame));
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
        if (bucket.items.length > 6) bucket.items.length = 6;
      } else if (bucket.items.length < 6) {
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

  buildMarkers = function buildIpadMarkers(list) {
    const locations = Array.isArray(list) ? list : visibleLocations();
    const margin = perf.interacting ? 24 : 40;
    const points = [];
    for (const location of locations) {
      const point = mapToScreen(location);
      if (point.x < -margin || point.y < -margin || point.x > innerWidth + margin || point.y > innerHeight + margin) continue;
      points.push({ x: point.x, y: point.y, location });
    }

    perf.lastVisiblePoints = points.length;
    const relative = state.scale / fitScale();
    const budget = perf.interacting ? perf.markerBudgetActive : perf.markerBudgetIdle;
    if (!perf.interacting && relative >= 1.55 && points.length <= budget) {
      perf.lastClusterCell = 0;
      perf.lastRenderedMarkers = points.length;
      return points.map(point => ({ x: point.x, y: point.y, count: 1, items: [point.location] }));
    }

    let cell = perf.interacting
      ? (relative < 1 ? 62 : relative < 1.25 ? 54 : 46)
      : (relative < .95 ? 52 : relative < 1.2 ? 46 : relative < 1.5 ? 40 : 34);
    let clusters = clusterPoints(points, cell);
    while (clusters.length > budget && cell < 88) {
      cell = Math.ceil(cell * 1.14);
      clusters = clusterPoints(points, cell);
    }
    perf.lastClusterCell = cell;
    perf.lastRenderedMarkers = clusters.length;
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
    const radius = selected ? 16 : Math.min(15, 9 + Math.log2(cluster.count + 1) * 1.6);
    ctx.save();
    ctx.globalAlpha = perf.interacting ? .9 : 1;
    ctx.beginPath();
    ctx.arc(cluster.x, cluster.y, radius + 2, 0, Math.PI * 2);
    ctx.fillStyle = selected ? '#f8e8e9' : '#181416';
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cluster.x, cluster.y, radius, 0, Math.PI * 2);
    ctx.fillStyle = selected ? '#b72d3c' : markerColor(location);
    ctx.fill();
    ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeStyle = selected ? '#fff5f6' : 'rgba(255,247,244,.72)';
    ctx.stroke();
    if (!perf.interacting || selected) {
      const label = cluster.count > 99 ? '99+' : String(cluster.count);
      ctx.fillStyle = '#fff';
      ctx.font = `800 ${label.length > 2 ? 9 : 10}px -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif`;
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(label, cluster.x, cluster.y + .4);
    }
    ctx.restore();
  }

  function drawSimpleMarker(cluster, relative) {
    const location = cluster.items[0];
    if (!location) return;
    const selected = location.id === state.selected?.id;
    const discovered = state.discovered.has(location.id);
    const radius = selected ? 9.5 : Math.max(5.8, Math.min(7.5, 5.5 + relative * 1.25));
    const centerY = cluster.y - radius * 1.05;
    ctx.save();
    ctx.globalAlpha = discovered && !selected ? .42 : 1;
    ctx.beginPath();
    ctx.moveTo(cluster.x, cluster.y + 1);
    ctx.lineTo(cluster.x - radius * .46, centerY + radius * .45);
    ctx.lineTo(cluster.x + radius * .46, centerY + radius * .45);
    ctx.closePath();
    ctx.fillStyle = markerColor(location);
    ctx.fill();
    ctx.beginPath();
    ctx.arc(cluster.x, centerY, radius, 0, Math.PI * 2);
    ctx.fillStyle = markerColor(location);
    ctx.fill();
    ctx.lineWidth = selected ? 2 : 1;
    ctx.strokeStyle = selected ? '#fff7f8' : 'rgba(255,247,244,.68)';
    ctx.stroke();
    if (!perf.interacting && state.markers.length < 620) {
      const category = state.categoryMap.get(location.category_id)?.title || '';
      AtlasIcons.draw(ctx, iconType(category), cluster.x, centerY, selected ? 12.5 : 9.5, { alpha: 1 });
    }
    ctx.restore();
  }

  drawMarker = function drawIpadMarker(cluster, relative) {
    if (cluster.count > 1) {
      drawCluster(cluster);
      return;
    }
    if (!perf.interacting && relative > 1.35 && state.markers.length < 430) {
      detailedMarker(cluster, relative);
      return;
    }
    drawSimpleMarker(cluster, relative);
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
    if (!perf.interacting) {
      points.forEach((point, index) => {
        if (index !== 0 && index !== points.length - 1 && points.length > 18) return;
        ctx.beginPath();
        ctx.arc(point.x, point.y, index === 0 || index === points.length - 1 ? 8 : 6, 0, Math.PI * 2);
        ctx.fillStyle = index === 0 ? '#d6aa56' : index === points.length - 1 ? '#f2e7d3' : '#a9212e';
        ctx.fill();
      });
    }
    ctx.restore();
  };

  function tuneCanvas() {
    const area = Math.max(1, innerWidth * innerHeight);
    const hardwareDpr = devicePixelRatio || 1;
    const pixelLimitedDpr = Math.sqrt(perf.maxCanvasPixels / area);
    const target = Math.max(1, Math.min(hardwareDpr, pixelLimitedDpr, 1.45));
    const dpr = Math.round(target * 20) / 20;
    const width = Math.floor(innerWidth * dpr);
    const height = Math.floor(innerHeight * dpr);
    perf.dpr = dpr;
    if (canvas.width === width && canvas.height === height) return;
    canvas.width = width;
    canvas.height = height;
    canvas.style.width = `${innerWidth}px`;
    canvas.style.height = `${innerHeight}px`;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    scheduleDraw();
  }

  addEventListener('resize', () => {
    clearTimeout(perf.resizeTimer);
    perf.resizeTimer = setTimeout(tuneCanvas, 120);
  }, { passive: true });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      clearTimeout(perf.timer);
      cancelAnimationFrame(perf.raf);
      state.framePending = false;
    } else {
      tuneCanvas();
      scheduleDraw();
    }
  }, { passive: true });

  window.AtlasIpadUltra = Object.freeze({
    version: perf.version,
    audit: () => ({
      version: perf.version,
      active: root.classList.contains('atlas-ipad-ultra'),
      interacting: perf.interacting,
      dpr: perf.dpr,
      visiblePoints: perf.lastVisiblePoints,
      renderedMarkers: perf.lastRenderedMarkers,
      clusterCell: perf.lastClusterCell,
      markerBudgetIdle: perf.markerBudgetIdle,
      markerBudgetActive: perf.markerBudgetActive,
      backdropMode: 'solid-no-backdrop-filter'
    })
  });

  root.dataset.atlasIpadUltra = perf.version;
  setTimeout(tuneCanvas, 260);
  setTimeout(tuneCanvas, 760);
  scheduleDraw();
})();
