'use strict';

(() => {
  const strict = {
    votes: [],
    lastKey: '',
    lastAt: 0,
    lastOrder: -1,
    lastChapter: '',
    contextAt: 0,
    lexicon: new Set(),
    timer: null
  };

  const COMMON = new Set('a an the and or but if then than to of in on at for from with without by is am are was were be been being do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how let start team copy move stay stop hold target mission'.split(' '));

  function words(text) {
    return String(text || '').toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  }

  function buildLexicon() {
    strict.lexicon.clear();
    for (const item of state.library || []) {
      const sources = [item?.en, ...(Array.isArray(item?.aliases) ? item.aliases : [])];
      for (const source of sources) {
        for (const word of words(source)) if (word.length >= 3) strict.lexicon.add(word);
      }
    }
  }

  function editDistance(a, b) {
    if (a === b) return 0;
    if (!a.length) return b.length;
    if (!b.length) return a.length;
    const row = Array.from({ length: b.length + 1 }, (_, i) => i);
    for (let i = 1; i <= a.length; i++) {
      let diagonal = row[0];
      row[0] = i;
      for (let j = 1; j <= b.length; j++) {
        const old = row[j];
        row[j] = Math.min(row[j] + 1, row[j - 1] + 1, diagonal + (a[i - 1] === b[j - 1] ? 0 : 1));
        diagonal = old;
      }
    }
    return row[b.length];
  }

  function dictionaryHits(raw) {
    const exact = [];
    const fuzzy = [];
    for (const word of [...new Set(words(raw))]) {
      if (word.length < 3 || COMMON.has(word)) continue;
      if (strict.lexicon.has(word)) {
        exact.push(word);
        continue;
      }
      if (word.length >= 5) {
        for (const known of strict.lexicon) {
          if (Math.abs(known.length - word.length) > 1) continue;
          if (known[0] !== word[0]) continue;
          if (editDistance(word, known) <= 1) {
            fuzzy.push(`${word}≈${known}`);
            break;
          }
        }
      }
    }
    return { exact, fuzzy };
  }

  function cleanFromResult(result) {
    const data = result?.data || {};
    const usableWords = Array.isArray(data.words)
      ? data.words.filter(item => Number(item?.confidence || 0) >= 32 && /^[A-Za-z][A-Za-z'’-]*$/.test(String(item?.text || '').trim()))
      : [];
    const text = usableWords.length >= 2
      ? usableWords.map(item => item.text).join(' ')
      : String(data.text || '');
    return normalizeText(text)
      .replace(/^[\-_=~]+|[\-_=~]+$/g, '')
      .replace(/\b[|Il]{4,}\b/g, ' ')
      .replace(/\s+/g, ' ')
      .trim();
  }

  function textQuality(raw) {
    const tokens = raw.split(/\s+/).filter(Boolean);
    const letterWords = words(raw);
    if (raw.length < 5 || raw.length > 170) return false;
    if (letterWords.length < 2 || letterWords.length > 28) return false;
    if (tokens.some(token => /[A-Za-z]/.test(token) && /\d/.test(token))) return false;
    const shortUnknown = letterWords.filter(word => word.length <= 2 && !COMMON.has(word));
    if (letterWords.length >= 3 && shortUnknown.length / letterWords.length > 0.25) return false;
    const weird = tokens.filter(token => /^[A-Z]{1,2}$/.test(token) || /^[A-Z][a-z]?[A-Z]$/.test(token));
    if (weird.length >= 2) return false;
    return true;
  }

  function clearInvalid(reason) {
    strict.votes = [];
    if (strict.timer) clearTimeout(strict.timer);
    if (els.detected) els.detected.textContent = '等待识别到有效的游戏英文字幕……';
    els.english.textContent = '';
    els.chinese.textContent = '';
    els.meta.textContent = reason || '未命中字典，本帧已忽略';
    els.speakAgain.disabled = true;
    state.lastChinese = '';
    setStatus('扫描中', true);
  }

  function candidateKey(local) {
    return `${local.item.chapter || ''}|${local.item.order || local.entry?.order || 0}|${local.item.en || ''}`;
  }

  function orderOf(local) {
    return Number(local.item.order || local.entry?.order || 0);
  }

  function sequenceOkay(local) {
    if (strict.lastOrder < 0 || Date.now() - strict.contextAt > 60000) return true;
    const chapter = local.item.chapter || local.entry?.chapter || '';
    if (chapter !== strict.lastChapter) return false;
    const delta = orderOf(local) - strict.lastOrder;
    return delta >= -1 && delta <= Number(els.sequenceWindow?.value || 8);
  }

  function voteFor(local, raw, confidence, hits) {
    const now = Date.now();
    const key = candidateKey(local);
    strict.votes.push({ key, local, raw, confidence, hits, at: now, score: Number(local.score || 0) });
    strict.votes = strict.votes.filter(vote => now - vote.at < 3500).slice(-4);
    const same = strict.votes.filter(vote => vote.key === key);
    const support = same.length;
    const bestScore = Math.max(...same.map(vote => vote.score));
    const bestConfidence = Math.max(...same.map(vote => vote.confidence));
    const bestEvidence = Math.max(...same.map(vote => vote.hits.exact.length * 2 + vote.hits.fuzzy.length));
    const required = Math.max(2, Number(els.stableFrames?.value || 2));
    const instant = bestScore >= 0.90 && bestConfidence >= 82 && bestEvidence >= 4;
    const stable = support >= required && bestScore >= 0.60 && bestEvidence >= 2;
    return { key, local, raw, support, required, bestScore, bestConfidence, bestEvidence, instant, stable };
  }

  function commit(vote) {
    const now = Date.now();
    if (vote.key === strict.lastKey && now - strict.lastAt < 9000) return;
    const local = vote.local;
    const chapter = local.item.chapter || local.entry?.chapter || '未分章';
    const order = orderOf(local);
    const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';

    strict.lastKey = vote.key;
    strict.lastAt = now;
    strict.lastOrder = order;
    strict.lastChapter = chapter;
    strict.contextAt = now;
    strict.votes = [];

    state.lastAccepted = local.item.en;
    state.lastAcceptedAt = now;
    state.lastChinese = local.item.zh;
    if (els.detected) els.detected.textContent = '已确认字典台词';
    els.english.textContent = local.item.en;
    els.chinese.textContent = local.item.zh;
    els.meta.textContent = `严格确认 · ${Math.round(vote.bestScore * 100)}% · ${vote.support}帧 · ${chapter} #${order}${speaker}`;
    els.speakAgain.disabled = false;
    addHistory(local.item.en, local.item.zh, els.meta.textContent);
    if (els.autoSpeak.checked) enqueueSpeech(local.item.zh);
    setStatus('扫描中', true);
  }

  recognizeOnce = async function recognizeStrictOnce() {
    if (!state.running || state.busy || !state.stream) return;
    state.busy = true;
    const started = performance.now();
    try {
      const worker = await ensureWorker();
      const result = await worker.recognize(captureCrop());
      const raw = cleanFromResult(result);
      const confidence = Number(result?.data?.confidence || 0);
      state.lastRaw = raw;

      if (!textQuality(raw)) {
        clearInvalid('没有检测到正常英文句子，背景乱码已丢弃');
        return;
      }

      const hits = dictionaryHits(raw);
      if (hits.exact.length < 1 && hits.fuzzy.length < 2) {
        clearInvalid('没有命中第6关台词关键词，本帧已丢弃');
        return;
      }

      const local = findLocalMatch(raw);
      if (!local || Number(local.score || 0) < 0.56 || !sequenceOkay(local)) {
        clearInvalid('未找到唯一且符合剧情顺序的字典台词');
        return;
      }

      const vote = voteFor(local, raw, confidence, hits);
      if (!vote.instant && !vote.stable) {
        if (els.detected) els.detected.textContent = `正在确认有效字幕 ${vote.support}/${vote.required}`;
        els.english.textContent = '';
        els.chinese.textContent = '';
        els.meta.textContent = '已命中字典，等待下一帧确认';
        setStatus('确认中', true);
        return;
      }

      commit(vote);
    } catch (error) {
      console.error(error);
      clearInvalid('本帧识别失败，已自动忽略');
    } finally {
      state.busy = false;
      const elapsed = performance.now() - started;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 8) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / Math.max(1, state.frameTimes.length);
      els.fpsText.textContent = average ? `OCR ${Math.round(average)}ms` : '';
    }
  };

  buildLexicon();
  if (els.chapter && [...els.chapter.options].some(option => option.value === '第6关')) els.chapter.value = '第6关';
  if (els.stableFrames) els.stableFrames.value = '2';
  els.english.textContent = '';
  els.chinese.textContent = '';
  els.meta.textContent = '严格模式：只有字典确认后才显示内容';
  if (els.detected) els.detected.textContent = '等待识别到有效的游戏英文字幕……';
  els.speakAgain.disabled = true;

  const info = document.getElementById('libraryInfo');
  if (info) info.textContent = `已内置第6关中英台词 ${state.library.length} 条。严格模式不会显示原始 OCR 乱码，只有连续命中字典后才显示翻译。`;
})();
