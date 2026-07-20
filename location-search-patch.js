(() => {
  'use strict';

  const OWNER = 'reward-aware-bilingual-search-v2';
  const MAX_RESULTS = 80;
  const STOP_WORDS = new Set(['所有', '全部', '的', '在', '里面', '地点', '给我', 'find', 'show', 'all', 'in', 'the', 'a', 'an']);
  let focusTicket = 0;

  function normalizeSearchText(value) {
    return String(value ?? '')
      .normalize('NFKD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase()
      .replace(/['’]/g, '')
      .replace(/[^\p{L}\p{N}]+/gu, ' ')
      .trim()
      .replace(/\s+/g, ' ');
  }

  function queryDocument(query) {
    const normalized = normalizeSearchText(query);
    const tokens = normalized
      .split(' ')
      .filter(token => token && !STOP_WORDS.has(token) && !(/^[a-z]$/.test(token)));
    return { normalized, tokens };
  }

  function includesToken(value, token) {
    return value.length > 0 && value.includes(token);
  }

  function rewardDocument(locationId) {
    const record = window.AtlasRewards?.getRecord?.(String(locationId));
    if (!record) return { items: [], summary: '', sources: '' };
    const rewards = Array.isArray(record.rewards) ? record.rewards : [];
    const sources = Array.isArray(record.sources) ? record.sources : [];
    return {
      items: rewards.map(reward => {
        const displayName = reward.nameZhCN || reward.nameOriginal || '奖励未确认';
        const nameText = normalizeSearchText([reward.nameOriginal, reward.nameZhCN].filter(Boolean).join(' '));
        return {
          displayName,
          nameText,
          text: normalizeSearchText([
            reward.nameOriginal,
            reward.nameZhCN,
            reward.type,
            reward.rarity,
            reward.quantity,
            reward.quantityStatus,
            reward.notesZhCN
          ].filter(value => value !== null && value !== undefined).join(' '))
        };
      }),
      summary: normalizeSearchText([record.summaryZhCN, record.status].filter(Boolean).join(' ')),
      sources: normalizeSearchText(sources.flatMap(source => [source.title, source.publisherOrAuthor]).filter(Boolean).join(' '))
    };
  }

  function locationDocument(location) {
    const category = state.categoryMap.get(location.category_id) || {};
    const region = state.regionMap.get(location.region_id) || {};
    return {
      category,
      region,
      title: normalizeSearchText([location.title_zh, location.title, location.title_en].filter(Boolean).join(' ')),
      titleZh: String(location.title_zh || location.title || ''),
      categoryText: normalizeSearchText([category.title, category.title_en].filter(Boolean).join(' ')),
      regionText: normalizeSearchText([region.title, region.title_en].filter(Boolean).join(' ')),
      description: normalizeSearchText(location.description || ''),
      reward: rewardDocument(location.id)
    };
  }

  function scoreLocation(location, index, query) {
    const document = locationDocument(location);
    if (!query.tokens.length) {
      return { location, index, score: 0, tier: 0, kind: '', label: '', rewardNames: [], document };
    }

    const exactTitle = document.title === query.normalized;
    const prefixTitle = !exactTitle && document.title.startsWith(query.normalized);
    const exactRewardItems = document.reward.items.filter(item => item.nameText === query.normalized);
    const prefixRewardItems = exactRewardItems.length ? [] : document.reward.items.filter(item => item.nameText.startsWith(query.normalized));
    const matchedRewards = new Map();
    let score = exactTitle ? 150 : prefixTitle ? 82 : 0;
    if (exactRewardItems.length) score += 145;
    else if (prefixRewardItems.length) score += 78;
    exactRewardItems.concat(prefixRewardItems).forEach(item => matchedRewards.set(item.displayName, item));

    let titleMatches = 0;
    let rewardMatches = 0;
    let taxonomyMatches = 0;
    let fallbackMatches = 0;

    for (const token of query.tokens) {
      let matched = false;
      if (includesToken(document.title, token)) { score += 30; titleMatches += 1; matched = true; }
      if (includesToken(document.categoryText, token)) { score += 15; taxonomyMatches += 1; matched = true; }
      if (includesToken(document.regionText, token)) { score += 15; taxonomyMatches += 1; matched = true; }

      for (const reward of document.reward.items) {
        if (includesToken(reward.nameText, token)) {
          score += 38;
          rewardMatches += 1;
          matchedRewards.set(reward.displayName, reward);
          matched = true;
        } else if (includesToken(reward.text, token)) {
          score += 18;
          rewardMatches += 1;
          matchedRewards.set(reward.displayName, reward);
          matched = true;
        }
      }

      if (includesToken(document.reward.summary, token) || includesToken(document.reward.sources, token)) {
        score += 7;
        fallbackMatches += 1;
        matched = true;
      }
      if (includesToken(document.description, token)) {
        score += 2;
        fallbackMatches += 1;
        matched = true;
      }
      if (!matched) return null;
    }

    let tier = 1;
    let kind = 'description';
    let label = '内容匹配';
    if (exactTitle) { tier = 7; kind = 'location-exact'; label = '地点精确匹配'; }
    else if (exactRewardItems.length) { tier = 7; kind = 'reward-exact'; label = '奖励精确匹配'; }
    else if (prefixTitle) { tier = 6; kind = 'location-prefix'; label = '地点前缀匹配'; }
    else if (prefixRewardItems.length) { tier = 6; kind = 'reward-prefix'; label = '奖励前缀匹配'; }
    else if (rewardMatches) { tier = 5; kind = 'reward'; label = '奖励匹配'; }
    else if (titleMatches) { tier = 4; kind = 'location'; label = '地点匹配'; }
    else if (taxonomyMatches) { tier = 3; kind = 'taxonomy'; label = '区域或类别匹配'; }
    else if (fallbackMatches) { tier = 2; }

    return {
      location,
      index,
      score,
      tier,
      kind,
      label,
      rewardNames: [...matchedRewards.keys()],
      document
    };
  }

  function focusAfterViewportSettles(location) {
    if (!location) return;
    const ticket = ++focusTicket;
    const input = el('searchInput');
    if (input) input.blur();
    closeSearch();

    const visual = window.visualViewport;
    const startedAt = performance.now();
    let lastWidth = -1;
    let lastHeight = -1;
    let stableFrames = 0;

    const settle = () => {
      if (ticket !== focusTicket) return;
      const width = Math.round(visual?.width || document.documentElement.clientWidth || innerWidth);
      const height = Math.round(visual?.height || document.documentElement.clientHeight || innerHeight);
      const scale = Number(visual?.scale || 1);
      const dimensionsStable = Math.abs(width - lastWidth) <= 1 && Math.abs(height - lastHeight) <= 1;
      const scaleStable = Math.abs(scale - 1) <= 0.02;
      stableFrames = dimensionsStable && scaleStable ? stableFrames + 1 : 0;
      lastWidth = width;
      lastHeight = height;

      if (stableFrames >= 2 || performance.now() - startedAt >= 480) {
        requestAnimationFrame(() => focusLocation(location));
        return;
      }
      setTimeout(() => requestAnimationFrame(settle), 38);
    };
    requestAnimationFrame(settle);
  }

  function install() {
    if (typeof state === 'undefined' || typeof el !== 'function' || typeof focusLocation !== 'function') {
      setTimeout(install, 30);
      return;
    }

    const results = el('searchResults');
    if (results && results.dataset.atlasSearchBound !== OWNER) {
      results.dataset.atlasSearchBound = OWNER;
      results.onclick = event => {
        const button = event.target.closest('.result-item[data-id]');
        if (!button || !results.contains(button)) return;
        const location = state.locations.find(item => String(item.id) === String(button.dataset.id));
        focusAfterViewportSettles(location);
      };
    }

    window.runSearch = function rewardAwareBilingualSearch(queryValue) {
      const query = queryDocument(queryValue);
      const allMatches = state.locations
        .map((location, index) => scoreLocation(location, index, query))
        .filter(Boolean)
        .sort((left, right) =>
          right.tier - left.tier ||
          right.score - left.score ||
          right.rewardNames.length - left.rewardNames.length ||
          left.document.titleZh.localeCompare(right.document.titleZh, 'zh-CN') ||
          left.index - right.index
        );
      const visibleMatches = allMatches.slice(0, MAX_RESULTS);

      el('resultCount').textContent = allMatches.length > MAX_RESULTS ? `${MAX_RESULTS}＋` : String(allMatches.length);
      el('searchResults').innerHTML = visibleMatches.map(item => {
        const location = item.location;
        const category = item.document.category;
        const region = item.document.region;
        const matchBadge = item.label
          ? `<span class="atlas-search-match ${item.kind.startsWith('reward') ? 'reward' : ''}">${escapeHTML(item.label)}</span>`
          : '';
        const rewardHint = item.rewardNames.length
          ? `<small class="atlas-search-reward">命中奖励：${escapeHTML(item.rewardNames.slice(0, 2).join(' · '))}</small>`
          : '';
        const title = location.title_zh || location.title;
        return `<button class="result-item" data-id="${escapeHTML(location.id)}" data-search-kind="${escapeHTML(item.kind)}" aria-label="打开 ${escapeHTML(title)}"><span class="result-icon">${iconMarkup(category?.title, 22)}</span><span class="result-copy"><span class="atlas-search-title-row"><b>${escapeHTML(title)}</b>${matchBadge}</span><small>${escapeHTML(category?.title || '')} · ${escapeHTML(region?.title || '未知区域')}</small>${rewardHint}</span><em>›</em></button>`;
      }).join('') || '<div class="empty-state">没有匹配结果</div>';
    };

    const input = el('searchInput');
    if (input) input.oninput = event => window.runSearch(event.target.value);
    window.AtlasSearchOwner = OWNER;
    window.AtlasSearch = Object.freeze({ owner: OWNER, normalizeSearchText, focusAfterViewportSettles });
    document.documentElement.dataset.atlasSearchOwner = OWNER;
  }

  function boot() {
    if (window.AtlasRewards?.refresh) {
      window.AtlasRewards.refresh().then(install, install);
    } else {
      setTimeout(boot, 30);
    }
  }

  document.readyState === 'loading'
    ? document.addEventListener('DOMContentLoaded', boot, { once: true })
    : boot();
})();