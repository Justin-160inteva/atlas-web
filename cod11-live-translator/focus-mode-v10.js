'use strict';

(() => {
  const body = document.body;
  const app = document.getElementById('app');
  const stage = document.getElementById('cameraStage');
  const video = document.getElementById('camera');
  const chinese = document.getElementById('chineseText');
  const mainActions = document.querySelector('.main-actions');

  if (!body || !app || !stage || !video || !chinese || !mainActions) return;

  const focusButton = document.createElement('button');
  focusButton.id = 'focusModeBtn';
  focusButton.type = 'button';
  focusButton.textContent = '放大翻译画面';
  mainActions.appendChild(focusButton);

  const exitButton = document.createElement('button');
  exitButton.id = 'exitFocusModeBtn';
  exitButton.type = 'button';
  exitButton.textContent = '退出放大';
  exitButton.setAttribute('aria-label', '退出放大翻译模式');
  stage.appendChild(exitButton);

  const style = document.createElement('style');
  style.textContent = `
    #exitFocusModeBtn {
      display: none;
      position: fixed;
      z-index: 1003;
      top: max(12px, env(safe-area-inset-top));
      right: max(12px, env(safe-area-inset-right));
      min-height: 40px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(0,0,0,.58);
      color: #fff;
      border: 1px solid rgba(255,255,255,.28);
      backdrop-filter: blur(12px);
      -webkit-backdrop-filter: blur(12px);
      font-size: 13px;
      font-weight: 750;
    }

    body.focus-view {
      overflow: hidden;
      overscroll-behavior: none;
      background: #000;
      touch-action: manipulation;
    }

    body.focus-view #app {
      width: 100vw;
      height: 100dvh;
      max-width: none;
      margin: 0;
    }

    body.focus-view .camera-stage {
      position: fixed;
      z-index: 1000;
      inset: 0;
      width: 100vw;
      height: 100dvh;
      min-height: 100dvh;
      background: #000;
    }

    body.focus-view #camera {
      width: 100vw;
      height: 100dvh;
      min-height: 100dvh;
      object-fit: cover;
    }

    body.focus-view .controls,
    body.focus-view .top-bar,
    body.focus-view .quick-toggle,
    body.focus-view .crop-box,
    body.focus-view .empty-state,
    body.focus-view .detected,
    body.focus-view .full-line-label,
    body.focus-view .english,
    body.focus-view .match-meta {
      display: none !important;
    }

    body.focus-view #exitFocusModeBtn {
      display: block;
    }

    body.focus-view .translation-panel {
      position: fixed;
      z-index: 1002;
      left: 0;
      right: 0;
      bottom: 0;
      border: 0;
      border-radius: 0;
      padding:
        clamp(22px, 5vh, 58px)
        max(22px, env(safe-area-inset-right))
        max(28px, calc(env(safe-area-inset-bottom) + 20px))
        max(22px, env(safe-area-inset-left));
      background: linear-gradient(to top, rgba(0,0,0,.92) 0%, rgba(0,0,0,.66) 58%, rgba(0,0,0,0) 100%);
      backdrop-filter: none;
      -webkit-backdrop-filter: none;
      pointer-events: none;
      min-height: 30vh;
      display: flex;
      align-items: flex-end;
      justify-content: center;
    }

    body.focus-view .chinese {
      width: min(94vw, 1200px);
      min-height: 1.25em;
      margin: 0 auto;
      text-align: center;
      color: #fff;
      font-size: clamp(30px, 6.6vw, 72px);
      font-weight: 850;
      line-height: 1.24;
      letter-spacing: .01em;
      text-wrap: balance;
      text-shadow: 0 3px 12px #000, 0 0 3px #000;
      transition: opacity .12s ease, transform .12s ease;
    }

    body.focus-view .chinese.focus-refresh {
      opacity: .58;
      transform: translateY(3px);
    }

    @media (orientation: landscape) {
      body.focus-view .translation-panel {
        min-height: 38vh;
        padding-left: max(6vw, env(safe-area-inset-left));
        padding-right: max(6vw, env(safe-area-inset-right));
      }

      body.focus-view .chinese {
        width: min(88vw, 1400px);
        font-size: clamp(28px, 4.7vw, 64px);
      }
    }
  `;
  document.head.appendChild(style);

  async function enterFocusMode() {
    if (!state?.stream) {
      alert('请先开启摄像头，再进入放大翻译模式。');
      return;
    }

    body.classList.add('focus-view');
    focusButton.textContent = '已进入放大模式';
    chinese.textContent = chinese.textContent || '等待翻译……';

    try {
      if (document.documentElement.requestFullscreen && !document.fullscreenElement) {
        await document.documentElement.requestFullscreen({ navigationUI: 'hide' });
      }
    } catch (_) {}
  }

  async function exitFocusMode() {
    body.classList.remove('focus-view');
    focusButton.textContent = '放大翻译画面';
    try {
      if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen();
    } catch (_) {}
  }

  focusButton.addEventListener('click', enterFocusMode);
  exitButton.addEventListener('click', exitFocusMode);

  document.addEventListener('fullscreenchange', () => {
    if (!document.fullscreenElement && body.classList.contains('focus-view')) {
      body.classList.remove('focus-view');
      focusButton.textContent = '放大翻译画面';
    }
  });

  let lastChinese = chinese.textContent;
  const observer = new MutationObserver(() => {
    const next = chinese.textContent;
    if (!body.classList.contains('focus-view') || !next || next === lastChinese) return;
    lastChinese = next;
    chinese.classList.add('focus-refresh');
    requestAnimationFrame(() => requestAnimationFrame(() => chinese.classList.remove('focus-refresh')));
  });
  observer.observe(chinese, { childList: true, characterData: true, subtree: true });

  window.addEventListener('pagehide', () => body.classList.remove('focus-view'));
})();
