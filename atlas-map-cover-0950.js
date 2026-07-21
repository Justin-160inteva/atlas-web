(() => {
  'use strict';

  const root = document.documentElement;
  const WORLD_SIZE = 4096;
  const OVERSCAN = 1.02;
  const MANUAL_MIN_RATIO = 0.25;
  let installed = false;
  let installTimer = 0;

  function metrics() {
    const measured = window.AtlasViewport?.measure?.();
    return {
      width: Math.max(1, Math.round(Number(measured?.width || window.innerWidth || 1))),
      height: Math.max(1, Math.round(Number(measured?.height || window.innerHeight || 1)))
    };
  }

  function coverScale(viewport = metrics()) {
    return Math.max(viewport.width / WORLD_SIZE, viewport.height / WORLD_SIZE) * OVERSCAN;
  }

  function manualMinimumScale(viewport = metrics()) {
    return coverScale(viewport) * MANUAL_MIN_RATIO;
  }

  function updateLabel() {
    const label = document.getElementById('zoomLabel');
    if (!label || typeof state === 'undefined') return;
    const fit = coverScale();
    const ratio = fit > 0 ? state.scale / fit : 1;
    label.textContent = `×${ratio.toFixed(ratio < 10 ? 2 : 0)}`;
  }

  function fitCover() {
    if (typeof state === 'undefined') return false;
    const viewport = metrics();
    const nextScale = coverScale(viewport);
    state.scale = nextScale;
    state.offsetX = (viewport.width - WORLD_SIZE * nextScale) / 2;
    state.offsetY = (viewport.height - WORLD_SIZE * nextScale) / 2;
    updateLabel();
    if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
    root.dataset.atlasMapCoverReady = 'true';
    root.dataset.atlasMapCoverScale = String(nextScale);
    root.dataset.atlasMapManualMinimumScale = String(manualMinimumScale(viewport));
    return true;
  }

  function clampToManualMinimum(anchorX, anchorY) {
    if (typeof state === 'undefined' || !Number.isFinite(state.scale) || state.scale <= 0) return;
    const viewport = metrics();
    const minimum = manualMinimumScale(viewport);
    if (state.scale >= minimum) return;
    const pointX = Number.isFinite(anchorX) ? anchorX : viewport.width / 2;
    const pointY = Number.isFinite(anchorY) ? anchorY : viewport.height / 2;
    const worldX = (pointX - state.offsetX) / state.scale;
    const worldY = (pointY - state.offsetY) / state.scale;
    state.scale = minimum;
    state.offsetX = pointX - worldX * minimum;
    state.offsetY = pointY - worldY * minimum;
    updateLabel();
    if (typeof window.scheduleDraw === 'function') window.scheduleDraw();
  }

  function install() {
    if (installed) return true;
    if (
      root.dataset.atlasMapViewportHooks !== 'true' ||
      typeof window.fitMap !== 'function' ||
      typeof window.zoomAt !== 'function' ||
      typeof state === 'undefined'
    ) {
      clearTimeout(installTimer);
      installTimer = window.setTimeout(install, 30);
      return false;
    }

    const originalZoomAt = window.zoomAt;
    window.fitMap = fitCover;
    window.updateZoomLabel = updateLabel;
    window.zoomAt = function coverFitManualZoomAt(factor, x, y) {
      originalZoomAt(factor, x, y);
      clampToManualMinimum(x, y);
      updateLabel();
    };

    const zoomInButton = document.getElementById('zoomIn');
    const zoomOutButton = document.getElementById('zoomOut');
    if (zoomInButton) zoomInButton.onclick = () => window.zoomAt(1.25);
    if (zoomOutButton) zoomOutButton.onclick = () => window.zoomAt(0.8);

    const mapCanvas = document.getElementById('mapCanvas');
    if (mapCanvas) {
      mapCanvas.addEventListener('wheel', event => {
        clampToManualMinimum(event.clientX, event.clientY);
        updateLabel();
      }, { passive: true });
      mapCanvas.addEventListener('pointermove', () => {
        if (state.pointers?.size !== 2) return;
        const points = [...state.pointers.values()];
        const centerX = (points[0].x + points[1].x) / 2;
        const centerY = (points[0].y + points[1].y) / 2;
        clampToManualMinimum(centerX, centerY);
        updateLabel();
      });
    }

    ['resetView', 'brandBtn', 'locateBtn'].forEach(id => {
      const button = document.getElementById(id);
      if (!button) return;
      button.addEventListener('click', () => requestAnimationFrame(fitCover));
    });

    root.addEventListener('atlas:viewportchange', event => {
      const reason = String(event.detail?.reason || '');
      if (/initial|orientation|page-show|bfcache|visibility|load/.test(reason)) {
        requestAnimationFrame(fitCover);
      }
    });

    installed = true;
    root.dataset.atlasMapCoverController = window.AtlasRelease?.version || '0.9.4.9';
    fitCover();
    return true;
  }

  window.AtlasMapCover = {
    fit: fitCover,
    coverScale,
    manualMinimumScale,
    minimumScale: manualMinimumScale,
    manualMinimumRatio: MANUAL_MIN_RATIO,
    ready: () => installed
  };

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', install, { once: true })
    : install();
})();
