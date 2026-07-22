(() => {
  'use strict';

  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isLargeTouch = navigator.maxTouchPoints > 1 && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isLargeTouch) return;

  if (
    typeof canvas === 'undefined' ||
    typeof state === 'undefined' ||
    typeof scheduleDraw !== 'function' ||
    typeof minScale !== 'function' ||
    typeof updateZoomLabel !== 'function'
  ) return;

  const root = document.documentElement;
  const pointers = new Map();
  const canonicalViewport = 'width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no,interactive-widget=resizes-content';

  let mode = 'idle';
  let moved = false;
  let hadPinch = false;
  let dragStartX = 0;
  let dragStartY = 0;
  let dragOffsetX = 0;
  let dragOffsetY = 0;
  let pinchStartDistance = 0;
  let pinchStartScale = 1;
  let pinchMapX = 0;
  let pinchMapY = 0;

  const clampValue = (value, min, max) => Math.max(min, Math.min(max, value));

  function prevent(event) {
    if (event.cancelable) event.preventDefault();
    event.stopImmediatePropagation();
  }

  function centerAndDistance() {
    const points = [...pointers.values()];
    if (points.length < 2) return null;
    const first = points[0];
    const second = points[1];
    const centerX = (first.x + second.x) / 2;
    const centerY = (first.y + second.y) / 2;
    const distance = Math.hypot(first.x - second.x, first.y - second.y);
    return { centerX, centerY, distance };
  }

  function beginDrag(point) {
    mode = 'drag';
    dragStartX = point.x;
    dragStartY = point.y;
    dragOffsetX = state.offsetX;
    dragOffsetY = state.offsetY;
  }

  function beginPinch() {
    const gesture = centerAndDistance();
    if (!gesture || gesture.distance < 12) return;
    mode = 'pinch';
    moved = true;
    hadPinch = true;
    pinchStartDistance = gesture.distance;
    pinchStartScale = Math.max(0.0001, state.scale);
    pinchMapX = (gesture.centerX - state.offsetX) / pinchStartScale;
    pinchMapY = (gesture.centerY - state.offsetY) / pinchStartScale;
  }

  function releasePointer(pointerId) {
    if (canvas.hasPointerCapture?.(pointerId)) {
      try { canvas.releasePointerCapture(pointerId); } catch (_) {}
    }
  }

  function resetGesture({ redraw = true, restoreViewport = false } = {}) {
    for (const pointerId of pointers.keys()) releasePointer(pointerId);
    pointers.clear();
    state.pointers?.clear?.();
    state.pinchDistance = 0;
    state.drag = false;
    state.moved = false;
    mode = 'idle';
    moved = false;
    hadPinch = false;
    pinchStartDistance = 0;
    root.classList.remove('atlas-gesture-active');
    if (restoreViewport) restorePageViewport();
    if (redraw) scheduleDraw();
  }

  function restorePageViewport() {
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport && viewport.getAttribute('content') !== canonicalViewport) {
      viewport.setAttribute('content', canonicalViewport);
    }
    const pageScaled = Math.abs((window.visualViewport?.scale || 1) - 1) > 0.01;
    if (pageScaled && viewport?.parentNode) {
      const replacement = viewport.cloneNode(true);
      replacement.setAttribute('content', canonicalViewport);
      viewport.parentNode.replaceChild(replacement, viewport);
    }
    window.scrollTo(0, 0);
    document.documentElement.scrollLeft = 0;
    document.documentElement.scrollTop = 0;
    document.body.scrollLeft = 0;
    document.body.scrollTop = 0;
  }

  canvas.addEventListener('pointerdown', event => {
    prevent(event);
    restorePageViewport();
    try { canvas.setPointerCapture(event.pointerId); } catch (_) {}
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    root.classList.add('atlas-gesture-active');

    if (pointers.size === 1) {
      moved = false;
      hadPinch = false;
      beginDrag({ x: event.clientX, y: event.clientY });
    } else if (pointers.size === 2) {
      beginPinch();
    }
  }, { capture: true, passive: false });

  canvas.addEventListener('pointermove', event => {
    if (!pointers.has(event.pointerId)) return;
    prevent(event);
    const previous = pointers.get(event.pointerId);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

    if (pointers.size >= 2) {
      if (mode !== 'pinch' || pinchStartDistance < 12) beginPinch();
      const gesture = centerAndDistance();
      if (!gesture || pinchStartDistance < 12) return;
      const rawRatio = gesture.distance / pinchStartDistance;
      const safeRatio = clampValue(rawRatio, 0.2, 5);
      const nextScale = clampValue(pinchStartScale * safeRatio, minScale(), state.maxScale);
      if (!Number.isFinite(nextScale)) return;
      state.scale = nextScale;
      state.offsetX = gesture.centerX - pinchMapX * nextScale;
      state.offsetY = gesture.centerY - pinchMapY * nextScale;
      updateZoomLabel();
      scheduleDraw();
      return;
    }

    if (mode !== 'drag') beginDrag({ x: event.clientX, y: event.clientY });
    if (Math.hypot(event.clientX - dragStartX, event.clientY - dragStartY) > 4 ||
        Math.hypot(event.clientX - previous.x, event.clientY - previous.y) > 4) {
      moved = true;
    }
    state.offsetX = dragOffsetX + event.clientX - dragStartX;
    state.offsetY = dragOffsetY + event.clientY - dragStartY;
    scheduleDraw();
  }, { capture: true, passive: false });

  function finishPointer(event, cancelled = false) {
    if (!pointers.has(event.pointerId)) return;
    prevent(event);
    const wasSingleTap = pointers.size === 1 && mode === 'drag' && !moved && !hadPinch && !cancelled;
    pointers.delete(event.pointerId);
    releasePointer(event.pointerId);

    if (wasSingleTap) {
      const target = typeof pickTarget === 'function' ? pickTarget(event.clientX, event.clientY) : null;
      if (target && typeof selectLocation === 'function') selectLocation(target.items[0]);
      else if (typeof closeSheet === 'function') closeSheet();
    }

    if (pointers.size === 1) {
      const remaining = [...pointers.values()][0];
      pinchStartDistance = 0;
      beginDrag(remaining);
      moved = true;
    } else if (pointers.size === 0) {
      resetGesture({ redraw: true, restoreViewport: true });
    }
  }

  canvas.addEventListener('pointerup', event => finishPointer(event, false), { capture: true, passive: false });
  canvas.addEventListener('pointercancel', event => finishPointer(event, true), { capture: true, passive: false });
  canvas.addEventListener('lostpointercapture', event => {
    if (pointers.has(event.pointerId)) {
      pointers.delete(event.pointerId);
      if (!pointers.size) resetGesture({ redraw: true, restoreViewport: true });
    }
  }, { capture: true, passive: true });

  canvas.addEventListener('touchstart', event => {
    if (event.touches.length > 1 && event.cancelable) event.preventDefault();
  }, { capture: true, passive: false });
  canvas.addEventListener('touchmove', event => {
    if (event.touches.length > 1 && event.cancelable) event.preventDefault();
  }, { capture: true, passive: false });

  ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
    document.addEventListener(type, event => {
      if (event.cancelable) event.preventDefault();
      if (type === 'gestureend') restorePageViewport();
    }, { capture: true, passive: false });
  });

  window.addEventListener('blur', () => resetGesture({ redraw: false, restoreViewport: true }), { passive: true });
  window.addEventListener('pageshow', () => resetGesture({ redraw: true, restoreViewport: true }), { passive: true });
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) resetGesture({ redraw: false, restoreViewport: false });
    else resetGesture({ redraw: true, restoreViewport: true });
  }, { passive: true });

  restorePageViewport();
  root.dataset.atlasIpadGestureHotfix = '0.9.4.8-ipad-gesture-1';
  window.AtlasIpadGestureHotfix = Object.freeze({
    version: '0.9.4.8-ipad-gesture-1',
    reset: () => resetGesture({ redraw: true, restoreViewport: true }),
    audit: () => ({
      activePointers: pointers.size,
      mode,
      mapScale: state.scale,
      pageScale: window.visualViewport?.scale || 1,
      pageOffsetLeft: window.visualViewport?.offsetLeft || 0,
      pageOffsetTop: window.visualViewport?.offsetTop || 0
    })
  });
})();
