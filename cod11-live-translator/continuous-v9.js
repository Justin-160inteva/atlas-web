'use strict';

(() => {
  const fast = {
    previousRaw: '',
    previousAt: 0,
    lastKey: '',
    lastAt: 0,
    requestNo: 0,
    inFlightKey: '',
    translationCache: new Map()
  };

  const COMMON = new Set('a an the and or but if then than to of in on at for from with without by is am are was were be been being do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how let make take keep move stay stop hold need know tell look give bring'.split(' '));

  function words(text) {
    return String(text || '').toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  }

  function cleanResult(result) {
    return normalizeText(result?.data?.text || '')
      .replace(/^[\-_=~]+|[\-_=~]+$/g, '')
      .replace(/\b[|Il]{4,}\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function looksLikeSubtitle(text, confidence) {
    if (!text || text.length < 3 || text.length > 190) return false;
    const letters = (text.match(/[A-Za-z]/g) || []).length;
    if (letters < 3 || letters / Math.max(1, text.length) < 0.67) return false;
    const rawTokens = text.split(/\s+/).filter(Boolean);
    const tokenList = words(text);
    if (!tokenList.length || tokenList.length > 32) return false;
    if (rawTokens.some(token => /[A-Za-z]/.test(token) && /\d/.test(token))) return false;
    const weirdCaps = rawTokens.filter(token => /^[A-Z]{1,3}$/.test(token) && !['KVA', 'UN', 'US'].includes(token));
    if (weirdCaps.length >= Math.max(2, Math.ceil(rawTokens.length * 0.45))) return false;
    const useful = tokenList.filter(token => token.length >= 3 || COMMON.has(token));
    if (tokenList.length >= 2 && useful.length < 2) return false;
    return Number(confidence || 0) >= 12;
  }

  function dictionaryEvidence(raw, local) {
    if (!local?.item) return false;
    const source = new Set(words(raw));
    const target = new Set(words([local.item.en, ...(local.item.aliases || [])].join(' ')));
    let overlap = 0;
    let strong = 0;
    source.forEach(token => {
      if (!target.has(token)) return;
      overlap++;
      if (token.length >= 4 && !COMMON.has(token)) strong++;
    });
    const score = Number(local.score || 0);
    return score >= 0.76 || strong >= 1 || overlap >= 2;
  }

  function polish(text) {
    let output = String(text || '').trim();
    const replacements = [
      [/哈迪斯/g, '冥王'], [/阿特拉斯/g, '巨神'], [/亚特拉斯/g, '巨神'],
      [/曼蒂科尔/g, '心智核心'], [/曼提科尔/g, '心智核心'], [/蝎尾狮计划/g, '心智核心计划'],
      [/钥匙人/g, '关键人'], [/关键人物/g, '关键人'], [/外骨骼服/g, '外骨骼'],
      [/阿特拉斯部队/g, '巨神部队']
    ];
    replacements.forEach(([pattern, value]) => { output = output.replace(pattern, value); });
    return output;
  }

  function output(english, chinese, source, key, startedAt) {
    const now = performance.now();
    const wallNow = Date.now();
    if (key === fast.lastKey && wallNow - fast.lastAt < 6500) return;
    fast.lastKey = key;
    fast.lastAt = wallNow;
    state.lastAccepted = english;
    state.lastAcceptedAt = wallNow;
    state.lastChinese = chinese;
    els.english.textContent = english;
    els.chinese.textContent = chinese;
    els.meta.textContent = `${source} · 总延迟 ${Math.round(now - startedAt)}ms`;
    if (els.detected) els.detected.textContent = source.startsWith('字典') ? '字典已确认完整台词' : '实时 OCR 已确认字幕';
    els.speakAgain.disabled = false;
    addHistory(english, chinese, els.meta.textContent);
    if (els.autoSpeak.checked) enqueueSpeech(chinese);
    setStatus('连续识别中', true);
  }

  async function translateImmediately(raw, confidence, startedAt) {
    const normalized = comparable(raw);
    if (!normalized || fast.inFlightKey === normalized) return;
    const cached = fast.translationCache.get(normalized);
    if (cached) {
      output(raw, cached, `实时翻译缓存 · OCR ${Math.round(confidence)}%`, `live|${normalized}`, startedAt);
      return;
    }

    fast.inFlightKey = normalized;
    const requestId = ++fast.requestNo;
    els.english.textContent = raw;
    els.chinese.textContent = '正在实时翻译……';
    els.meta.textContent = `字典未命中 · OCR ${Math.round(confidence)}% · 已立即发送翻译`;
    setStatus('正在翻译', true);

    try {
      const translated = polish(await translateCloud(raw));
      if (requestId !== fast.requestNo || !translated) return;
      fast.translationCache.set(normalized, translated);
      if (fast.translationCache.size > 160) fast.translationCache.delete(fast.translationCache.keys().next().value);
      output(raw, translated, `实时翻译 · OCR ${Math.round(confidence)}%`, `live|${normalized}`, startedAt);
    } finally {
      if (fast.inFlightKey === normalized) fast.inFlightKey = '';
    }
  }

  recognizeOnce = async function recognizeContinuousOnce() {
    if (!state.running || state.busy || !state.stream) return;
    state.busy = true;
    const startedAt = performance.now();
    try {
      const worker = await ensureWorker();
      const result = await worker.recognize(captureCrop());
      const raw = cleanResult(result);
      const confidence = Number(result?.data?.confidence || 0);
      state.lastRaw = raw;

      if (!looksLikeSubtitle(raw, confidence)) {
        if (els.detected) els.detected.textContent = '连续识别中：当前帧没有可靠英文字幕';
        setStatus('连续识别中', true);
        return;
      }

      const local = findLocalMatch(raw);
      if (local && Number(local.score || 0) >= 0.53 && dictionaryEvidence(raw, local)) {
        const chapter = local.item.chapter || local.entry?.chapter || '未分章';
        const order = Number(local.item.order || local.entry?.order || 0);
        const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';
        output(
          local.item.en,
          local.item.zh,
          `字典确认 · ${Math.round(Number(local.score || 0) * 100)}% · ${chapter} #${order}${speaker}`,
          `dict|${chapter}|${order}|${local.item.en}`,
          startedAt
        );
        fast.previousRaw = raw;
        fast.previousAt = Date.now();
        return;
      }

      const now = Date.now();
      const previousIsSame = fast.previousRaw
        && now - fast.previousAt < 1100
        && similarity(raw, fast.previousRaw) >= 0.48;
      fast.previousRaw = raw;
      fast.previousAt = now;

      const highConfidenceSingleFrame = confidence >= 58 && words(raw).length >= 2;
      if (!highConfidenceSingleFrame && !previousIsSame) {
        if (els.detected) els.detected.textContent = '字幕已出现，正在用下一帧快速纠错……';
        els.meta.textContent = `OCR ${Math.round(confidence)}% · 尚未达到单帧直出条件`;
        setStatus('快速确认中', true);
        return;
      }

      void translateImmediately(raw, confidence, startedAt);
    } catch (error) {
      console.error(error);
      setStatus('本帧失败，立即继续', true);
    } finally {
      state.busy = false;
      const elapsed = performance.now() - startedAt;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 8) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / Math.max(1, state.frameTimes.length);
      els.fpsText.textContent = average ? `连续 OCR ${Math.round(average)}ms` : '';
    }
  };

  scheduleNext = function scheduleContinuousNext() {
    clearTimeout(state.timer);
    if (!state.running) return;
    state.timer = setTimeout(async () => {
      await recognizeOnce();
      if (state.running) scheduleNext();
    }, 0);
  };

  document.title = 'COD11 连续实时翻译器 V9';
  const heading = document.querySelector('.empty-state h1');
  const intro = document.querySelector('.empty-state p');
  if (heading) heading.textContent = 'COD11 连续实时翻译器 V9';
  if (intro) intro.textContent = '上一帧结束后立即识别下一帧，不再按固定间隔抽查。';
  els.statusText.textContent = '未启动 · V9连续模式';

  if (els.scanInterval) {
    const label = els.scanInterval.closest('label');
    if (label?.firstChild) label.firstChild.textContent = '识别调度\n            ';
    els.scanInterval.innerHTML = '<option value="0" selected>连续流水线（无额外等待）</option>';
    els.scanInterval.disabled = true;
  }
  if (els.finishBeforeNext) {
    els.finishBeforeNext.checked = false;
    const label = els.finishBeforeNext.closest('label');
    if (label) label.lastChild.textContent = ' 新字幕出现时立即播报，不等待上一句';
  }
  if (els.cloudFallback) {
    els.cloudFallback.checked = true;
    els.cloudFallback.disabled = false;
  }
  if (els.detected) els.detected.textContent = '等待英文字幕进入识别框……';
  els.english.textContent = '';
  els.chinese.textContent = '';
  els.meta.textContent = 'V9连续模式：无固定扫描等待；字典直出，未命中立即翻译';

  const info = document.getElementById('libraryInfo');
  if (info) info.textContent = `已内置第6关中英台词 ${state.library.length} 条。字典用于快速确认；未命中时直接进入实时翻译。`;
})();
