(() => {
  'use strict';

  const ua = navigator.userAgent || '';
  const isIPad = /iPad/i.test(ua) || (navigator.platform === 'MacIntel' && navigator.maxTouchPoints > 1);
  const isLargeTouch = navigator.maxTouchPoints > 1 && Math.min(screen.width, screen.height) >= 700;
  if (!isIPad && !isLargeTouch) return;

  const canvas = document.getElementById('mapCanvas');
  if (!canvas) return;

  const blockedLegacyTypes = new Set(['pointerdown', 'pointermove', 'pointerup', 'pointercancel']);
  const nativeAdd = canvas.addEventListener;
  let intercepting = true;
  let installed = false;

  canvas.addEventListener = function atlasGestureRegistrationGuard(type, listener, options) {
    if (intercepting && blockedLegacyTypes.has(type)) {
      blockedLegacyTypes.delete(type);
      if (!blockedLegacyTypes.size) queueMicrotask(installAuthoritativeController);
      return;
    }
    return nativeAdd.call(this, type, listener, options);
  };

  function restoreCanvasRegistration() {
    if (!intercepting) return;
    intercepting = false;
    delete canvas.addEventListener;
  }

  function installAuthoritativeController() {
    if (installed) return;
    restoreCanvasRegistration();

    if (
      typeof state === 'undefined' ||
      typeof scheduleDraw !== 'function' ||
      typeof minScale !== 'function' ||
      typeof updateZoomLabel !== 'function'
    ) {
      setTimeout(installAuthoritativeController, 0);
      return;
    }

    installed = true;
    installMapGestures();
    installPanelScrolling();
    preventNativePageZoom();
    restorePageViewport();

    document.documentElement.dataset.atlasIpadGestureHotfix = '0.9.4.8-ipad-gesture-2';
  }

  function installMapGestures() {
    const root = document.documentElement;
    const pointers = new Map();
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

    function stop(event) {
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();
    }

    function centerAndDistance() {
      const points = [...pointers.values()];
      if (points.length < 2) return null;
      const first = points[0];
      const second = points[1];
      return {
        centerX: (first.x + second.x) / 2,
        centerY: (first.y + second.y) / 2,
        distance: Math.hypot(first.x - second.x, first.y - second.y)
      };
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

    function release(pointerId) {
      if (!canvas.hasPointerCapture?.(pointerId)) return;
      try { canvas.releasePointerCapture(pointerId); } catch (_) {}
    }

    function reset({ redraw = true, restoreViewport = false } = {}) {
      for (const pointerId of pointers.keys()) release(pointerId);
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

    canvas.addEventListener('pointerdown', event => {
      stop(event);
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
      stop(event);
      const previous = pointers.get(event.pointerId);
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

      if (pointers.size >= 2) {
        if (mode !== 'pinch' || pinchStartDistance < 12) beginPinch();
        const gesture = centerAndDistance();
        if (!gesture || pinchStartDistance < 12) return;

        const ratio = clampValue(gesture.distance / pinchStartDistance, 0.25, 4);
        const nextScale = clampValue(pinchStartScale * ratio, minScale(), state.maxScale);
        if (!Number.isFinite(nextScale)) return;

        state.scale = nextScale;
        state.offsetX = gesture.centerX - pinchMapX * nextScale;
        state.offsetY = gesture.centerY - pinchMapY * nextScale;
        updateZoomLabel();
        scheduleDraw();
        return;
      }

      if (mode !== 'drag') beginDrag({ x: event.clientX, y: event.clientY });
      if (
        Math.hypot(event.clientX - dragStartX, event.clientY - dragStartY) > 4 ||
        Math.hypot(event.clientX - previous.x, event.clientY - previous.y) > 4
      ) moved = true;

      state.offsetX = dragOffsetX + event.clientX - dragStartX;
      state.offsetY = dragOffsetY + event.clientY - dragStartY;
      scheduleDraw();
    }, { capture: true, passive: false });

    function finish(event, cancelled = false) {
      if (!pointers.has(event.pointerId)) return;
      stop(event);
      const wasTap = pointers.size === 1 && mode === 'drag' && !moved && !hadPinch && !cancelled;
      pointers.delete(event.pointerId);
      release(event.pointerId);

      if (wasTap) {
        const target = typeof pickTarget === 'function' ? pickTarget(event.clientX, event.clientY) : null;
        if (target && typeof selectLocation === 'function') selectLocation(target.items[0]);
        else if (typeof closeSheet === 'function') closeSheet();
      }

      if (pointers.size === 1) {
        pinchStartDistance = 0;
        beginDrag([...pointers.values()][0]);
        moved = true;
      } else if (!pointers.size) {
        reset({ redraw: true, restoreViewport: true });
      }
    }

    canvas.addEventListener('pointerup', event => finish(event, false), { capture: true, passive: false });
    canvas.addEventListener('pointercancel', event => finish(event, true), { capture: true, passive: false });
    canvas.addEventListener('lostpointercapture', event => {
      if (!pointers.has(event.pointerId)) return;
      pointers.delete(event.pointerId);
      if (!pointers.size) reset({ redraw: true, restoreViewport: true });
    }, { capture: true, passive: true });

    canvas.addEventListener('touchstart', event => {
      if (event.cancelable) event.preventDefault();
    }, { capture: true, passive: false });
    canvas.addEventListener('touchmove', event => {
      if (event.cancelable) event.preventDefault();
    }, { capture: true, passive: false });

    window.addEventListener('blur', () => reset({ redraw: false, restoreViewport: true }), { passive: true });
    window.addEventListener('pageshow', () => reset({ redraw: true, restoreViewport: true }), { passive: true });
    document.addEventListener('visibilitychange', () => {
      reset({ redraw: !document.hidden, restoreViewport: !document.hidden });
    }, { passive: true });

    window.AtlasIpadGestureHotfix = Object.freeze({
      version: '0.9.4.8-ipad-gesture-2',
      reset: () => reset({ redraw: true, restoreViewport: true }),
      audit: () => ({
        activePointers: pointers.size,
        mode,
        mapScale: state.scale,
        pageScale: window.visualViewport?.scale || 1
      })
    });
  }

  function installPanelScrolling() {
    const scrollers = document.querySelectorAll(
      '#filterPanel,#routePanel,#progressPanel,.sheet-body,.search-results,.evidence-scroll,.settings-scroll'
    );

    scrollers.forEach(scroller => {
      scroller.style.touchAction = 'pan-y';
      scroller.style.webkitOverflowScrolling = 'touch';
      scroller.style.overflowY = 'auto';

      let gesture = null;
      let suppressClick = false;
      let inertiaFrame = 0;

      const stopInertia = () => {
        if (inertiaFrame) cancelAnimationFrame(inertiaFrame);
        inertiaFrame = 0;
      };

      const startInertia = velocity => {
        stopInertia();
        let speed = velocity;
        let previous = performance.now();
        const step = now => {
          const elapsed = Math.min(32, now - previous);
          previous = now;
          if (Math.abs(speed) < 0.015) return;
          const max = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
          const next = Math.max(0, Math.min(max, scroller.scrollTop + speed * elapsed));
          if (next === scroller.scrollTop && (next === 0 || next === max)) return;
          scroller.scrollTop = next;
          speed *= Math.pow(0.92, elapsed / 16.7);
          inertiaFrame = requestAnimationFrame(step);
        };
        inertiaFrame = requestAnimationFrame(step);
      };

      scroller.addEventListener('touchstart', event => {
        if (event.touches.length !== 1) return;
        stopInertia();
        const touch = event.touches[0];
        gesture = {
          startY: touch.clientY,
          lastY: touch.clientY,
          lastTime: performance.now(),
          startScroll: scroller.scrollTop,
          velocity: 0,
          moved: false
        };
      }, { capture: true, passive: true });

      scroller.addEventListener('touchmove', event => {
        if (!gesture || event.touches.length !== 1) return;
        const touch = event.touches[0];
        const delta = gesture.startY - touch.clientY;
        if (!gesture.moved && Math.abs(delta) < 4) return;
        gesture.moved = true;
        if (event.cancelable) event.preventDefault();
        event.stopPropagation();

        const max = Math.max(0, scroller.scrollHeight - scroller.clientHeight);
        scroller.scrollTop = Math.max(0, Math.min(max, gesture.startScroll + delta));

        const now = performance.now();
        const elapsed = Math.max(1, now - gesture.lastTime);
        gesture.velocity = (gesture.lastY - touch.clientY) / elapsed;
        gesture.lastY = touch.clientY;
        gesture.lastTime = now;
      }, { capture: true, passive: false });

      const finishScroll = () => {
        if (!gesture) return;
        if (gesture.moved) {
          suppressClick = true;
          startInertia(gesture.velocity);
        }
        gesture = null;
      };

      scroller.addEventListener('touchend', finishScroll, { capture: true, passive: true });
      scroller.addEventListener('touchcancel', finishScroll, { capture: true, passive: true });
      scroller.addEventListener('click', event => {
        if (!suppressClick) return;
        suppressClick = false;
        event.preventDefault();
        event.stopImmediatePropagation();
      }, { capture: true });
    });
  }

  function preventNativePageZoom() {
    ['gesturestart', 'gesturechange', 'gestureend'].forEach(type => {
      document.addEventListener(type, event => {
        if (event.cancelable) event.preventDefault();
        if (type === 'gestureend') restorePageViewport();
      }, { capture: true, passive: false });
    });
  }

  function restorePageViewport() {
    const canonical = 'width=device-width,initial-scale=1,minimum-scale=1,maximum-scale=1,viewport-fit=cover,user-scalable=no,interactive-widget=resizes-content';
    const viewport = document.querySelector('meta[name="viewport"]');
    if (viewport && viewport.getAttribute('content') !== canonical) viewport.setAttribute('content', canonical);
    window.scrollTo(0, 0);
    document.documentElement.scrollLeft = 0;
    document.documentElement.scrollTop = 0;
    document.body.scrollLeft = 0;
    document.body.scrollTop = 0;
  }

  document.addEventListener('DOMContentLoaded', () => {
    if (!installed) installAuthoritativeController();
  }, { once: true });
})();
