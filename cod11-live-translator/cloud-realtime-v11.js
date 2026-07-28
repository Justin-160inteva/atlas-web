'use strict';

(() => {
  const cloud = {
    pc: null,
    dc: null,
    connected: false,
    connecting: false,
    running: false,
    frameHandle: 0,
    lastCaptureAt: 0,
    inFlight: false,
    pendingFrame: null,
    responseText: '',
    responseStartedAt: 0,
    lastOutputKey: '',
    lastOutputAt: 0,
    emptyCount: 0,
    crop: { x: .08, y: .67, w: .84, h: .18 },
    previousSample: null,
    captureCanvas: document.createElement('canvas'),
    sampleCanvas: document.createElement('canvas'),
    sequence: 0,
  };

  const COMMON = new Set('a an the and or but if then than to of in on at for from with by is am are was were be been do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how'.split(' '));

  function words(text) {
    return String(text || '').toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  }

  function replaceButton(oldButton, text) {
    const next = oldButton.cloneNode(true);
    next.textContent = text;
    oldButton.replaceWith(next);
    return next;
  }

  els.recognize = replaceButton(els.recognize, '连接并开始实时翻译');
  els.pause = replaceButton(els.pause, '暂停实时翻译');
  els.quickToggle = replaceButton(els.quickToggle, '开始实时翻译');
  els.pause.disabled = true;

  const connectionDetails = document.createElement('details');
  connectionDetails.open = true;
  connectionDetails.id = 'realtimeCloudSettings';
  connectionDetails.innerHTML = `
    <summary>云端实时视觉</summary>
    <div class="settings-grid">
      <label>Realtime Worker 地址
        <input id="realtimeEndpoint" type="url" inputmode="url" autocomplete="url"
          placeholder="https://cod11-realtime.你的账户.workers.dev" />
      </label>
      <label>视频字幕帧率
        <select id="realtimeFps">
          <option value="3">3 帧/秒（省流量）</option>
          <option value="5" selected>5 帧/秒（推荐）</option>
          <option value="7">7 帧/秒（更及时）</option>
        </select>
      </label>
      <label class="checkbox"><input id="streamPartial" type="checkbox" checked /> 流式显示尚未完成的中文</label>
      <label class="checkbox"><input id="clearWhenEmpty" type="checkbox" checked /> 字幕消失后自动清空中文</label>
    </div>
    <div class="control-row" style="margin-top:12px">
      <button id="testRealtimeBtn">测试云端连接</button>
      <span id="realtimeCloudStatus" class="hint">尚未连接。密钥只保存在云端 Worker。</span>
    </div>
  `;
  const firstDetails = document.querySelector('.controls details');
  firstDetails?.parentNode?.insertBefore(connectionDetails, firstDetails);

  const endpointInput = document.getElementById('realtimeEndpoint');
  const fpsSelect = document.getElementById('realtimeFps');
  const partialToggle = document.getElementById('streamPartial');
  const clearToggle = document.getElementById('clearWhenEmpty');
  const testButton = document.getElementById('testRealtimeBtn');
  const cloudStatus = document.getElementById('realtimeCloudStatus');

  const queryEndpoint = new URLSearchParams(location.search).get('endpoint');
  endpointInput.value = queryEndpoint || localStorage.getItem('cod11-realtime-endpoint') || '';
  fpsSelect.value = localStorage.getItem('cod11-realtime-fps') || '5';
  endpointInput.addEventListener('change', () => localStorage.setItem('cod11-realtime-endpoint', endpointInput.value.trim()));
  fpsSelect.addEventListener('change', () => localStorage.setItem('cod11-realtime-fps', fpsSelect.value));

  function setCloudStatus(text, good = false) {
    cloudStatus.textContent = text;
    cloudStatus.style.color = good ? '#cfffaa' : '';
  }

  function normalizedEndpoint() {
    let value = endpointInput.value.trim().replace(/\/+$/, '');
    if (!value) return '';
    if (!/^https:\/\//i.test(value)) value = `https://${value}`;
    if (!/\/api\/realtime\/call$/i.test(value)) value += '/api/realtime/call';
    return value;
  }

  function saveCropSnapshot() {
    try {
      const videoW = els.camera.videoWidth || 0;
      const videoH = els.camera.videoHeight || 0;
      if (!videoW || !videoH || els.crop.getClientRects().length === 0) return;
      const c = cropCoordinates();
      cloud.crop = {
        x: Math.max(0, Math.min(1, c.x / videoW)),
        y: Math.max(0, Math.min(1, c.y / videoH)),
        w: Math.max(.02, Math.min(1, c.w / videoW)),
        h: Math.max(.02, Math.min(1, c.h / videoH)),
      };
    } catch (_) {}
  }

  els.crop.addEventListener('pointerup', saveCropSnapshot);
  els.crop.addEventListener('pointercancel', saveCropSnapshot);
  document.getElementById('focusModeBtn')?.addEventListener('click', saveCropSnapshot, true);

  function captureSubtitleFrame() {
    const videoW = els.camera.videoWidth;
    const videoH = els.camera.videoHeight;
    if (!videoW || !videoH) return null;

    const x = Math.round(cloud.crop.x * videoW);
    const y = Math.round(cloud.crop.y * videoH);
    const w = Math.max(80, Math.round(cloud.crop.w * videoW));
    const h = Math.max(30, Math.round(cloud.crop.h * videoH));
    const targetW = Math.min(960, Math.max(520, w));
    const targetH = Math.max(72, Math.min(280, Math.round(h * targetW / w)));
    const canvas = cloud.captureCanvas;
    canvas.width = targetW;
    canvas.height = targetH;
    const ctx = canvas.getContext('2d', { alpha: false, willReadFrequently: false });
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(els.camera, x, y, w, h, 0, 0, targetW, targetH);

    const sample = cloud.sampleCanvas;
    sample.width = 48;
    sample.height = 14;
    const sctx = sample.getContext('2d', { alpha: false, willReadFrequently: true });
    sctx.drawImage(canvas, 0, 0, sample.width, sample.height);
    const pixels = sctx.getImageData(0, 0, sample.width, sample.height).data;
    const signature = new Uint8Array(sample.width * sample.height);
    for (let i = 0, j = 0; i < pixels.length; i += 4, j++) {
      signature[j] = Math.round(pixels[i] * .299 + pixels[i + 1] * .587 + pixels[i + 2] * .114);
    }

    return { dataUrl: canvas.toDataURL('image/jpeg', .62), signature, at: performance.now() };
  }

  function frameDifference(next) {
    const previous = cloud.previousSample;
    cloud.previousSample = next;
    if (!previous || previous.length !== next.length) return 255;
    let sum = 0;
    for (let i = 0; i < next.length; i++) sum += Math.abs(next[i] - previous[i]);
    return sum / next.length;
  }

  function activeItems() {
    const selected = els.chapter?.value || 'all';
    return selected === 'all' ? state.library : state.library.filter(item => item.chapter === selected);
  }

  function dictionaryConfirm(english) {
    const sourceWords = new Set(words(english));
    let best = null;
    let bestScore = 0;
    let bestStrong = 0;
    for (const item of activeItems()) {
      const surfaces = [item.en, ...(Array.isArray(item.aliases) ? item.aliases : [])].filter(Boolean);
      let itemScore = 0;
      let strong = 0;
      for (const surface of surfaces) {
        itemScore = Math.max(itemScore, similarity(english, surface));
        const target = new Set(words(surface));
        let localStrong = 0;
        sourceWords.forEach(word => {
          if (target.has(word) && word.length >= 4 && !COMMON.has(word)) localStrong++;
        });
        strong = Math.max(strong, localStrong);
      }
      if (itemScore > bestScore) {
        best = item;
        bestScore = itemScore;
        bestStrong = strong;
      }
    }
    return best && (bestScore >= .68 || (bestScore >= .54 && bestStrong >= 1))
      ? { item: best, score: bestScore }
      : null;
  }

  function polishChinese(text) {
    return String(text || '')
      .replace(/哈迪斯/g, '冥王')
      .replace(/亚特拉斯|阿特拉斯/g, '巨神')
      .replace(/曼蒂科尔|曼提科尔|蝎尾狮/g, '心智核心')
      .replace(/钥匙人|关键人物/g, '关键人')
      .replace(/外骨骼服/g, '外骨骼')
      .trim();
  }

  function parseModelLine(text) {
    let value = String(text || '').trim().replace(/^```(?:text|json)?\s*|\s*```$/gi, '').trim();
    if (!value || /^NONE[.!]?$/i.test(value)) return { empty: true };
    const match = value.match(/^([\s\S]*?)(?:\t|\s*\|\s*|\s*=>\s*|\n)([\s\S]+)$/);
    if (!match) return null;
    const en = normalizeText(match[1]);
    const zh = polishChinese(match[2].replace(/^中文[:：]\s*/, ''));
    if (!en || !zh || words(en).length < 1) return null;
    return { en, zh, empty: false };
  }

  function showPartial() {
    if (!partialToggle.checked) return;
    const parsed = parseModelLine(cloud.responseText);
    if (!parsed || parsed.empty) return;
    els.english.textContent = parsed.en;
    els.chinese.textContent = parsed.zh;
    els.meta.textContent = '云端实时视觉 · 正在流式生成';
  }

  function outputSubtitle(english, chinese, source, startedAt) {
    const confirmed = dictionaryConfirm(english);
    if (confirmed) {
      english = confirmed.item.en;
      chinese = confirmed.item.zh;
      source = `字典确认 · ${Math.round(confirmed.score * 100)}%`;
    }

    chinese = polishChinese(chinese);
    const key = `${comparable(english)}|${chinese}`;
    const now = Date.now();
    if (key === cloud.lastOutputKey && now - cloud.lastOutputAt < 5000) return;
    cloud.lastOutputKey = key;
    cloud.lastOutputAt = now;
    cloud.emptyCount = 0;

    const latency = Math.max(0, Math.round(performance.now() - startedAt));
    state.lastAccepted = english;
    state.lastAcceptedAt = now;
    state.lastChinese = chinese;
    els.english.textContent = english;
    els.chinese.textContent = chinese;
    els.meta.textContent = `${source} · 总延迟 ${latency}ms`;
    els.speakAgain.disabled = false;
    addHistory(english, chinese, `${source} · ${latency}ms`);
    if (els.autoSpeak.checked) enqueueSpeech(chinese);
    setStatus('云端实时识别中', true);
  }

  function handleEmptyFrame() {
    cloud.emptyCount++;
    if (clearToggle.checked && cloud.emptyCount >= 2) {
      els.english.textContent = '';
      els.chinese.textContent = '';
      els.meta.textContent = '等待下一条字幕';
      state.lastChinese = '';
      els.speakAgain.disabled = true;
    }
  }

  function releaseResponse() {
    cloud.inFlight = false;
    cloud.responseText = '';
    const pending = cloud.pendingFrame;
    cloud.pendingFrame = null;
    if (pending && cloud.running) sendFrame(pending);
  }

  function handleRealtimeEvent(event) {
    let message;
    try { message = JSON.parse(event.data); } catch { return; }

    if (message.type === 'response.output_text.delta') {
      cloud.responseText += message.delta || '';
      showPartial();
      return;
    }

    if (message.type === 'response.output_text.done') {
      cloud.responseText = message.text || cloud.responseText;
      const parsed = parseModelLine(cloud.responseText);
      if (parsed?.empty) handleEmptyFrame();
      else if (parsed) outputSubtitle(parsed.en, parsed.zh, '云端实时视觉', cloud.responseStartedAt);
      else setCloudStatus('模型返回格式异常，已忽略本帧。');
      return;
    }

    if (message.type === 'response.done') {
      releaseResponse();
      return;
    }

    if (message.type === 'error') {
      console.error('Realtime error', message);
      setCloudStatus(`实时服务错误：${message.error?.message || '未知错误'}`);
      releaseResponse();
    }
  }

  async function connectRealtime() {
    if (cloud.connected && cloud.dc?.readyState === 'open') return;
    if (cloud.connecting) return new Promise((resolve, reject) => {
      const timeout = setTimeout(() => reject(new Error('连接超时')), 12000);
      const timer = setInterval(() => {
        if (cloud.connected) { clearTimeout(timeout); clearInterval(timer); resolve(); }
      }, 100);
    });

    const endpoint = normalizedEndpoint();
    if (!endpoint) throw new Error('请先填写已经部署的 Realtime Worker 地址。');
    localStorage.setItem('cod11-realtime-endpoint', endpointInput.value.trim());
    cloud.connecting = true;
    setCloudStatus('正在建立 WebRTC 实时视觉连接……');
    setStatus('连接云端视觉', true);

    try {
      cloud.pc?.close();
      const pc = new RTCPeerConnection();
      const dc = pc.createDataChannel('oai-events');
      cloud.pc = pc;
      cloud.dc = dc;
      dc.addEventListener('message', handleRealtimeEvent);

      const openPromise = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => reject(new Error('WebRTC 数据通道开启超时')), 15000);
        dc.addEventListener('open', () => { clearTimeout(timeout); resolve(); }, { once: true });
        dc.addEventListener('error', () => { clearTimeout(timeout); reject(new Error('WebRTC 数据通道失败')); }, { once: true });
      });

      pc.addEventListener('connectionstatechange', () => {
        const status = pc.connectionState;
        if (status === 'connected') {
          cloud.connected = true;
          setCloudStatus('云端实时视觉已连接。', true);
        } else if (['failed', 'closed', 'disconnected'].includes(status)) {
          cloud.connected = false;
          if (status === 'failed') setCloudStatus('云端连接失败，请重新连接。');
        }
      });

      const offer = await pc.createOffer();
      await pc.setLocalDescription(offer);
      const response = await fetch(endpoint, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sdp: offer.sdp }),
      });
      const answerSdp = await response.text();
      if (!response.ok) {
        let detail = answerSdp;
        try { detail = JSON.parse(answerSdp).error || detail; } catch (_) {}
        throw new Error(detail || `Worker 返回 ${response.status}`);
      }

      await pc.setRemoteDescription({ type: 'answer', sdp: answerSdp });
      await openPromise;
      cloud.connected = true;
      setCloudStatus('云端实时视觉已连接。', true);
      setStatus('云端视觉已就绪', false);
    } finally {
      cloud.connecting = false;
    }
  }

  function sendFrame(frame) {
    if (!cloud.running || !cloud.connected || cloud.dc?.readyState !== 'open') return;
    if (cloud.inFlight) {
      cloud.pendingFrame = frame;
      return;
    }

    cloud.inFlight = true;
    cloud.responseText = '';
    cloud.responseStartedAt = frame.at;
    const frameId = ++cloud.sequence;
    const event = {
      type: 'response.create',
      response: {
        conversation: 'none',
        output_modalities: ['text'],
        max_output_tokens: 120,
        metadata: { frame_id: String(frameId) },
        instructions: 'Read only the newest visible English game dialogue subtitle. Output exactly ENGLISH<TAB>SIMPLIFIED_CHINESE. If no clear dialogue subtitle is visible, output NONE. No commentary.',
        input: [{
          type: 'message',
          role: 'user',
          content: [
            { type: 'input_image', image_url: frame.dataUrl, detail: 'low' },
            { type: 'input_text', text: 'Read and translate the visible English dialogue subtitle now.' },
          ],
        }],
      },
    };
    cloud.dc.send(JSON.stringify(event));
    if (els.detected) els.detected.textContent = '字幕画面已送入云端实时视觉……';
    setStatus('实时识别中', true);
  }

  function processVideoFrame(now) {
    if (!cloud.running) return;
    const interval = 1000 / Math.max(1, Number(fpsSelect.value || 5));
    if (now - cloud.lastCaptureAt >= interval) {
      cloud.lastCaptureAt = now;
      const frame = captureSubtitleFrame();
      if (frame) {
        const diff = frameDifference(frame.signature);
        if (diff >= 2.8 || !cloud.lastOutputKey) sendFrame(frame);
      }
    }
    scheduleVideoFrame();
  }

  function scheduleVideoFrame() {
    if (!cloud.running) return;
    if ('requestVideoFrameCallback' in HTMLVideoElement.prototype) {
      cloud.frameHandle = els.camera.requestVideoFrameCallback((now) => processVideoFrame(now));
    } else {
      cloud.frameHandle = requestAnimationFrame(processVideoFrame);
    }
  }

  function cancelVideoFrame() {
    if ('cancelVideoFrameCallback' in HTMLVideoElement.prototype && cloud.frameHandle) {
      try { els.camera.cancelVideoFrameCallback(cloud.frameHandle); } catch (_) {}
    } else if (cloud.frameHandle) cancelAnimationFrame(cloud.frameHandle);
    cloud.frameHandle = 0;
  }

  async function startCloudRecognition() {
    try {
      if (!state.stream) throw new Error('请先开启摄像头。');
      unlockSpeech();
      await requestWakeLock();
      saveCropSnapshot();
      await connectRealtime();
      state.running = true;
      cloud.running = true;
      cloud.previousSample = null;
      cloud.lastCaptureAt = 0;
      els.recognize.textContent = '云端实时翻译运行中';
      els.recognize.disabled = true;
      els.pause.disabled = false;
      els.quickToggle.textContent = '暂停';
      setStatus('云端实时识别中', true);
      cancelVideoFrame();
      scheduleVideoFrame();
    } catch (error) {
      console.error(error);
      setCloudStatus(error.message || String(error));
      setStatus('云端实时视觉未连接', false);
      alert(error.message || error);
    }
  }

  function pauseCloudRecognition() {
    state.running = false;
    cloud.running = false;
    cancelVideoFrame();
    releaseWakeLock();
    els.recognize.textContent = '继续云端实时翻译';
    els.recognize.disabled = false;
    els.pause.disabled = true;
    els.quickToggle.textContent = '继续翻译';
    setStatus('已暂停', false);
  }

  els.recognize.addEventListener('click', startCloudRecognition);
  els.pause.addEventListener('click', pauseCloudRecognition);
  els.quickToggle.addEventListener('click', () => cloud.running ? pauseCloudRecognition() : startCloudRecognition());
  testButton.addEventListener('click', async () => {
    try { await connectRealtime(); } catch (error) { setCloudStatus(error.message || String(error)); }
  });

  document.title = 'COD11 云端实时视觉翻译器 V11';
  const heading = document.querySelector('.empty-state h1');
  const intro = document.querySelector('.empty-state p');
  if (heading) heading.textContent = 'COD11 云端实时视觉翻译器 V11';
  if (intro) intro.textContent = '持续视频帧通过 WebRTC 进入云端视觉；字典只负责确认和纠错。';
  els.statusText.textContent = '未启动 · V11云端实时视觉';
  if (els.detected) els.detected.textContent = '等待云端实时视觉连接……';
  els.english.textContent = '';
  els.chinese.textContent = '';
  els.meta.textContent = 'V11：WebRTC实时视觉主识别，本地字典确认';
  if (els.scanInterval) {
    els.scanInterval.disabled = true;
    els.scanInterval.innerHTML = '<option selected>由摄像头真实视频帧驱动</option>';
  }
  if (els.cloudFallback) {
    els.cloudFallback.checked = true;
    els.cloudFallback.disabled = true;
    const label = els.cloudFallback.closest('label');
    if (label) label.lastChild.textContent = ' 云端视觉直接识别并翻译，字典用于确认';
  }
  const info = document.getElementById('libraryInfo');
  if (info) info.textContent = `当前字典 ${state.library.length} 条，仅用于确认、补全和专有名词纠错；未收录字幕仍由云端视觉实时翻译。`;

  window.addEventListener('pagehide', () => {
    cloud.running = false;
    cancelVideoFrame();
    try { cloud.dc?.close(); } catch (_) {}
    try { cloud.pc?.close(); } catch (_) {}
  });
})();
