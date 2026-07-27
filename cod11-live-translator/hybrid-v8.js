'use strict';

(() => {
  const hybrid = {
    frames: [],
    lastOutputKey: '',
    lastOutputAt: 0,
    translating: false,
    glossaryReady: false
  };

  const COMMON = new Set('a an the and or but if then than to of in on at for from with without by is am are was were be been being do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how let make take keep move stay stop hold need know tell look give bring'.split(' '));

  function tokens(text) {
    return String(text || '').toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  }

  function cleanText(result) {
    let text = normalizeText(result?.data?.text || '');
    text = text
      .replace(/^[\-_=~]+|[\-_=~]+$/g, '')
      .replace(/\b[|Il]{4,}\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    return text;
  }

  function textQuality(text, confidence) {
    if (!text || text.length < 4 || text.length > 190) return false;
    const letters = (text.match(/[A-Za-z]/g) || []).length;
    if (letters < 4 || letters / Math.max(1, text.length) < 0.72) return false;

    const rawTokens = text.split(/\s+/).filter(Boolean);
    const words = tokens(text);
    if (!words.length || words.length > 32) return false;
    if (rawTokens.some(token => /[A-Za-z]/.test(token) && /\d/.test(token))) return false;

    const weird = rawTokens.filter(token => /^[A-Z]{1,3}$/.test(token) && !['KVA','UN','US'].includes(token));
    if (weird.length >= Math.max(2, Math.ceil(rawTokens.length * .35))) return false;

    const tiny = words.filter(word => word.length <= 2 && !COMMON.has(word));
    if (words.length >= 3 && tiny.length / words.length > .34) return false;

    const useful = words.filter(word => word.length >= 4 || COMMON.has(word));
    if (words.length >= 2 && useful.length < 2) return false;

    return Number(confidence || 0) >= 16;
  }

  function addFrame(raw, confidence) {
    const now = Date.now();
    hybrid.frames.push({ raw, confidence: Number(confidence || 0), at: now });
    hybrid.frames = hybrid.frames.filter(frame => now - frame.at < 4200).slice(-6);
  }

  function stableCluster() {
    if (!hybrid.frames.length) return null;
    const clusters = [];
    for (const frame of hybrid.frames) {
      let cluster = clusters.find(item => similarity(item.seed.raw, frame.raw) >= .50);
      if (!cluster) {
        cluster = { seed: frame, frames: [] };
        clusters.push(cluster);
      }
      cluster.frames.push(frame);
    }
    clusters.sort((a, b) => {
      const aScore = a.frames.length * 100 + Math.max(...a.frames.map(f => f.confidence));
      const bScore = b.frames.length * 100 + Math.max(...b.frames.map(f => f.confidence));
      return bScore - aScore;
    });
    const best = clusters[0];
    if (!best) return null;
    const chosen = best.frames.slice().sort((a, b) => {
      const aScore = a.confidence + Math.min(24, a.raw.length * .18);
      const bScore = b.confidence + Math.min(24, b.raw.length * .18);
      return bScore - aScore;
    })[0];
    const averageConfidence = best.frames.reduce((sum, frame) => sum + frame.confidence, 0) / best.frames.length;
    return {
      raw: chosen.raw,
      support: best.frames.length,
      bestConfidence: Math.max(...best.frames.map(frame => frame.confidence)),
      averageConfidence
    };
  }

  function dictionaryEvidence(raw, local) {
    if (!local?.item) return false;
    const sourceWords = new Set(tokens(raw));
    const targetWords = new Set(tokens([local.item.en, ...(local.item.aliases || [])].join(' ')));
    let overlap = 0;
    let strong = 0;
    sourceWords.forEach(word => {
      if (targetWords.has(word)) {
        overlap++;
        if (word.length >= 4 && !COMMON.has(word)) strong++;
      }
    });
    const score = Number(local.score || 0);
    return score >= .79 || strong >= 1 || overlap >= 2;
  }

  function polishTranslation(text) {
    let out = String(text || '').trim();
    const replacements = [
      [/哈迪斯/g, '冥王'],
      [/阿特拉斯/g, '巨神'],
      [/亚特拉斯/g, '巨神'],
      [/艾恩斯/g, '艾恩斯'],
      [/伊洛娜/g, '伊洛娜'],
      [/吉迪恩/g, '吉迪恩'],
      [/米切尔/g, '米切尔'],
      [/曼蒂科尔/g, '心智核心'],
      [/曼提科尔/g, '心智核心'],
      [/蝎尾狮计划/g, '心智核心计划'],
      [/圣托里尼/g, '圣托里尼'],
      [/钥匙人/g, '关键人'],
      [/关键人物/g, '关键人'],
      [/外骨骼服/g, '外骨骼'],
      [/阿特拉斯部队/g, '巨神部队']
    ];
    replacements.forEach(([pattern, value]) => { out = out.replace(pattern, value); });
    return out;
  }

  async function translateStable(raw) {
    const previous = els.cloudFallback?.checked;
    if (els.cloudFallback) els.cloudFallback.checked = true;
    try {
      const translated = await translateCloud(raw);
      return polishTranslation(translated);
    } finally {
      if (els.cloudFallback && previous === false) els.cloudFallback.checked = true;
    }
  }

  function showWaiting(message) {
    if (els.detected) els.detected.textContent = message || '等待稳定的英文对话字幕……';
    els.meta.textContent = '字典优先；未命中字典时自动实时翻译';
    setStatus('扫描中', true);
  }

  function outputResult(english, chinese, source, key) {
    const now = Date.now();
    if (key === hybrid.lastOutputKey && now - hybrid.lastOutputAt < 8000) return;
    hybrid.lastOutputKey = key;
    hybrid.lastOutputAt = now;
    hybrid.frames = [];

    state.lastAccepted = english;
    state.lastAcceptedAt = now;
    state.lastChinese = chinese;
    if (els.detected) els.detected.textContent = source.startsWith('字典') ? '已由台词字典确认' : '已由多帧 OCR 确认';
    els.english.textContent = english;
    els.chinese.textContent = chinese;
    els.meta.textContent = source;
    els.speakAgain.disabled = false;
    addHistory(english, chinese, source);
    if (els.autoSpeak.checked) enqueueSpeech(chinese);
    setStatus('扫描中', true);
  }

  recognizeOnce = async function recognizeHybridOnce() {
    if (!state.running || state.busy || !state.stream || hybrid.translating) return;
    state.busy = true;
    const started = performance.now();
    try {
      const worker = await ensureWorker();
      const result = await worker.recognize(captureCrop());
      const raw = cleanText(result);
      const confidence = Number(result?.data?.confidence || 0);
      state.lastRaw = raw;

      if (!textQuality(raw, confidence)) {
        showWaiting('未检测到可靠英文字幕，继续扫描……');
        return;
      }

      addFrame(raw, confidence);
      const stable = stableCluster();
      if (!stable || stable.support < 2) {
        if (els.detected) els.detected.textContent = `正在合并字幕帧 ${stable?.support || 1}/2`;
        els.meta.textContent = '正在确认英文内容，避免把背景纹理当成字幕';
        setStatus('确认中', true);
        return;
      }

      const local = findLocalMatch(stable.raw);
      if (local && Number(local.score || 0) >= .56 && dictionaryEvidence(stable.raw, local)) {
        const chapter = local.item.chapter || local.entry?.chapter || '未分章';
        const order = Number(local.item.order || local.entry?.order || 0);
        const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';
        outputResult(
          local.item.en,
          local.item.zh,
          `字典确认 · ${Math.round(Number(local.score || 0) * 100)}% · ${stable.support}帧 · ${chapter} #${order}${speaker}`,
          `dict|${chapter}|${order}|${local.item.en}`
        );
        return;
      }

      if (stable.averageConfidence < 30 && stable.bestConfidence < 48) {
        showWaiting('英文字幕清晰度不足，继续读取下一帧……');
        return;
      }

      hybrid.translating = true;
      if (els.detected) els.detected.textContent = `已确认英文：${stable.raw}`;
      els.english.textContent = stable.raw;
      els.chinese.textContent = '正在翻译……';
      els.meta.textContent = `字典未命中 · 多帧 OCR ${stable.support}帧 · 正在实时翻译`;
      setStatus('正在翻译', true);

      const chinese = await translateStable(stable.raw);
      if (!chinese) {
        els.chinese.textContent = '实时翻译暂时不可用，请检查网络后继续。';
        els.meta.textContent = '字典未命中；在线翻译服务未返回结果';
        return;
      }

      outputResult(
        stable.raw,
        chinese,
        `实时翻译 · 多帧 OCR ${stable.support}帧 · OCR ${Math.round(stable.averageConfidence)}%`,
        `live|${comparable(stable.raw)}`
      );
    } catch (error) {
      console.error(error);
      showWaiting('本帧识别失败，已自动继续……');
    } finally {
      hybrid.translating = false;
      state.busy = false;
      const elapsed = performance.now() - started;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 8) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / Math.max(1, state.frameTimes.length);
      els.fpsText.textContent = average ? `OCR ${Math.round(average)}ms` : '';
    }
  };

  document.title = 'COD11 混合字幕翻译器 V8';
  const heading = document.querySelector('.empty-state h1');
  const intro = document.querySelector('.empty-state p');
  if (heading) heading.textContent = 'COD11 混合字幕翻译器 V8';
  if (intro) intro.textContent = '字典优先确认；未命中的字幕自动进行多帧识别与实时翻译。';
  els.statusText.textContent = '未启动 · V8混合模式';
  if (els.cloudFallback) {
    els.cloudFallback.disabled = false;
    els.cloudFallback.checked = true;
    const label = els.cloudFallback.closest('label');
    if (label) label.lastChild.textContent = ' 字典未命中时自动实时翻译';
  }
  if (els.english) els.english.textContent = '';
  if (els.chinese) els.chinese.textContent = '';
  if (els.detected) els.detected.textContent = '等待稳定的英文对话字幕……';
  els.meta.textContent = 'V8混合模式：字典确认 + 多帧OCR实时翻译';
  const info = document.getElementById('libraryInfo');
  if (info) info.textContent = `已内置第6关中英台词 ${state.library.length} 条。字典用于优先确认和纠错，未命中的内容仍会自动翻译。`;
})();