(() => {
  'use strict';

  const LEVELS = ['peek', 'mid', 'full'];
  const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

  function install() {
    const sheet = document.getElementById('detailSheet');
    const handle = document.getElementById('sheetHandle');
    if (!sheet || !handle || sheet.dataset.smoothDragInstalled === 'true') return;

    sheet.dataset.smoothDragInstalled = 'true';
    document.querySelector('.sheet-levels')?.remove();

    // app.js installs a click-to-cycle handler. The transparent drag surface
    // becomes authoritative instead, while a light tap still advances a level.
    handle.onclick = null;
    handle.setAttribute('aria-label', '上下拖动调整详情高度');
    handle.setAttribute('aria-expanded', 'false');

    let gesture = null;
    let animationFrame = 0;
    let pendingHeight = null;
    let cleanupTimer = 0;

    function viewportHeight() {
      return window.visualViewport?.height || window.innerHeight || 768;
    }

    function heights() {
      const viewport = viewportHeight();
      const peek = 180;
      const full = Math.max(peek, Math.min(720, viewport * .86));
      const mid = clamp(Math.min(410, viewport * .52), peek, full);
      return { peek, mid, full };
    }

    function currentHeight() {
      const inline = Number.parseFloat(sheet.style.height);
      return Number.isFinite(inline) ? inline : sheet.getBoundingClientRect().height;
    }

    function renderHeight(value) {
      pendingHeight = value;
      if (animationFrame) return;
      animationFrame = requestAnimationFrame(() => {
        animationFrame = 0;
        sheet.style.height = `${pendingHeight}px`;
      });
    }

    function nearestLevel(value) {
      const map = heights();
      return LEVELS.reduce((best, level) => (
        Math.abs(map[level] - value) < Math.abs(map[best] - value) ? level : best
      ), 'peek');
    }

    function nextLevel(value, direction) {
      const map = heights();
      if (direction > 0) {
        return LEVELS.find(level => map[level] > value + 8) || 'full';
      }
      return [...LEVELS].reverse().find(level => map[level] < value - 8) || 'peek';
    }

    function finishSnap(level, fromHeight = currentHeight()) {
      const map = heights();
      const target = map[level] ?? map.peek;
      const starting = clamp(fromHeight, map.peek, map.full);

      clearTimeout(cleanupTimer);
      sheet.classList.remove('dragging');
      sheet.dataset.level = level;
      handle.setAttribute('aria-expanded', level === 'peek' ? 'false' : 'true');
      sheet.style.height = `${starting}px`;

      requestAnimationFrame(() => {
        sheet.style.height = `${target}px`;
      });

      const clearInlineHeight = event => {
        if (event && event.target !== sheet) return;
        if (event && event.propertyName !== 'height') return;
        sheet.removeEventListener('transitionend', clearInlineHeight);
        sheet.style.removeProperty('height');
        clearTimeout(cleanupTimer);
      };

      sheet.addEventListener('transitionend', clearInlineHeight);
      cleanupTimer = window.setTimeout(() => clearInlineHeight(), 460);
      sheet.dispatchEvent(new CustomEvent('atlas:sheet-level-change', { detail: { level } }));
    }

    function releaseCapture(pointerId) {
      if (!handle.hasPointerCapture?.(pointerId)) return;
      try { handle.releasePointerCapture(pointerId); } catch (_) {}
    }

    function endGesture(event, cancelled = false) {
      if (!gesture || event.pointerId !== gesture.pointerId) return;
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();

      if (animationFrame) {
        cancelAnimationFrame(animationFrame);
        animationFrame = 0;
        if (pendingHeight != null) sheet.style.height = `${pendingHeight}px`;
      }

      const map = heights();
      const height = clamp(currentHeight(), map.peek, map.full);
      const samples = gesture.samples;
      const first = samples[0];
      const last = samples[samples.length - 1];
      const elapsed = Math.max(1, last.t - first.t);
      const velocity = (last.h - first.h) / elapsed;
      const tap = !cancelled && !gesture.moved && performance.now() - gesture.startedAt < 320;

      let level;
      if (tap) {
        const active = LEVELS.includes(sheet.dataset.level) ? sheet.dataset.level : nearestLevel(height);
        level = LEVELS[(LEVELS.indexOf(active) + 1) % LEVELS.length];
      } else if (!cancelled && Math.abs(velocity) >= .28) {
        level = nextLevel(height, velocity > 0 ? 1 : -1);
      } else {
        level = nearestLevel(height);
      }

      const pointerId = gesture.pointerId;
      gesture = null;
      releaseCapture(pointerId);
      finishSnap(level, height);
    }

    handle.addEventListener('pointerdown', event => {
      if (!sheet.classList.contains('open')) return;
      if (event.pointerType === 'mouse' && event.button !== 0) return;
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();

      clearTimeout(cleanupTimer);
      const startHeight = currentHeight();
      const now = performance.now();
      gesture = {
        pointerId: event.pointerId,
        startY: event.clientY,
        startHeight,
        startedAt: now,
        moved: false,
        samples: [{ t: now, h: startHeight }]
      };

      sheet.classList.add('dragging');
      sheet.style.height = `${startHeight}px`;
      try { handle.setPointerCapture(event.pointerId); } catch (_) {}
    }, { passive: false });

    handle.addEventListener('pointermove', event => {
      if (!gesture || event.pointerId !== gesture.pointerId) return;
      if (event.cancelable) event.preventDefault();
      event.stopPropagation();

      const map = heights();
      const delta = gesture.startY - event.clientY;
      let height = gesture.startHeight + delta;

      if (height < map.peek) height = map.peek - (map.peek - height) * .16;
      if (height > map.full) height = map.full + (height - map.full) * .12;

      if (Math.abs(delta) > 4) gesture.moved = true;
      renderHeight(height);

      const now = performance.now();
      gesture.samples.push({ t: now, h: height });
      gesture.samples = gesture.samples.filter(sample => now - sample.t <= 120).slice(-6);
    }, { passive: false });

    handle.addEventListener('pointerup', event => endGesture(event, false), { passive: false });
    handle.addEventListener('pointercancel', event => endGesture(event, true), { passive: false });
    handle.addEventListener('lostpointercapture', event => {
      if (gesture && event.pointerId === gesture.pointerId) endGesture(event, true);
    }, { passive: false });

    handle.addEventListener('keydown', event => {
      if (event.key !== 'Enter' && event.key !== ' ') return;
      event.preventDefault();
      const active = LEVELS.includes(sheet.dataset.level) ? sheet.dataset.level : 'peek';
      finishSnap(LEVELS[(LEVELS.indexOf(active) + 1) % LEVELS.length]);
    });

    window.addEventListener('resize', () => {
      if (!sheet.classList.contains('open') || sheet.classList.contains('dragging')) return;
      const level = LEVELS.includes(sheet.dataset.level) ? sheet.dataset.level : 'peek';
      finishSnap(level);
    }, { passive: true });

    window.AtlasSheetDragPatch = Object.freeze({
      version: '0.9.4.8-sheet-drag-1',
      snapTo: level => {
        if (!LEVELS.includes(level)) return false;
        finishSnap(level);
        return true;
      },
      levels: () => ({ ...heights() })
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', install, { once: true });
  } else {
    queueMicrotask(install);
  }
})();
