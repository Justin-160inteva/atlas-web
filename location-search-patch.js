(() => {
  'use strict';

  function rewardDocument(locationId) {
    const record = window.AtlasRewards?.getRecord?.(String(locationId));
    if (!record) return { text: '', names: [] };
    const rewards = Array.isArray(record.rewards) ? record.rewards : [];
    const sources = Array.isArray(record.sources) ? record.sources : [];
    return {
      names: rewards.map(reward => reward.nameZhCN || reward.nameOriginal).filter(Boolean),
      text: [
        record.summaryZhCN,
        record.status,
        ...rewards.flatMap(reward => [reward.nameOriginal, reward.nameZhCN, reward.type, reward.rarity, reward.quantity]),
        ...sources.flatMap(source => [source.title, source.publisherOrAuthor])
      ].filter(value => value !== null && value !== undefined).join(' ').toLowerCase()
    };
  }

  function install() {
    if (typeof state === 'undefined' || typeof smartTokens !== 'function' || typeof el !== 'function') {
      setTimeout(install, 30);
      return;
    }

    runSearch = function rewardAwareBilingualSearch(query) {
      const tokens = smartTokens(query);
      const scored = state.locations.map(location => {
        const category = state.categoryMap.get(location.category_id) || {};
        const region = state.regionMap.get(location.region_id) || {};
        const titleZh = String(location.title_zh || location.title || '');
        const titleEn = String(location.title_en || '');
        const categoryZh = String(category.title || '');
        const categoryEn = String(category.title_en || '');
        const regionZh = String(region.title || '');
        const regionEn = String(region.title_en || '');
        const baseText = `${titleZh} ${titleEn} ${categoryZh} ${categoryEn} ${regionZh} ${regionEn} ${location.description || ''}`.toLowerCase();
        const reward = rewardDocument(location.id);
        let score = 0;
        let rewardMatches = 0;

        for (const token of tokens) {
          let matched = false;
          if (titleZh.toLowerCase().includes(token) || titleEn.toLowerCase().includes(token)) { score += 8; matched = true; }
          if (categoryZh.toLowerCase().includes(token) || categoryEn.toLowerCase().includes(token)) { score += 5; matched = true; }
          if (regionZh.toLowerCase().includes(token) || regionEn.toLowerCase().includes(token)) { score += 5; matched = true; }
          if (baseText.includes(token)) { score += 1; matched = true; }
          if (reward.text.includes(token)) { score += 10; rewardMatches += 1; matched = true; }
          if (!matched) return { location, score: -1, rewardMatches: 0, rewardNames: [] };
        }

        return { location, score, rewardMatches, rewardNames: reward.names };
      }).filter(item => !tokens.length || item.score >= 0)
        .sort((left, right) => right.score - left.score || right.rewardMatches - left.rewardMatches)
        .slice(0, 80);

      el('resultCount').textContent = scored.length + (scored.length === 80 ? '＋' : '');
      el('searchResults').innerHTML = scored.map(item => {
        const location = item.location;
        const category = state.categoryMap.get(location.category_id);
        const region = state.regionMap.get(location.region_id);
        const rewardHint = item.rewardMatches && item.rewardNames.length
          ? `<small class="atlas-search-reward">奖励：${escapeHTML(item.rewardNames.slice(0, 2).join(' · '))}</small>`
          : '';
        return `<button class="result-item" data-id="${escapeHTML(location.id)}"><span class="result-icon">${iconMarkup(category?.title, 22)}</span><span class="result-copy"><b>${escapeHTML(location.title_zh || location.title)}</b><small>${escapeHTML(category?.title || '')} · ${escapeHTML(region?.title || '未知区域')}</small>${rewardHint}</span><em>›</em></button>`;
      }).join('') || '<div class="empty-state">没有匹配结果</div>';

      document.querySelectorAll('.result-item').forEach(button => {
        button.onclick = () => {
          const location = state.locations.find(item => item.id === button.dataset.id);
          closeSearch();
          focusLocation(location);
        };
      });
    };

    const input = el('searchInput');
    if (input) input.oninput = event => runSearch(event.target.value);
    window.AtlasSearchOwner = 'reward-aware-bilingual-search';
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
