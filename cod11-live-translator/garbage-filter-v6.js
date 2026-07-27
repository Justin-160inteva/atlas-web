'use strict';

(() => {
  const guard = {
    votes: [],
    lastKey: '',
    lastAt: 0,
    lastOrder: -1,
    lastChapter: '',
    contextAt: 0,
    lexicon: new Set()
  };

  const COMMON = new Set('a an the and or but if then than to of in on at for from with without by is am are was were be been being do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how let start who what where team copy move stay stop hold target mission'.split(' '));

  function wordTokens(text) {
    return String(text || '').toLowerCase().match(/[a-z]+(?:'[a-z]+)?/g) || [];
  }

  function rebuildLexicon() {
    guard.lexicon.clear();
    for (const item of state.library || []) {
      const surfaces = [item?.en, ...(Array.isArray(item?.aliases) ? item.aliases : [])];
      for (const surface of surfaces) {
        for (const token of wordTokens(surface)) {
          if (token.length >= 3) guard.lexicon.add(token);
        }
      }
    }
  }

  function basicTextQuality(raw, confidence) {
    const text = String(raw || '').trim();
    if (text.length < 4 || text.length > 180) return false;
    const letters = (text.match(/[A-Za-z]/g) || []).length;
    if (letters < 4 || letters / Math.max(1, text.length) < 0.62) return false;

    const rawTokens = text.split(/\s+/).filter(Boolean);
    const words = wordTokens(text);
    if (!words.length || words.length > 30) return false;

    const mixedJunk = rawTokens.filter(token => /[A-Za-z]/.test(token) && /\d/.test(token)).length;
    if (mixedJunk > 0) return false;

    const tinyUnknown = words.filter(word => word.length <= 2 && !COMMON.has(word)).length;
    if (words.length >= 3 && tinyUnknown / words.length > 0.34) return false;

    const oddCaps = rawTokens.filter(token => /^[A-Z][a-z]?[A-Z]$/.test(token) || /^[a-z][A-Z]$/.test(token)).length;
    if (oddCaps >= 2) return false;

    return confidence >= 12;
  }

  function dictionaryEvidence(raw, local) {
    if (!local?.item) return { valid: false, hits: [], strongHits: [] };
    const words = [...new Set(wordTokens(raw))];
    const hits = words.filter(word => guard.lexicon.has(word));
    const strongHits = hits.filter(word => word.length >= 4 && !COMMON.has(word));
    const score = Number(local.score || 0);
    const valid = strongHits.length >= 1 || hits.length >= 2 || (score >= 0.84 && hits.length >= 1);
    return { valid, hits, strongHits };
  }

  function candidateKey(local) {
    return `${local.item.chapter || ''}|${local.item.order || local.entry?.order || 0}|${local.item.en || ''}`;
  }

  function candidateOrder(local) {
    return Number(local.item.order || local.entry?.order || 0);
  }

  function sequenceAllowed(local) {
    if (guard.lastOrder < 0 || Date.now() - guard.contextAt > 60000) return true;
    const chapter = local.item.chapter || local.entry?.chapter || '';
    if (chapter !== guard.lastChapter) return false;
    const delta = candidateOrder(local) - guard.lastOrder;
    const windowSize = Number(els.sequenceWindow?.value || 8);
    return delta >= -1 && delta <= windowSize;
  }

  function addVote(local, raw, confidence, evidence) {
    const now = Date.now();
    const key = candidateKey(local);
    guard.votes.push({ key, local, raw, confidence, evidence, at: now, score: Number(local.score || 0) });
    guard.votes = guard.votes.filter(vote => now - vote.at < 4200).slice(-5);

    const same = guard.votes.filter(vote => vote.key === key);
    const support = same.length;
    const bestScore = Math.max(...same.map(vote => vote.score));
    const bestConfidence = Math.max(...same.map(vote => vote.confidence));
    const maxStrongHits = Math.max(...same.map(vote => vote.evidence.strongHits.length));
    const required = Math.max(2, Number(els.stableFrames?.value || 2));
    const veryStrong = bestScore >= 0.88 && bestConfidence >= 78 && maxStrongHits >= 2;
    const stable = support >= required && bestScore >= 0.56;
    return { key, local, raw, support, required, bestScore, bestConfidence, veryStrong, stable };
  }

  function quietlyWait(reason) {
    if (els.detected) els.detected.textContent = '等待可确认的对话字幕……';
    els.meta.textContent = reason || '未检测到字典中的有效台词关键词，继续扫描';
    setStatus('扫描中', true);
  }

  function commitCandidate(vote) {
    const local = vote.local;
    const now = Date.now();
    if (vote.key === guard.lastKey && now - guard.lastAt < 9000) {
      quietlyWait('同一句字幕仍在画面中，已忽略重复识别');
      return;
    }

    const chapter = local.item.chapter || local.entry?.chapter || '未分章';
    const order = candidateOrder(local);
    const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';
    const source = `字典确认 · ${Math.round(vote.bestScore * 100)}% · ${vote.support}帧 · ${chapter} #${order}${speaker}`;

    guard.lastKey = vote.key;
    guard.lastAt = now;
    guard.lastOrder = order;
    guard.lastChapter = chapter;
    guard.contextAt = now;
    guard.votes = [];

    state.lastAccepted = local.item.en;
    state.lastAcceptedAt = now;
    state.lastChinese = local.item.zh;
    if (els.detected) els.detected.textContent = `已确认片段：${vote.raw}`;
    els.english.textContent = local.item.en;
    els.chinese.textContent = local.item.zh;
    els.meta.textContent = source;
    els.speakAgain.disabled = false;
    addHistory(local.item.en, local.item.zh, source);
    if (els.autoSpeak.checked) enqueueSpeech(local.item.zh);
    setStatus('扫描中', true);
  }

  const previousPause = pauseRecognition;
  pauseRecognition = function pauseWithGarbageReset() {
    guard.votes = [];
    previousPause();
  };

  recognizeOnce = async function recognizeGuardedOnce() {
    if (!state.running || state.busy || !state.stream) return;
    state.busy = true;
    const started = performance.now();
    try {
      const worker = await ensureWorker();
      const canvas = captureCrop();
      const result = await worker.recognize(canvas);
      let raw = normalizeText(result?.data?.text || '');
      raw = raw
        .replace(/^[\-_=~]+|[\-_=~]+$/g, '')
        .replace(/\b[|Il]{4,}\b/g, ' ')
        .replace(/\s+/g, ' ')
        .trim();
      const confidence = Number(result?.data?.confidence || 0);
      state.lastRaw = raw;

      if (!basicTextQuality(raw, confidence)) {
        quietlyWait('画面中没有清晰的英文对话字幕，背景识别结果已丢弃');
        return;
      }

      const local = findLocalMatch(raw);
      const evidence = dictionaryEvidence(raw, local);
      if (!evidence.valid || !sequenceAllowed(local)) {
        quietlyWait(local ? '候选不符合字典关键词或剧情顺序，已丢弃' : '没有命中第6关台词字典，继续扫描');
        return;
      }

      const vote = addVote(local, raw, confidence, evidence);
      if (!vote.veryStrong && !vote.stable) {
        if (els.detected) els.detected.textContent = `正在确认字幕片段…… ${vote.support}/${vote.required}`;
        els.meta.textContent = `已命中字典候选，等待下一帧确认 · OCR ${Math.round(confidence)}%`;
        setStatus('确认中', true);
        return;
      }

      commitCandidate(vote);
    } catch (error) {
      console.error(error);
      quietlyWait('本帧识别失败，已自动继续');
    } finally {
      state.busy = false;
      const elapsed = performance.now() - started;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 8) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / Math.max(1, state.frameTimes.length);
      els.fpsText.textContent = average ? `OCR ${Math.round(average)}ms` : '';
    }
  };

  rebuildLexicon();
  const info = document.getElementById('libraryInfo');
  if (info) info.textContent = `已内置第6关中英台词 ${state.library.length} 条。未命中字典关键词的 OCR 结果会直接丢弃，不再显示乱码。`;
  if (/没有找到唯一匹配|未识别到对应中文/.test(els.chinese?.textContent || '')) {
    els.english.textContent = '等待完整台词……';
    els.chinese.textContent = '等待检测到游戏对话字幕';
    els.meta.textContent = '';
  }

  const style = document.createElement('style');
  style.textContent = '.crop-box{z-index:7!important}.crop-label{z-index:8!important}.translation-panel{z-index:5!important}';
  document.head.appendChild(style);
})();