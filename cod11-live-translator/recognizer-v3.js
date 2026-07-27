'use strict';

(() => {
  const STOPWORDS = new Set('a an the and or but if then than to of in on at for from with without by is am are was were be been being do does did have has had i you he she it we they me him her us them my your his its our their this that these those there here now just get got go come can could will would should must not no yes up down out into over back all any some one two three what when where who why how'.split(' '));
  let dialogueIndex = null;
  let lastMatchedIndex = -1;
  let lastMatchedChapter = '';
  let lastMatchedAt = 0;

  function addRecognizerUI() {
    document.title = 'COD11 专用台词识别器';
    const heading = document.querySelector('.empty-state h1');
    const intro = document.querySelector('.empty-state p');
    if (heading) heading.textContent = 'COD11 专用台词识别器';
    if (intro) intro.textContent = '识别到半句或关键词，立即定位完整台词和精准中文。';

    const panel = document.querySelector('.translation-panel');
    if (panel && !document.getElementById('detectedText')) {
      const detected = document.createElement('div');
      detected.id = 'detectedText';
      detected.className = 'detected';
      detected.textContent = '识别片段：等待字幕……';
      const label = document.createElement('div');
      label.className = 'full-line-label';
      label.textContent = '匹配到的完整英文台词';
      panel.insertBefore(label, panel.firstChild);
      panel.insertBefore(detected, label);
    }

    const settings = document.querySelector('#chapterSelect')?.closest('.settings-grid');
    if (settings && !document.getElementById('minKeywords')) {
      settings.insertAdjacentHTML('beforeend', `
        <label>最少命中关键词
          <input id="minKeywords" type="range" min="1" max="4" step="1" value="2" />
          <output id="minKeywordsValue">2 个</output>
        </label>
        <label class="checkbox"><input id="fragmentMode" type="checkbox" checked /> 片段命中完整台词</label>
        <label class="checkbox"><input id="contextMode" type="checkbox" checked /> 根据前后台词顺序消除歧义</label>
      `);
    }

    const thresholdLabel = document.getElementById('matchThreshold')?.closest('label');
    if (thresholdLabel?.firstChild) thresholdLabel.firstChild.textContent = '完整台词命中置信度\n            ';
    if (els.threshold) {
      els.threshold.value = '0.64';
      els.thresholdValue.textContent = '64%';
    }
    if (els.cloudFallback) {
      els.cloudFallback.checked = false;
      const label = els.cloudFallback.closest('label');
      if (label) label.lastChild.textContent = ' 未命中时临时联网翻译（可能不精准）';
    }

    const info = document.getElementById('libraryInfo');
    if (info) info.textContent = `当前专用台词库：${state.library.length} 句。识别到一小段或关键词后，会定位并输出完整原句与完整中文。`;

    const style = document.createElement('style');
    style.textContent = `
      .detected{font-size:12px;color:#9aa5b2;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
      .full-line-label{margin-top:5px;color:var(--accent);font-size:11px;font-weight:800;letter-spacing:.08em}
      .english{font-size:clamp(14px,2.2vw,20px)!important;color:#e1e7ef!important;font-weight:650}
    `;
    document.head.appendChild(style);

    els.detected = document.getElementById('detectedText');
    els.minKeywords = document.getElementById('minKeywords');
    els.minKeywordsValue = document.getElementById('minKeywordsValue');
    els.fragmentMode = document.getElementById('fragmentMode');
    els.contextMode = document.getElementById('contextMode');
    els.minKeywords?.addEventListener('input', () => { els.minKeywordsValue.textContent = `${els.minKeywords.value} 个`; });
  }

  function tokens(text) {
    return comparable(text).split(' ').filter(Boolean);
  }
  function keywords(text) {
    return tokens(text).filter(word => word.length >= 3 && !STOPWORDS.has(word));
  }
  function charTrigrams(text) {
    const compact = comparable(text).replace(/\s+/g, '');
    const out = new Set();
    if (compact.length < 3) {
      if (compact) out.add(compact);
      return out;
    }
    for (let i = 0; i <= compact.length - 3; i++) out.add(compact.slice(i, i + 3));
    return out;
  }
  function dice(a, b) {
    const ag = charTrigrams(a), bg = charTrigrams(b);
    if (!ag.size || !bg.size) return 0;
    let hits = 0;
    ag.forEach(value => { if (bg.has(value)) hits++; });
    return (2 * hits) / (ag.size + bg.size);
  }
  function windowSimilarity(fragment, full) {
    const fragmentTokens = tokens(fragment);
    const fullTokens = tokens(full);
    if (!fragmentTokens.length || !fullTokens.length) return 0;
    if (fullTokens.length <= fragmentTokens.length + 1) return similarity(fragment, full);
    let best = 0;
    const minSize = Math.max(1, fragmentTokens.length - 1);
    const maxSize = Math.min(fullTokens.length, fragmentTokens.length + 2);
    for (let size = minSize; size <= maxSize; size++) {
      for (let i = 0; i <= fullTokens.length - size; i++) {
        best = Math.max(best, similarity(fragment, fullTokens.slice(i, i + size).join(' ')));
      }
    }
    return best;
  }

  function buildDialogueIndex() {
    const tokenFrequency = new Map();
    const inverted = new Map();
    const chapterCounters = new Map();
    const entries = state.library.map((item, index) => {
      const chapter = item.chapter || '未分章';
      const order = (chapterCounters.get(chapter) || 0) + 1;
      chapterCounters.set(chapter, order);
      const aliases = Array.isArray(item.aliases) ? item.aliases : [];
      const surfaces = [item.en, ...aliases].filter(Boolean);
      const keySet = new Set(surfaces.flatMap(keywords));
      keySet.forEach(token => tokenFrequency.set(token, (tokenFrequency.get(token) || 0) + 1));
      return { item, index, chapter, order, surfaces, keySet };
    });
    entries.forEach(entry => entry.keySet.forEach(token => {
      if (!inverted.has(token)) inverted.set(token, new Set());
      inverted.get(token).add(entry.index);
    }));
    dialogueIndex = { entries, tokenFrequency, inverted, total: Math.max(1, entries.length) };
  }

  function activeEntries() {
    if (!dialogueIndex) buildDialogueIndex();
    const chapter = els.chapter?.value || 'all';
    return chapter === 'all' ? dialogueIndex.entries : dialogueIndex.entries.filter(entry => entry.chapter === chapter);
  }
  function sequenceBonus(entry) {
    if (!els.contextMode?.checked || lastMatchedIndex < 0 || Date.now() - lastMatchedAt > 45000) return 0;
    if (entry.chapter !== lastMatchedChapter) return 0;
    const previous = dialogueIndex.entries[lastMatchedIndex];
    if (!previous) return 0;
    const delta = entry.order - previous.order;
    if (delta === 1) return 0.13;
    if (delta === 2) return 0.08;
    if (delta === 0) return 0.03;
    if (delta === -1) return 0.02;
    return 0;
  }
  function scoreCandidate(fragment, entry, recognizedKeywords) {
    const fragmentText = comparable(fragment);
    let contains = 0, fullSimilarity = 0, bestWindow = 0, bestDice = 0;
    for (const surface of entry.surfaces) {
      const target = comparable(surface);
      if (!target) continue;
      if (target.includes(fragmentText) && fragmentText.length >= 4) {
        contains = Math.max(contains, Math.min(1, 0.78 + fragmentText.length / Math.max(20, target.length) * 0.22));
      }
      if (fragmentText.includes(target) && target.length >= 4) contains = Math.max(contains, 0.96);
      fullSimilarity = Math.max(fullSimilarity, similarity(fragment, surface));
      bestWindow = Math.max(bestWindow, windowSimilarity(fragment, surface));
      bestDice = Math.max(bestDice, dice(fragment, surface));
    }

    let matched = 0, matchedWeight = 0, totalWeight = 0, rarest = Infinity;
    for (const token of recognizedKeywords) {
      const frequency = dialogueIndex.tokenFrequency.get(token) || dialogueIndex.total;
      const weight = Math.log((dialogueIndex.total + 1) / (frequency + 1)) + 1;
      totalWeight += weight;
      if (entry.keySet.has(token)) {
        matched++;
        matchedWeight += weight;
        rarest = Math.min(rarest, frequency);
      }
    }
    const keywordRecall = totalWeight ? matchedWeight / totalWeight : 0;
    const base = Math.max(contains, fullSimilarity * 0.38 + bestWindow * 0.30 + bestDice * 0.14 + keywordRecall * 0.28);
    return { score: Math.min(1, base + sequenceBonus(entry)), matched, rarest, contains, bestWindow };
  }

  function fragmentMatcher(text) {
    if (!els.fragmentMode?.checked) {
      let best = null, bestScore = 0;
      for (const entry of activeEntries()) {
        const current = similarity(text, entry.item.en);
        if (current > bestScore) { best = entry; bestScore = current; }
      }
      return best && bestScore >= Number(els.threshold.value) ? { item: best.item, entry: best, score: bestScore, matched: keywords(text).length } : null;
    }

    const recognizedKeywords = [...new Set(keywords(text))];
    const minKeywords = Number(els.minKeywords?.value || 2);
    const active = activeEntries();
    const activeIds = new Set(active.map(entry => entry.index));
    const candidateIds = new Set();
    recognizedKeywords.forEach(token => dialogueIndex.inverted.get(token)?.forEach(id => { if (activeIds.has(id)) candidateIds.add(id); }));
    const candidates = candidateIds.size ? [...candidateIds].map(id => dialogueIndex.entries[id]) : active;
    const ranked = [];
    for (const entry of candidates) {
      const detail = scoreCandidate(text, entry, recognizedKeywords);
      const oneRareKeyword = detail.matched === 1 && detail.rarest <= 2 && recognizedKeywords.some(word => word.length >= 6 && entry.keySet.has(word));
      const enoughEvidence = detail.matched >= minKeywords || oneRareKeyword || detail.contains >= 0.88;
      if (enoughEvidence) ranked.push({ item: entry.item, entry, ...detail });
    }
    ranked.sort((a, b) => b.score - a.score);
    const best = ranked[0], second = ranked[1];
    if (!best) return null;
    const margin = best.score - (second?.score || 0);
    const threshold = Number(els.threshold.value);
    const strongPhrase = best.contains >= 0.92 || best.bestWindow >= 0.86;
    const resolvedBySequence = sequenceBonus(best.entry) >= 0.08 && best.score >= threshold - 0.05;
    if (best.score < threshold || (margin < 0.035 && !strongPhrase && !resolvedBySequence)) return null;
    return { ...best, margin };
  }

  const originalSaveLibrary = saveLibrary;
  saveLibrary = function patchedSaveLibrary() {
    originalSaveLibrary();
    buildDialogueIndex();
    const info = document.getElementById('libraryInfo');
    if (info) info.textContent = `当前专用台词库：${state.library.length} 句。识别到一小段或关键词后，会定位并输出完整原句与完整中文。`;
  };
  findLocalMatch = fragmentMatcher;

  recognizeOnce = async function recognizeDialogueFragment() {
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
      if (els.detected) els.detected.textContent = `识别片段：${raw}`;
      els.english.textContent = raw;

      const local = fragmentMatcher(raw);
      let chinese = null;
      let source = '';
      if (local) {
        if (local.entry.index === lastMatchedIndex && Date.now() - lastMatchedAt < 6500) {
          els.meta.textContent = '同一条完整台词，已忽略重复片段';
          setStatus('扫描中', true);
          return;
        }
        chinese = local.item.zh;
        els.english.textContent = local.item.en;
        const speaker = local.item.speaker ? ` · ${local.item.speaker}` : '';
        source = `完整台词命中 · ${Math.round(local.score * 100)}% · ${local.matched || 0} 个关键词 · ${local.item.chapter || '未分章'}${speaker}`;
        lastMatchedIndex = local.entry.index;
        lastMatchedChapter = local.entry.chapter;
        lastMatchedAt = Date.now();
      } else if (els.cloudFallback.checked) {
        setStatus('正在临时翻译…', true);
        chinese = await translateCloud(raw);
        source = chinese ? '未命中专用台词库 · 临时联网翻译' : '未找到唯一完整台词';
      } else {
        source = '未找到唯一完整台词';
      }

      if (!chinese) {
        els.chinese.textContent = '没有找到唯一匹配的完整台词。请确认已导入对应章节的完整中英台词库。';
        els.meta.textContent = source;
        return;
      }

      state.lastAccepted = local ? local.item.en : raw;
      state.lastAcceptedAt = Date.now();
      state.lastChinese = chinese;
      els.chinese.textContent = chinese;
      els.meta.textContent = source;
      els.speakAgain.disabled = false;
      addHistory(local ? local.item.en : raw, chinese, source);
      if (els.autoSpeak.checked) enqueueSpeech(chinese);
      setStatus('扫描中', true);
    } catch (error) {
      console.error(error);
      setStatus('识别出错，继续重试', true);
    } finally {
      state.busy = false;
      const elapsed = performance.now() - started;
      state.frameTimes.push(elapsed);
      if (state.frameTimes.length > 10) state.frameTimes.shift();
      const average = state.frameTimes.reduce((sum, value) => sum + value, 0) / state.frameTimes.length;
      els.fpsText.textContent = average ? `识别 ${Math.round(average)}ms` : '';
    }
  };

  addRecognizerUI();
  buildDialogueIndex();
})();
