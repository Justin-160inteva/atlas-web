'use strict';
(() => {
  const sheet = document.getElementById('detailSheet');
  const handle = document.getElementById('sheetHandle');
  const body = document.getElementById('detailContent');
  if (!sheet || !handle || !body) return;

  const levels = ['peek', 'mid', 'full'];
  const levelButtons = [...document.querySelectorAll('.sheet-levels button')];
  const drag = {
    active: false,
    moved: false,
    pointerId: null,
    startY: 0,
    startHeight: 0,
    currentHeight: 0,
    lastY: 0,
    lastAt: 0,
    velocityY: 0,
    suppressClick: false,
    snapTimer: 0
  };

  function viewportHeight() {
    return Math.max(320, document.documentElement.clientHeight || window.innerHeight || 720);
  }

  function levelHeights() {
    const viewport = viewportHeight();
    const peek = 180;
    const full = Math.max(peek + 120, Math.min(720, viewport * .86));
    const mid = Math.min(full - 72, Math.max(peek + 96, Math.min(410, viewport * .52)));
    return { peek, mid, full };
  }

  function nearestLevel(height) {
    const heights = levelHeights();
    return levels.reduce((best, level) => (
      Math.abs(heights[level] - height) < Math.abs(heights[best] - height) ? level : best
    ), 'peek');
  }

  function currentLevel() {
    return levels.includes(sheet.dataset.level) ? sheet.dataset.level : 'peek';
  }

  function updateAccessibility(level = currentLevel()) {
    const labels = {
      peek: '基础信息',
      mid: '奖励信息',
      full: '完整详情'
    };
    handle.setAttribute('aria-label', `上下拖动详情卡，当前显示${labels[level]}`);
    handle.setAttribute('aria-controls', 'detailContent');
    handle.setAttribute('aria-expanded', level !== 'peek' ? 'true' : 'false');
    handle.dataset.level = level;
    levelButtons.forEach(button => {
      const buttonLevel = button.dataset.level;
      button.setAttribute('aria-label', labels[buttonLevel] || buttonLevel);
      button.setAttribute('aria-pressed', buttonLevel === level ? 'true' : 'false');
    });
  }

  function sectionTop(level) {
    if (level === 'peek') return 0;
    const selector = level === 'mid' ? '.sheet-highlight' : '.sheet-description';
    const target = body.querySelector(selector);
    if (!target) return body.scrollTop;
    return Math.max(0, target.offsetTop - 10);
  }

  function revealSection(level, smooth = true) {
    window.clearTimeout(drag.snapTimer);
    drag.snapTimer = window.setTimeout(() => {
      body.scrollTo({ top: sectionTop(level), behavior: smooth ? 'smooth' : 'auto' });
    }, smooth ? 190 : 0);
  }

  function setLevelState(level) {
    if (typeof window.setSheetLevel === 'function') {
      window.setSheetLevel(level);
    } else if (typeof setSheetLevel === 'function') {
      setSheetLevel(level);
    } else {
      sheet.dataset.level = level;
      levelButtons.forEach(button => button.classList.toggle('active', button.dataset.level === level));
    }
    updateAccessibility(level);
  }

  function snapTo(level, reveal = true) {
    const targetLevel = levels.includes(level) ? level : nearestLevel(drag.currentHeight || sheet.getBoundingClientRect().height);
    const targetHeight = levelHeights()[targetLevel];
    const currentHeight = sheet.getBoundingClientRect().height;
    let settled = false;
    let fallbackTimer = 0;

    sheet.classList.remove('dragging');
    sheet.classList.add('snapping');
    sheet.style.height = `${currentHeight}px`;
    setLevelState(targetLevel);

    const finish = event => {
      if (settled) return;
      if (event && (event.target !== sheet || event.propertyName !== 'height')) return;
      settled = true;
      window.clearTimeout(fallbackTimer);
      sheet.classList.remove('snapping');
      sheet.style.removeProperty('height');
      sheet.removeEventListener('transitionend', finish);
      updateAccessibility(targetLevel);
      if (reveal) revealSection(targetLevel, true);
    };

    sheet.addEventListener('transitionend', finish);
    requestAnimationFrame(() => {
      sheet.style.height = `${targetHeight}px`;
    });
    fallbackTimer = window.setTimeout(() => finish(), 430);
  }

  function nextLevel(direction) {
    const index = levels.indexOf(currentLevel());
    return levels[Math.max(0, Math.min(levels.length - 1, index + direction))];
  }

  function onPointerDown(event) {
    if (!sheet.classList.contains('open') || event.button > 0) return;
    window.clearTimeout(drag.snapTimer);
    drag.active = true;
    drag.moved = false;
    drag.pointerId = event.pointerId;
    drag.startY = event.clientY;
    drag.startHeight = sheet.getBoundingClientRect().height;
    drag.currentHeight = drag.startHeight;
    drag.lastY = event.clientY;
    drag.lastAt = performance.now();
    drag.velocityY = 0;
    sheet.classList.remove('snapping');
    sheet.classList.add('dragging');
    sheet.style.height = `${drag.startHeight}px`;
    handle.setPointerCapture?.(event.pointerId);
    event.preventDefault();
  }

  function onPointerMove(event) {
    if (!drag.active || event.pointerId !== drag.pointerId) return;
    const now = performance.now();
    const elapsed = Math.max(1, now - drag.lastAt);
    drag.velocityY = (event.clientY - drag.lastY) / elapsed;
    drag.lastY = event.clientY;
    drag.lastAt = now;

    const delta = drag.startY - event.clientY;
    if (Math.abs(delta) > 4) drag.moved = true;
    const heights = levelHeights();
    const nextHeight = Math.max(heights.peek, Math.min(heights.full, drag.startHeight + delta));
    drag.currentHeight = nextHeight;
    sheet.style.height = `${nextHeight}px`;

    const nearest = nearestLevel(nextHeight);
    levelButtons.forEach(button => button.classList.toggle('active', button.dataset.level === nearest));
    event.preventDefault();
  }

  function finishPointer(event) {
    if (!drag.active || event.pointerId !== drag.pointerId) return;
    const moved = drag.moved;
    const velocity = drag.velocityY;
    const height = drag.currentHeight;
    drag.active = false;
    drag.pointerId = null;
    if (handle.hasPointerCapture?.(event.pointerId)) handle.releasePointerCapture(event.pointerId);

    if (!moved) {
      sheet.classList.remove('dragging');
      sheet.style.removeProperty('height');
      updateAccessibility();
      return;
    }

    drag.suppressClick = true;
    requestAnimationFrame(() => { drag.suppressClick = false; });

    let target = nearestLevel(height);
    if (velocity < -.38) target = nextLevel(1);
    if (velocity > .38) target = nextLevel(-1);
    snapTo(target, true);
    event.preventDefault();
  }

  handle.addEventListener('pointerdown', onPointerDown);
  handle.addEventListener('pointermove', onPointerMove);
  handle.addEventListener('pointerup', finishPointer);
  handle.addEventListener('pointercancel', finishPointer);
  handle.addEventListener('click', event => {
    if (drag.suppressClick) {
      event.preventDefault();
      event.stopImmediatePropagation();
      return;
    }
    event.preventDefault();
    event.stopImmediatePropagation();
    snapTo(currentLevel() === 'full' ? 'peek' : nextLevel(1), true);
  }, true);

  handle.addEventListener('keydown', event => {
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      snapTo(nextLevel(1), true);
    } else if (event.key === 'ArrowDown') {
      event.preventDefault();
      snapTo(nextLevel(-1), true);
    } else if (event.key === 'Home') {
      event.preventDefault();
      snapTo('peek', true);
    } else if (event.key === 'End') {
      event.preventDefault();
      snapTo('full', true);
    }
  });

  levelButtons.forEach(button => {
    button.onclick = event => {
      event.preventDefault();
      snapTo(button.dataset.level, true);
    };
  });

  new MutationObserver(() => updateAccessibility()).observe(sheet, {
    attributes: true,
    attributeFilter: ['data-level', 'class']
  });

  new MutationObserver(() => {
    body.scrollTop = 0;
    updateAccessibility('peek');
  }).observe(body, { childList: true });

  window.addEventListener('resize', () => {
    if (!drag.active) sheet.style.removeProperty('height');
  });

  updateAccessibility();
})();
