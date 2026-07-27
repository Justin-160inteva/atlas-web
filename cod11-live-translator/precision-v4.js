'use strict';

(() => {
  const precision = {
    scanNo: 0,
    frames: [],
    lastCommittedKey: '',
    lastCommittedAt: 0,
    lastOrder: -1,
    lastChapter: '',
    lastContextAt: 0,
    currentMode: 0
  };

  const baseEnsureWorker = ensureWorker;
  const baseStartCamera = startCamera;
  const basePauseRecognition = pauseRecognition;
  const baseFindLocalMatch = findLocalMatch;

  function addPrecisionUI() {
    const settings = document.querySelector('#chapterSelect')?.closest('.settings-grid');
    if (settings && !document.getElementById('stableFrames')) {
      settings.insertAdjacentHTML('beforeend', `
        <label>稳定确认
          <select id="stableFrames">
            <option value="1">最快：强命中立即显示</option>
            <option value="2" selected>平衡：最多确认 2 帧</option>
            <option value="3">最稳：最多确认 3 帧</option>
          </select>
        </label>
        <label>剧情顺序锁定
          <select id="sequenceWindow">
            <option value="4">严格：只看后续 4 句</option>
            <option value="8" selected>推荐：只看后续 8 句</option>
            <option value="16">宽松：只看后续 16 句</option>
          </select>
        </label>
      `);
    }

    els.stableFrames = document.getElementById('stableFrames');
    els.sequenceWindow = document.getElementById('sequenceWindow');

    if (els.threshold) {
      els.threshold.value = '0.56';
      els.thresholdValue.textContent = '56%';
    }
    if (els.minKeywords) {
      els.minKeywords.value = '1';
      els.minKeywordsValue.textContent = '1 个';
    }
    const info = document.getElementById('libraryInfo');
    if (info) {
      info.textContent = `已内置第6关中英台词 ${state.library.length} 条。新版使用多帧稳定确认、三种字幕增强和剧情顺序锁定。`;
    }
  }

  function percentile(values, p) {
    if (!values.length) return 128;
    const sorted = values.slice().sort((a, b) => a - b);
    return sorted[Math.min(sorted.length - 1, Math.max(0, Math.floor(sorted.length * p)))];
  }

  function dilateBlackMask(data, width, height) {
    const source = new Uint8ClampedArray(data);
    for (let y = 1; y < height - 1; y++) {
      for (let x = 1; x < width - 1; x++) {
        const i = (y * width + x) * 4;
        if (source[i] < 80) continue;
        let blackNeighbor = false;
        for (let yy = -1; yy <= 1 && !blackNeighbor; yy++) {
          for (let xx = -1; xx <= 1; xx++) {
            const n = ((y + yy) * width + (x + xx)) * 4;
            if (source[n] < 60) { blackNeighbor = true; break; }
          }
        }
        if (blackNeighbor) data[i] = data[i + 1] = data[i + 2] = 0;
      }
    }
  }

  captureCrop = function capturePrecisionCrop() {
    const { x, y, w, h } = cropCoordinates();
    const targetWidth = Math.max(1100, Math.min(1900, Math.round(w * 2.15)));
    const scale = targetWidth / Math.max(1, w);
    const innerW = Math.max(700, Math.round(w * scale));
    const innerH = Math.max(110, Math.round(h * scale));
    const pad = 26;
    const canvas = els.canvas;
    canvas.width = innerW + pad * 2;
    canvas.height = innerH + pad * 2;
    const ctx = canvas.getContext('2d', { willReadFrequently: true });
    ctx.save();
    ctx.fillStyle = '#fff';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    ctx.imageSmoothingEnabled = true;
    ctx.imageSmoothingQuality = 'high';
    ctx.drawImage(els.camera, x, y, w, h, pad, pad, innerW, innerH);
    ctx.restore();

    if (!els.highContrast.checked) return canvas;

    const img = ctx.getImageData(pad, pad, innerW, innerH);
    const d = img.data;
    const lumas = [];
    const whiteScores = [];
    for (let i = 0; i < d.length; i += 16) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      const l = r * .299 + g * .587 + b * .114;
      const spread = Math.max(r, g, b) - Math.min(r, g, b);
      lumas.push(l);
      whiteScores.push(l - spread * .72);
    }

    const mode = precision.scanNo % 3;
    precision.currentMode = mode;
    const high = Math.max(138, percentile(whiteScores, .79));
    const mid = Math.max(112, percentile(lumas, .64));

    for (let i = 0; i < d.length; i += 4) {
      const r = d[i], g = d[i + 1], b = d[i + 2];
      const l = r * .299 + g * .587 + b * .114;
      const spread = Math.max(r, g, b) - Math.min(r, g, b);
      let v;
      if (mode === 0) {
        const score = l - spread * .72;
        v = score >= high && l > 132 ? 0 : 255;
      } else if (mode === 1) {
        const boosted = Math.max(0, Math.min(255, (l - mid) * 2.15 + 142));
        v = 255 - boosted;
      } else {
        const threshold = Math.max(130, percentile(lumas, .74));
        v = l >= threshold ? 0 : 255;
      }
      d[i] = d[i + 1] = d[i + 2] = v;
      d[i + 3] = 255;
    }

    if (mode !== 1) dilateBlackMask(d, innerW, innerH);
    ctx.putImageData(img, pad, pad);
    return canvas;
  };

  ensureWorker = async function ensurePrecisionWorker() {
    const worker = await baseEnsureWorker();
    try {
      await worker.setParameters({
        tessedit_pageseg_mode: Tesseract.PSM.SINGLE_BLOCK,
        preserve_interword_spaces: '1',
        user_defined_dpi: '300',
        tessedit_char_whitelist: "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789'!?.,- "
      });
    } catch (_) {}
    return worker;
  };

  startCamera = async function startPrecisionCamera() {
    await baseStartCamera();
    const track = state.stream?.getVideoTracks?.()[0];
    if (!track) return;
    try {
      const caps = track.getCapabilities?.() || {};
      const advanced = {};
      if (Array.isArray(caps.focusMode) && caps.focusMode.includes('continuous')) advanced.focusMode = 'continuous';
      if (Array.isArray(caps.exposureMode) && caps.exposureMode.includes('continuous')) advanced.exposureMode = 'continuous';
      if (Array.isArray(caps.whiteBalanceMode) && caps.whiteBalanceMode.includes('continuous')) advanced.whiteBalanceMode = 'continuous';
      if (Object.keys(advanced).length) await track.applyConstraints({ advanced: [advanced] });
      const settings = track.getSettings?.() || {};
      els.meta.textContent = settings.width && settings.height
        ? `相机 ${settings.width}×${settings.height} · 请让字幕尽量占满绿色框`
        : '请让字幕尽量占满绿色框';
    } catch (_) {}
  };

  pauseRecognition = function pausePrecisionRecognition() {
    precision.frames = [];
    basePauseRecognition();
  };

  function looseMatch(text) {
    const threshold = els.threshold?.value;
    const minKeywords = els.minKeywords?.value;
    try {
      if (els.threshold) els.threshold.value = '0.45';
      if (els.minKeywords) els.minKeywords.value = '1';
      return baseFindLocalMatch(text);
    } finally {
      if (els.threshold && threshold != null) els.threshold.value = threshold;
      if (els.minKeywords && minKeywords != null) els.minKeywords.value = minKeywords;
    }
  }

  function candidateKey(local) {
    return `${local.item.chapter || ''}|${local.item.order || local.entry?.order || 0}|${local.item.en}`;
  }

  function sequenceAdjustment(local) {
    if (!local || precision.lastOrder < 0 || Date.now() - precision.lastContextAt > 50000) return 0;
    const chapter = local.item.chapter || local.entry?.chapter || '';
    if (chapter !== precision.lastChapter) return -0.05;
    const order = Number(local.item.order || local.entry?.order || 0);
    const delta = order - precision.lastOrder;
    const windowSize = Number(els.sequenceWindow?.value || 8);
    if (delta === 0) return 0.03;
    if (delta === 1) return 0.18;
    if (delta === 2) return 0.12;
    if (delta > 2 && delta <= windowSize) return Math.max(0.02, 0.09 - delta * .006);
    if (delta < -1) return -0.20;
    if (delta > windowSize) return -0.12;
    return 0;
  }

  function aggregateCandidates() {
    const groups = new Map();
    for (const frame of precision.frames) {
      const local = looseMatch(frame.raw);
      if (!local) continue;
      const key = candidateKey(local);
      if (!groups.has(key)) groups.set(key, {
        key,
        local,
        support: 0,
        maxScore: 0,
        weighted: 0,
        bestConfidence: 0,
        fragments: []
      });
      const group = groups.get(key);
      const confidenceFactor = Math.max(.35, Math.min(1, frame.confidence / 75));
      group.support++;
      group.maxScore = Math.max(group.maxScore, local.score || 0);
      group.weighted += (local.score || 0) * confidenceFactor;
      group.bestConfidence = Math.max(group.bestConfidence, frame.confidence);
      group.fragments.push(frame.raw);
    }

    const ranked = [...groups.values()].map(group => {
      const average = group.weighted / Math.max(1, group.support);
      const supportBonus = Math.min(.18, (group.support - 1) * .09);
      group.finalScore = Math.min(1, Math.max(group.maxScore, average) + supportBonus + sequenceAdjustment(group.local));
      return group;
    }).sort((a, b) => b.finalScore - a.finalScore);
    return ranked;
  }

  function shouldCommit(best, second) {
    if (!best) return false;
    const requiredFrames = Number(els.stableFrames?.value || 2);
    const margin = best.finalScore - (second?.finalScore || 0);
    const strongUnique = best.maxScore >= .82 && margin >= .055;
    const strongOCR = best.bestConfidence >= 68 && best.maxScore >= .72 && margin >= .05;
    const stable = best.support >= requiredFrames && best.finalScore >= .61 && margin >= .025;
    const expectedNext = precision.lastOrder >= 0
      && (best.local.item.chapter || '') === precision.lastChapter
      && Number(best.local.item.order || best.local.entry?.order || 0) - precision.lastOrder === 1
      && best.finalScore >= .57;
    return strongUnique || strongOCR || stable || expectedNext;
  }

  function acceptFrame(raw, confidence) {
    const now = Date.now();
    const previous = precision.frames[precision.frames.length - 1];
    if (previous && similarity(raw, previous.raw) < .18 && now - previous.at < 2200) {
      precision.frames = [];
    }
    precision.frames.push({ raw, confidence, at: now });
    precision.frames = precision.frames.filter(frame => now - frame.at < 3600).slice(-4);
  }

  recognizeOnce = async function recognizePrecisionOnce() {
    if (!state.running || state.busy || !state.stream) return;
    state.busy = true;
    const started = performance.now();
    precision.scanNo++;
    try {
      const worker = await ensureWorker();
      const canvas = captureCrop();
      const result = await worker.recognize(canvas);
      let raw = normalizeText(result?.data?.text || '');
      raw = raw.replace(/^[\-_=~]+|[\-_=~]+$/g, '').replace(/\b[|Il]{4,}\b/g, ' ').replace(/\s+/g, ' ').trim();
      const confidence = Number(result?.data?.confidence || 0);
      state.lastRaw = raw;

      if (els.detected) {
        els.detected.textContent = raw
          ? `识别片段：${raw} · OCR ${Math.round(confidence)}% · 增强${precision.currentMode + 1}`
          : `未读到字幕 · 增强${precision.currentMode + 1}`;
      }

      if (!isLikelySubtitle(raw) || confidence < 14) {
        setStatus('继续取样', true);
        return;
      }

      acceptFrame(raw, confidence);
      const ranked = aggregateCandidates();
      const best = ranked[0];
      const second = ranked[1];

      if (!shouldCommit(best, second)) {
        els.meta.textContent = best
          ? `候选确认中 · ${best.support}/${Number(els.stableFrames?.value || 2)} 帧 · ${Math.round(best.finalScore * 100)}%`
          : '未找到可靠候选，继续读取下一帧';
        setStatus('稳定确认中', true);
        return;
      }

      const local = best.local;
      const key = best.key;
      const now = Date.now();
      if (key === precision.lastCommittedKey && now - precision.lastCommittedAt < 8500) {
        els.meta.textContent = '同一句字幕的重复画面，已忽略';
        setStatus('扫描中', true);
        return;
      }

      const chapter = local.item.chapter || local.entry?.chapter || '未分章';
      const order = Number(local.item.order || local.entry?.order || 0);
      const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';
      const source = `稳定命中 · ${Math.round(best.finalScore * 100)}% · ${best.support} 帧 · ${chapter} #${order}${speaker}`;

      precision.lastCommittedKey = key;
      precision.lastCommittedAt = now;
      precision.lastOrder = order;
      precision.lastChapter = chapter;
      precision.lastContextAt = now;
      precision.frames = [];

      state.lastAccepted = local.item.en;
      state.lastAcceptedAt = now;
      state.lastChinese = local.item.zh;
      els.english.textContent = local.item.en;
      els.chinese.textContent = local.item.zh;
      els.meta.textContent = source;
      els.speakAgain.disabled = false;
      addHistory(local.item.en, local.item.zh, source);
      if (els.autoSpeak.checked) enqueueSpeech(local.item.zh);
      setStatus('扫描中', true);
    } catch (error) {
      console.error(error);
      setStatus('识别出错，继续重试', true);
    } finally {
      state.busy = false;
      const elapsed = performance.now() - started;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 8) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / Math.max(1, state.frameTimes.length);
      els.fpsText.textContent = average ? `OCR ${Math.round(average)}ms` : '';
    }
  };

  addPrecisionUI();
})();
