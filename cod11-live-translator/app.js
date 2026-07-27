'use strict';

const $ = (id) => document.getElementById(id);
const els = {
  camera: $('camera'), canvas: $('frameCanvas'), stage: $('cameraStage'), empty: $('emptyState'), crop: $('cropBox'),
  startCamera: $('startCameraBtn'), recognize: $('recognizeBtn'), pause: $('pauseBtn'), speakAgain: $('speakAgainBtn'), quickToggle: $('quickToggleBtn'),
  switchCamera: $('switchCameraBtn'), torch: $('torchBtn'), resetCrop: $('resetCropBtn'), statusDot: $('statusDot'),
  statusText: $('statusText'), fpsText: $('fpsText'), english: $('englishText'), chinese: $('chineseText'), meta: $('matchMeta'),
  scanInterval: $('scanInterval'), speechRate: $('speechRate'), speechRateValue: $('speechRateValue'), autoSpeak: $('autoSpeak'),
  finishBeforeNext: $('finishBeforeNext'), cloudFallback: $('cloudFallback'), highContrast: $('highContrast'), keepAwake: $('keepAwake'),
  libraryFile: $('libraryFile'), exportBtn: $('exportBtn'), clearLibrary: $('clearLibraryBtn'), chapter: $('chapterSelect'),
  threshold: $('matchThreshold'), thresholdValue: $('matchThresholdValue'), libraryInfo: $('libraryInfo'),
  history: $('historyList'), clearHistory: $('clearHistoryBtn'), installStatus: $('installStatus')
};

const DEMO_LIBRARY = [
  { chapter: '演示', en: 'Keep your eyes open.', zh: '提高警惕。' },
  { chapter: '演示', en: 'We are going in hot.', zh: '我们要直接强攻。' },
  { chapter: '演示', en: 'Move! Move! Move!', zh: '快走！快走！快走！' },
  { chapter: '演示', en: 'Stay where you are!', zh: '待在原地！' },
  { chapter: '演示', en: 'We are out of time.', zh: '我们没时间了。' },
  { chapter: '演示', en: 'You have got to jump now.', zh: '你现在必须跳下去。' }
];

const state = {
  stream: null,
  facingMode: 'environment',
  running: false,
  busy: false,
  timer: null,
  worker: null,
  lastRaw: '',
  lastAccepted: '',
  lastChinese: '',
  lastAcceptedAt: 0,
  library: loadLibrary(),
  speechQueue: [],
  speaking: false,
  torchOn: false,
  frameTimes: [],
  wakeLock: null,
  speechUnlocked: false
};

function isStandaloneMode() {
  return window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true;
}
function refreshInstallStatus() {
  if (!els.installStatus) return;
  if (isStandaloneMode()) {
    els.installStatus.textContent = '已从主屏幕模式启动。摄像头、朗读和全屏显示均可使用。';
    els.installStatus.classList.add('installed');
  } else {
    els.installStatus.textContent = '当前在浏览器中运行。使用 Safari 的“添加到主屏幕”即可安装。';
    els.installStatus.classList.remove('installed');
  }
}
function unlockSpeech() {
  if (state.speechUnlocked || !('speechSynthesis' in window)) return;
  try {
    const warmup = new SpeechSynthesisUtterance(' ');
    warmup.volume = 0;
    warmup.rate = 10;
    speechSynthesis.speak(warmup);
    state.speechUnlocked = true;
  } catch (_) {}
}
async function requestWakeLock() {
  if (!els.keepAwake?.checked || !('wakeLock' in navigator) || document.visibilityState !== 'visible') return;
  try {
    if (!state.wakeLock) {
      state.wakeLock = await navigator.wakeLock.request('screen');
      state.wakeLock.addEventListener('release', () => { state.wakeLock = null; });
    }
  } catch (_) {}
}
async function releaseWakeLock() {
  try { await state.wakeLock?.release(); } catch (_) {}
  state.wakeLock = null;
}

function loadLibrary() {
  try {
    const saved = JSON.parse(localStorage.getItem('cod11-subtitle-library') || 'null');
    if (Array.isArray(saved) && saved.length) return saved;
  } catch (_) {}
  return DEMO_LIBRARY.slice();
}
function saveLibrary() {
  localStorage.setItem('cod11-subtitle-library', JSON.stringify(state.library));
  refreshLibraryUI();
}
function normalizeText(s) {
  return String(s || '')
    .replace(/[|“”‘’]/g, ' ')
    .replace(/[^a-zA-Z0-9'!?.,\-\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}
function comparable(s) {
  return normalizeText(s).toLowerCase().replace(/[^a-z0-9]+/g, ' ').trim();
}
function levenshtein(a, b) {
  if (a === b) return 0;
  if (!a.length) return b.length;
  if (!b.length) return a.length;
  const prev = Array.from({ length: b.length + 1 }, (_, i) => i);
  const curr = new Array(b.length + 1);
  for (let i = 1; i <= a.length; i++) {
    curr[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const cost = a[i - 1] === b[j - 1] ? 0 : 1;
      curr[j] = Math.min(curr[j - 1] + 1, prev[j] + 1, prev[j - 1] + cost);
    }
    for (let j = 0; j <= b.length; j++) prev[j] = curr[j];
  }
  return prev[b.length];
}
function similarity(a, b) {
  a = comparable(a); b = comparable(b);
  if (!a || !b) return 0;
  const lev = 1 - levenshtein(a, b) / Math.max(a.length, b.length);
  const aw = new Set(a.split(' '));
  const bw = new Set(b.split(' '));
  let overlap = 0;
  aw.forEach(w => { if (bw.has(w)) overlap++; });
  const jaccard = overlap / Math.max(1, new Set([...aw, ...bw]).size);
  return lev * 0.72 + jaccard * 0.28;
}
function activeLibrary() {
  const ch = els.chapter.value;
  return ch === 'all' ? state.library : state.library.filter(x => x.chapter === ch);
}
function findLocalMatch(text) {
  let best = null;
  let score = 0;
  for (const item of activeLibrary()) {
    const s = similarity(text, item.en);
    if (s > score) { score = s; best = item; }
  }
  const threshold = Number(els.threshold.value);
  return score >= threshold ? { item: best, score } : null;
}
function isLikelySubtitle(text) {
  const clean = normalizeText(text);
  if (clean.length < 3 || clean.length > 180) return false;
  const letters = (clean.match(/[A-Za-z]/g) || []).length;
  if (letters / clean.length < 0.48) return false;
  const words = clean.split(/\s+/).filter(Boolean);
  return words.length >= 1 && words.length <= 30;
}
function isDuplicate(text) {
  const now = Date.now();
  if (!state.lastAccepted) return false;
  const score = similarity(text, state.lastAccepted);
  return score > 0.88 && now - state.lastAcceptedAt < 6500;
}

async function startCamera() {
  stopCamera();
  try {
    const constraints = {
      audio: false,
      video: {
        facingMode: { ideal: state.facingMode },
        width: { ideal: 1920 }, height: { ideal: 1080 },
        frameRate: { ideal: 30, max: 60 }
      }
    };
    state.stream = await navigator.mediaDevices.getUserMedia(constraints);
    els.camera.srcObject = state.stream;
    await els.camera.play();
    els.empty.style.display = 'none';
    els.crop.style.display = 'block';
    els.recognize.disabled = false;
    els.quickToggle.hidden = false;
    els.quickToggle.textContent = '开始翻译';
    els.switchCamera.disabled = false;
    const track = state.stream.getVideoTracks()[0];
    const caps = track.getCapabilities?.() || {};
    els.torch.disabled = !caps.torch;
    setStatus('摄像头已开启', false);
  } catch (err) {
    setStatus('无法开启摄像头', false);
    alert('摄像头开启失败。请使用 HTTPS 打开网站，并允许摄像头权限。\n\n' + err.message);
  }
}
function stopCamera() {
  if (state.stream) state.stream.getTracks().forEach(t => t.stop());
  state.stream = null;
}
async function toggleTorch() {
  const track = state.stream?.getVideoTracks()[0];
  if (!track) return;
  state.torchOn = !state.torchOn;
  try {
    await track.applyConstraints({ advanced: [{ torch: state.torchOn }] });
    els.torch.textContent = state.torchOn ? '关闭手电筒' : '手电筒';
  } catch (_) { state.torchOn = false; }
}

async function ensureWorker() {
  if (state.worker) return state.worker;
  if (!window.Tesseract) throw new Error('OCR 引擎未加载，请检查网络。');
  setStatus('正在加载英文识别引擎…', false);
  state.worker = await Tesseract.createWorker('eng', 1, {
    logger: m => {
      if (m.status === 'recognizing text') setStatus(`正在识别 ${Math.round((m.progress || 0) * 100)}%`, true);
    }
  });
  await state.worker.setParameters({
    tessedit_pageseg_mode: Tesseract.PSM.SINGLE_BLOCK,
    preserve_interword_spaces: '1',
    user_defined_dpi: '180'
  });
  return state.worker;
}

function cropCoordinates() {
  const vr = els.camera.getBoundingClientRect();
  const cr = els.crop.getBoundingClientRect();
  const videoW = els.camera.videoWidth || 1920;
  const videoH = els.camera.videoHeight || 1080;
  const displayedAspect = vr.width / vr.height;
  const videoAspect = videoW / videoH;
  let contentW, contentH, offsetX = 0, offsetY = 0;
  if (videoAspect > displayedAspect) {
    contentH = vr.height;
    contentW = contentH * videoAspect;
    offsetX = (contentW - vr.width) / 2;
  } else {
    contentW = vr.width;
    contentH = contentW / videoAspect;
    offsetY = (contentH - vr.height) / 2;
  }
  const x = ((cr.left - vr.left + offsetX) / contentW) * videoW;
  const y = ((cr.top - vr.top + offsetY) / contentH) * videoH;
  const w = (cr.width / contentW) * videoW;
  const h = (cr.height / contentH) * videoH;
  return {
    x: Math.max(0, Math.round(x)), y: Math.max(0, Math.round(y)),
    w: Math.max(32, Math.min(videoW, Math.round(w))),
    h: Math.max(24, Math.min(videoH, Math.round(h)))
  };
}
function captureCrop() {
  const { x, y, w, h } = cropCoordinates();
  const scale = Math.min(1.25, 1200 / w);
  const outW = Math.max(360, Math.round(w * scale));
  const outH = Math.max(80, Math.round(h * scale));
  const c = els.canvas;
  c.width = outW; c.height = outH;
  const ctx = c.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(els.camera, x, y, w, h, 0, 0, outW, outH);
  if (els.highContrast.checked) {
    const img = ctx.getImageData(0, 0, outW, outH);
    const d = img.data;
    let mean = 0;
    for (let i = 0; i < d.length; i += 4) mean += (d[i] * .299 + d[i+1] * .587 + d[i+2] * .114);
    mean /= d.length / 4;
    const threshold = Math.max(110, Math.min(205, mean + 25));
    for (let i = 0; i < d.length; i += 4) {
      const g = d[i] * .299 + d[i+1] * .587 + d[i+2] * .114;
      const v = g > threshold ? 255 : 0;
      d[i] = d[i+1] = d[i+2] = v;
    }
    ctx.putImageData(img, 0, 0);
  }
  return c;
}

async function translateCloud(text) {
  if (!els.cloudFallback.checked) return null;
  try {
    if ('Translator' in self) {
      const availability = await self.Translator.availability({ sourceLanguage: 'en', targetLanguage: 'zh' });
      if (availability !== 'unavailable') {
        if (!translateCloud.browserTranslator) {
          translateCloud.browserTranslator = await self.Translator.create({ sourceLanguage: 'en', targetLanguage: 'zh' });
        }
        const out = await translateCloud.browserTranslator.translate(text);
        if (out) return out.trim();
      }
    }
  } catch (_) {}
  try {
    const url = 'https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=' + encodeURIComponent(text);
    const res = await fetch(url, { signal: AbortSignal.timeout ? AbortSignal.timeout(1800) : undefined });
    if (!res.ok) throw new Error('translate http ' + res.status);
    const data = await res.json();
    const out = Array.isArray(data?.[0]) ? data[0].map(x => x?.[0] || '').join('') : '';
    return out.trim() || null;
  } catch (_) {
    return null;
  }
}

async function recognizeOnce() {
  if (!state.running || state.busy || !state.stream) return;
  state.busy = true;
  const started = performance.now();
  try {
    const worker = await ensureWorker();
    const canvas = captureCrop();
    const result = await worker.recognize(canvas);
    let raw = normalizeText(result?.data?.text || '');
    raw = raw.replace(/^[\-_=~]+|[\-_=~]+$/g, '').trim();
    state.lastRaw = raw;
    if (!isLikelySubtitle(raw)) {
      setStatus('扫描中', true);
      return;
    }
    els.english.textContent = raw;
    if (isDuplicate(raw)) {
      els.meta.textContent = '重复字幕，已忽略';
      setStatus('扫描中', true);
      return;
    }

    const local = findLocalMatch(raw);
    let chinese = null;
    let source = '';
    if (local) {
      chinese = local.item.zh;
      source = `本地字幕库 · ${Math.round(local.score * 100)}% · ${local.item.chapter || '未分章'}`;
    } else {
      setStatus('正在翻译…', true);
      chinese = await translateCloud(raw);
      source = chinese ? '联网翻译' : '未找到翻译';
    }
    if (!chinese) {
      els.chinese.textContent = '未识别到对应中文，可导入该章节字幕库提高速度和准确率。';
      els.meta.textContent = source;
      return;
    }

    state.lastAccepted = raw;
    state.lastAcceptedAt = Date.now();
    state.lastChinese = chinese;
    els.chinese.textContent = chinese;
    els.meta.textContent = source;
    els.speakAgain.disabled = false;
    addHistory(raw, chinese, source);
    if (els.autoSpeak.checked) enqueueSpeech(chinese);
    setStatus('扫描中', true);
  } catch (err) {
    console.error(err);
    setStatus('识别出错，继续重试', true);
  } finally {
    state.busy = false;
    const ms = performance.now() - started;
    state.frameTimes.push(ms);
    if (state.frameTimes.length > 10) state.frameTimes.shift();
    const avg = state.frameTimes.reduce((a,b)=>a+b,0) / state.frameTimes.length;
    els.fpsText.textContent = avg ? `识别 ${Math.round(avg)}ms` : '';
  }
}
function scheduleNext() {
  clearTimeout(state.timer);
  if (!state.running) return;
  state.timer = setTimeout(async () => {
    await recognizeOnce();
    scheduleNext();
  }, Number(els.scanInterval.value));
}
async function startRecognition() {
  try {
    unlockSpeech();
    await requestWakeLock();
    await ensureWorker();
    state.running = true;
    els.recognize.textContent = '识别运行中';
    els.recognize.disabled = true;
    els.pause.disabled = false;
    els.quickToggle.textContent = '暂停';
    setStatus('扫描中', true);
    scheduleNext();
  } catch (err) {
    alert(err.message);
    setStatus('OCR 加载失败', false);
  }
}
function pauseRecognition() {
  state.running = false;
  releaseWakeLock();
  clearTimeout(state.timer);
  els.recognize.textContent = '继续实时翻译';
  els.recognize.disabled = false;
  els.pause.disabled = true;
  els.quickToggle.textContent = '继续翻译';
  setStatus('已暂停', false);
}
function setStatus(text, live) {
  els.statusText.textContent = text;
  els.statusDot.classList.toggle('live', !!live);
}

function pickChineseVoice() {
  const voices = speechSynthesis.getVoices();
  return voices.find(v => /^zh(-|_)/i.test(v.lang) && /ting|xiaoxiao|mei|mandarin|中文|普通话/i.test(v.name))
      || voices.find(v => /^zh(-|_)/i.test(v.lang))
      || null;
}
function enqueueSpeech(text) {
  if (!text) return;
  if (!els.finishBeforeNext.checked) {
    speechSynthesis.cancel();
    state.speechQueue = [];
    state.speaking = false;
  }
  if (state.speechQueue[state.speechQueue.length - 1] === text) return;
  state.speechQueue.push(text);
  if (state.speechQueue.length > 5) state.speechQueue.splice(0, state.speechQueue.length - 5);
  speakNext();
}
function speakNext() {
  if (state.speaking || !state.speechQueue.length) return;
  const text = state.speechQueue.shift();
  const utter = new SpeechSynthesisUtterance(text);
  utter.lang = 'zh-CN';
  utter.rate = Number(els.speechRate.value);
  utter.pitch = 1;
  const voice = pickChineseVoice();
  if (voice) utter.voice = voice;
  state.speaking = true;
  utter.onend = utter.onerror = () => { state.speaking = false; speakNext(); };
  speechSynthesis.speak(utter);
}

function addHistory(en, zh, meta) {
  const li = document.createElement('li');
  li.innerHTML = `<strong>${escapeHtml(zh)}</strong><span>${escapeHtml(en)}</span><small> · ${escapeHtml(meta)}</small>`;
  els.history.prepend(li);
  while (els.history.children.length > 60) els.history.lastChild.remove();
}
function escapeHtml(s) {
  return String(s).replace(/[&<>'"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[c]));
}

function parseSrtVtt(text) {
  const blocks = text.replace(/\r/g, '').split(/\n\s*\n/);
  const items = [];
  for (const block of blocks) {
    const lines = block.split('\n').map(x => x.trim()).filter(Boolean);
    const content = lines.filter(x => !/^\d+$/.test(x) && !/\d{1,2}:\d{2}:\d{2}[,.]\d{3}\s+-->/.test(x) && x !== 'WEBVTT');
    if (!content.length) continue;
    const joined = content.join(' ');
    const split = joined.split(/\s*\|\s*|\s*=>\s*|\s*→\s*/);
    if (split.length >= 2) items.push({ chapter: '导入字幕', en: split[0], zh: split.slice(1).join(' ') });
  }
  return items;
}
function parseCsv(text) {
  const rows = text.replace(/\r/g, '').split('\n').filter(Boolean);
  const out = [];
  for (let i = 0; i < rows.length; i++) {
    const cols = rows[i].match(/("(?:[^"]|"")*"|[^,]*)(?:,|$)/g)?.map(x => x.replace(/,$/, '').replace(/^"|"$/g, '').replace(/""/g, '"').trim()) || [];
    if (i === 0 && cols.join(',').toLowerCase().includes('english')) continue;
    if (cols.length >= 2) out.push({ chapter: cols[0] || '导入字幕', en: cols[1] || '', zh: cols[2] || '' });
  }
  return out.filter(x => x.en && x.zh);
}
async function importLibrary(file) {
  const text = await file.text();
  let items = [];
  try {
    if (/\.json$/i.test(file.name)) {
      const parsed = JSON.parse(text);
      const arr = Array.isArray(parsed) ? parsed : (parsed.subtitles || parsed.items || []);
      items = arr.map(x => ({ chapter: x.chapter || x.mission || '导入字幕', en: x.en || x.english || x.source, zh: x.zh || x.chinese || x.translation })).filter(x => x.en && x.zh);
    } else if (/\.csv$/i.test(file.name)) items = parseCsv(text);
    else items = parseSrtVtt(text);
  } catch (err) {
    alert('字幕文件解析失败：' + err.message); return;
  }
  if (!items.length) {
    alert('没有找到有效的中英对照。SRT/VTT 每条字幕请写成：英文 | 中文'); return;
  }
  const replace = confirm(`识别到 ${items.length} 句。\n\n点“确定”替换当前字幕库；点“取消”追加到当前字幕库。`);
  state.library = replace ? items : [...state.library, ...items];
  saveLibrary();
  alert(`已导入 ${items.length} 句字幕。`);
}
function exportLibrary() {
  const blob = new Blob([JSON.stringify(state.library, null, 2)], { type: 'application/json' });
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = 'cod11-subtitles.json';
  a.click();
  URL.revokeObjectURL(a.href);
}
function refreshLibraryUI() {
  const chapters = [...new Set(state.library.map(x => x.chapter || '未分章'))];
  const current = els.chapter.value;
  els.chapter.innerHTML = '<option value="all">全部章节</option>' + chapters.map(ch => `<option value="${escapeHtml(ch)}">${escapeHtml(ch)}</option>`).join('');
  if ([...els.chapter.options].some(o => o.value === current)) els.chapter.value = current;
  els.libraryInfo.textContent = `当前字幕库：${state.library.length} 句，${chapters.length} 个章节。本地匹配不联网，速度最快。`;
}

function resetCrop() {
  Object.assign(els.crop.style, { left: '8%', top: '67%', width: '84%', height: '18%' });
}
function installCropDragging() {
  let action = null;
  els.crop.addEventListener('pointerdown', e => {
    e.preventDefault();
    const stage = els.stage.getBoundingClientRect();
    const box = els.crop.getBoundingClientRect();
    const handle = e.target.dataset.handle || 'move';
    action = { id: e.pointerId, handle, startX: e.clientX, startY: e.clientY,
      left: box.left - stage.left, top: box.top - stage.top, width: box.width, height: box.height,
      stageW: stage.width, stageH: stage.height };
    els.crop.setPointerCapture(e.pointerId);
  });
  els.crop.addEventListener('pointermove', e => {
    if (!action || action.id !== e.pointerId) return;
    const dx = e.clientX - action.startX, dy = e.clientY - action.startY;
    let { left, top, width, height } = action;
    if (action.handle === 'move') { left += dx; top += dy; }
    else {
      if (action.handle.includes('e')) width += dx;
      if (action.handle.includes('s')) height += dy;
      if (action.handle.includes('w')) { left += dx; width -= dx; }
      if (action.handle.includes('n')) { top += dy; height -= dy; }
    }
    width = Math.max(120, Math.min(width, action.stageW));
    height = Math.max(55, Math.min(height, action.stageH));
    left = Math.max(0, Math.min(left, action.stageW - width));
    top = Math.max(0, Math.min(top, action.stageH - height));
    Object.assign(els.crop.style, {
      left: `${left / action.stageW * 100}%`, top: `${top / action.stageH * 100}%`,
      width: `${width / action.stageW * 100}%`, height: `${height / action.stageH * 100}%`
    });
  });
  els.crop.addEventListener('pointerup', () => { action = null; });
  els.crop.addEventListener('pointercancel', () => { action = null; });
}

els.startCamera.addEventListener('click', startCamera);
els.recognize.addEventListener('click', startRecognition);
els.pause.addEventListener('click', pauseRecognition);
els.quickToggle.addEventListener('click', () => state.running ? pauseRecognition() : startRecognition());
els.speakAgain.addEventListener('click', () => enqueueSpeech(state.lastChinese));
els.switchCamera.addEventListener('click', async () => { state.facingMode = state.facingMode === 'environment' ? 'user' : 'environment'; await startCamera(); });
els.torch.addEventListener('click', toggleTorch);
els.resetCrop.addEventListener('click', resetCrop);
els.scanInterval.addEventListener('change', () => { if (state.running) scheduleNext(); });
els.speechRate.addEventListener('input', () => els.speechRateValue.textContent = `${Number(els.speechRate.value).toFixed(2)}×`);
els.threshold.addEventListener('input', () => els.thresholdValue.textContent = `${Math.round(Number(els.threshold.value) * 100)}%`);
els.libraryFile.addEventListener('change', e => { const f = e.target.files?.[0]; if (f) importLibrary(f); e.target.value = ''; });
els.exportBtn.addEventListener('click', exportLibrary);
els.clearLibrary.addEventListener('click', () => { if (confirm('确认清空字幕库？')) { state.library = []; saveLibrary(); } });
els.clearHistory.addEventListener('click', () => els.history.innerHTML = '');
els.keepAwake?.addEventListener('change', () => {
  if (els.keepAwake.checked && state.running) requestWakeLock();
  else releaseWakeLock();
});
document.addEventListener('visibilitychange', () => {
  if (document.visibilityState === 'visible' && state.running) requestWakeLock();
});

installCropDragging();
refreshLibraryUI();
refreshInstallStatus();
if ('serviceWorker' in navigator) navigator.serviceWorker.register('./sw.js').catch(() => {});
window.addEventListener('beforeunload', () => { releaseWakeLock(); stopCamera(); });
