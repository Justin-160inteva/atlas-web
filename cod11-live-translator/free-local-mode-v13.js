'use strict';

(() => {
  const VERSION = '13.0';
  const cloudDetails = document.getElementById('realtimeCloudSettings');
  const controls = document.querySelector('.controls');
  const firstDetails = controls?.querySelector('details');

  const modePanel = document.createElement('details');
  modePanel.open = true;
  modePanel.id = 'recognitionModeSettings';
  modePanel.innerHTML = `
    <summary>识别模式</summary>
    <div class="control-row" style="margin-top:12px">
      <button id="useLocalModeBtn" class="primary">免费本地模式</button>
      <button id="useCloudModeBtn">云端增强模式（需 API 额度）</button>
    </div>
    <p id="modeDescription" class="hint">当前使用免费本地 OCR + 第 6 关字幕字典，不调用 OpenAI API，不产生费用。</p>
  `;
  if (firstDetails?.parentNode) firstDetails.parentNode.insertBefore(modePanel, firstDetails);

  const localBtn = document.getElementById('useLocalModeBtn');
  const cloudBtn = document.getElementById('useCloudModeBtn');
  const description = document.getElementById('modeDescription');
  let mode = localStorage.getItem('cod11-recognition-mode') === 'cloud' ? 'cloud' : 'local';

  function cloneAction(id, text, handler) {
    const old = document.getElementById(id);
    if (!old) return null;
    const next = old.cloneNode(true);
    next.textContent = text;
    old.replaceWith(next);
    next.addEventListener('click', handler);
    return next;
  }

  function prepareLocalControls() {
    if (els.scanInterval) {
      els.scanInterval.disabled = false;
      els.scanInterval.innerHTML = `
        <option value="350">0.35 秒（最快）</option>
        <option value="500" selected>0.5 秒（推荐）</option>
        <option value="750">0.75 秒</option>
        <option value="1000">1 秒（省电）</option>
      `;
    }
    if (els.cloudFallback) {
      els.cloudFallback.disabled = false;
      els.cloudFallback.checked = false;
      const label = els.cloudFallback.closest('label');
      if (label) label.lastChild.textContent = ' 未命中字典时尝试免费联网翻译（可关闭）';
    }
  }

  function activateLocal() {
    mode = 'local';
    localStorage.setItem('cod11-recognition-mode', mode);
    if (state.running) pauseRecognition();
    prepareLocalControls();
    els.recognize = cloneAction('recognizeBtn', '开始免费本地翻译', startRecognition);
    els.pause = cloneAction('pauseBtn', '暂停本地翻译', pauseRecognition);
    els.quickToggle = cloneAction('quickToggleBtn', '开始本地翻译', () => state.running ? pauseRecognition() : startRecognition());
    els.recognize.disabled = !state.stream;
    els.pause.disabled = true;
    if (els.quickToggle) els.quickToggle.hidden = !state.stream;
    if (cloudDetails) cloudDetails.open = false;
    localBtn.classList.add('primary');
    cloudBtn.classList.remove('primary');
    description.textContent = '当前使用免费本地 OCR + 第 6 关字幕字典，不调用 OpenAI API，不产生费用。未收录字幕可选用免费联网翻译。';
    document.title = `COD11 免费本地字幕翻译器 V${VERSION}`;
    const heading = document.querySelector('.empty-state h1');
    if (heading) heading.textContent = `COD11 免费本地字幕翻译器 V${VERSION}`;
    if (els.statusText) els.statusText.textContent = `未启动 · V${VERSION}免费本地识别`;
    if (els.meta) els.meta.textContent = `V${VERSION}：本地 OCR + 字幕字典，不产生 API 费用`;
  }

  function activateCloud() {
    mode = 'cloud';
    localStorage.setItem('cod11-recognition-mode', mode);
    localBtn.classList.remove('primary');
    cloudBtn.classList.add('primary');
    description.textContent = '云端增强模式会调用 OpenAI API，账户必须有可用额度。';
    if (cloudDetails) {
      cloudDetails.open = true;
      cloudDetails.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
    alert('云端增强模式需要 OpenAI API 可用额度。当前没有额度时，请继续使用免费本地模式。');
  }

  localBtn.addEventListener('click', activateLocal);
  cloudBtn.addEventListener('click', activateCloud);

  const note = document.querySelector('.privacy-note');
  if (note) note.textContent = '免费本地模式只在设备上处理绿色框中的字幕画面；只有主动切换云端增强模式时才会发送裁切画面。';

  // 没有 API 额度时始终安全地落到本地模式；用户以后仍可打开云端设置。
  activateLocal();
})();
