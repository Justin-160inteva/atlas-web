'use strict';
(() => {
  const INDEX_URL = 'data/rewards/reward-evidence-index.json';
  const RECORDS_URL = 'data/rewards/reward-records-runtime.json';
  const STATUS_LABELS = {
    official_confirmed: '官方确认',
    multi_source_confirmed: '多来源确认',
    high_confidence_inference: '高置信推断',
    unresolved: '尚未解决'
  };
  const runtime = {
    coverage: null,
    records: new Map(),
    ready: false,
    loading: null
  };

  const escapeHTML = value => String(value ?? '').replace(/[&<>"']/g, char => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'
  }[char]));

  async function loadJSON(url) {
    const response = await fetch(url, { cache: 'no-store' });
    if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
    return response.json();
  }

  async function loadRuntimeRecords(recordIndex) {
    const records = new Map(Object.entries(recordIndex.records || {}));
    const fileEntries = Object.entries(recordIndex.recordFiles || {});
    const results = await Promise.allSettled(fileEntries.map(async ([locationId, path]) => {
      const record = await loadJSON(path);
      if (String(record.locationId) !== String(locationId)) {
        throw new Error(`${path}: locationId 与运行时索引不一致`);
      }
      return [String(locationId), record];
    }));
    results.forEach((result, index) => {
      if (result.status === 'fulfilled') {
        records.set(result.value[0], result.value[1]);
      } else {
        console.warn('[Atlas Rewards] 奖励记录加载失败', fileEntries[index]?.[1], result.reason);
      }
    });
    const expected = Number(recordIndex.recordCount || records.size);
    if (records.size !== expected) {
      console.warn(`[Atlas Rewards] 奖励记录数量不完整：${records.size}/${expected}`);
    }
    return records;
  }

  function selectedLocationId() {
    try {
      return typeof state !== 'undefined' && state.selected ? String(state.selected.id) : null;
    } catch (_error) {
      return null;
    }
  }

  function rewardSupportCount(reward, sources) {
    const token = `reward:${reward.type}:${reward.nameOriginal || reward.nameZhCN}`;
    return sources.filter(source => Array.isArray(source.supports) && source.supports.includes(token)).length;
  }

  function formatQuantity(reward, sources) {
    const name = escapeHTML(reward.nameZhCN || '奖励未确认');
    const supportCount = rewardSupportCount(reward, sources);
    const sourceBadgeText = `${supportCount}个来源`;
    const badge = `<span title="可复查来源数量">${sourceBadgeText}</span>`;
    if (reward.quantityStatus === 'not_applicable') return `${name}${badge}`;
    if (reward.quantityStatus === 'exact' && Number.isFinite(reward.quantity)) {
      return `${escapeHTML(reward.quantity)} × ${name}${badge}`;
    }
    if (reward.quantityStatus === 'minimum' && Number.isFinite(reward.quantity)) {
      return `至少 ${escapeHTML(reward.quantity)} × ${name}${badge}`;
    }
    return `${name}<span title="可复查来源数量">数量未确认 · ${sourceBadgeText}</span>`;
  }

  function unresolvedMarkup() {
    return `
      <div class="atlas-reward-heading">
        <small>奖励证据</small>
        <span class="atlas-reward-status unresolved">${STATUS_LABELS.unresolved}</span>
      </div>
      <b>奖励尚未确认</b>
      <p>当前没有可复查的点位级奖励证据，旧描述不会被当作已确认事实。</p>
    `;
  }

  function recordMarkup(record) {
    const status = STATUS_LABELS[record.status] || STATUS_LABELS.unresolved;
    const confidence = Math.round(Math.max(0, Math.min(1, Number(record.confidence) || 0)) * 100);
    const rewards = Array.isArray(record.rewards) ? record.rewards : [];
    const sources = Array.isArray(record.sources) ? record.sources : [];
    const conflicts = Array.isArray(record.conflicts) ? record.conflicts : [];
    const openConflicts = conflicts.filter(conflict => conflict.status === 'open');
    const acceptedUncertainty = conflicts.filter(conflict => conflict.status === 'accepted_uncertainty');
    const sourceMarkup = sources.length ? `
      <details class="atlas-reward-evidence">
        <summary>${sources.length} 个可复查来源</summary>
        ${sources.map(source => `
          <div class="atlas-reward-source">
            <b>${escapeHTML(source.title || source.sourceId)}</b>
            <small>${escapeHTML(source.locator)}</small>
            ${source.limitationsZhCN ? `<p>${escapeHTML(source.limitationsZhCN)}</p>` : ''}
          </div>
        `).join('')}
      </details>
    ` : '';
    return `
      <div class="atlas-reward-heading">
        <small>奖励证据</small>
        <span class="atlas-reward-status ${escapeHTML(record.status)}">${escapeHTML(status)}</span>
      </div>
      <b>${escapeHTML(record.summaryZhCN || '奖励尚未确认')}</b>
      ${rewards.length ? `<div class="atlas-reward-list">${rewards.map(reward => `<div>${formatQuantity(reward, sources)}</div>`).join('')}</div>` : ''}
      <div class="atlas-reward-meta"><span>置信度 ${confidence}%</span><span>${sources.length} 个来源</span><span>${openConflicts.length} 个未解决冲突</span><span>${acceptedUncertainty.length} 项已接受不确定性</span></div>
      ${openConflicts.length ? `<p class="atlas-reward-conflict">存在未解决证据冲突，当前摘要不可视为最终结论。</p>` : ''}
      ${record.status === 'high_confidence_inference' ? '<p>来源覆盖可能只支持部分奖励；整条记录仍是高置信推断，不代表官方确认。</p>' : ''}
      ${sourceMarkup}
    `;
  }

  function renderSelectedReward() {
    const detail = document.getElementById('detailContent');
    const highlight = detail?.querySelector('.sheet-highlight');
    if (!highlight) return;
    const locationId = selectedLocationId();
    if (!locationId) return;
    const record = runtime.records.get(locationId);
    highlight.classList.add('atlas-reward-summary');
    highlight.dataset.rewardLocationId = locationId;
    highlight.dataset.rewardState = record?.status || 'unresolved';
    highlight.innerHTML = record ? recordMarkup(record) : unresolvedMarkup();
  }

  function renderCoverage() {
    const progress = document.querySelector('#progressPanel .overall-progress');
    if (!progress || !runtime.coverage) return;
    let card = progress.querySelector('.atlas-reward-coverage');
    if (!card) {
      card = document.createElement('section');
      card.className = 'atlas-reward-coverage';
      progress.append(card);
    }
    const coverage = runtime.coverage;
    const confirmed = Number(coverage.officialConfirmed || 0) + Number(coverage.multiSourceConfirmed || 0);
    card.innerHTML = `
      <header><b>奖励证据覆盖</b><small>仅统计可审查记录</small></header>
      <div class="atlas-reward-coverage-grid">
        <div><b>${confirmed}</b><small>已确认</small></div>
        <div><b>${Number(coverage.highConfidenceInference || 0)}</b><small>高置信推断</small></div>
        <div><b>${Number(coverage.unresolved || 0)}</b><small>尚未解决</small></div>
        <div><b>${Number(coverage.openConflicts || 0)}</b><small>开放冲突</small></div>
        <div><b>${Number(coverage.humanReviewed || 0)}</b><small>人工复核</small></div>
        <div><b>${Number(coverage.locked || 0)}</b><small>锁定记录</small></div>
      </div>
      <p>总计 ${Number(coverage.total || 0)} 个点位；未找到可靠证据的点位不会自动生成奖励。</p>
    `;
  }

  function observeDetails() {
    const detail = document.getElementById('detailContent');
    if (!detail || detail.dataset.rewardObserver === '1') return;
    detail.dataset.rewardObserver = '1';
    new MutationObserver(() => {
      if (!runtime.ready) return;
      const highlight = detail.querySelector('.sheet-highlight');
      const locationId = selectedLocationId();
      if (highlight && locationId && highlight.dataset.rewardLocationId !== locationId) {
        queueMicrotask(renderSelectedReward);
      }
    }).observe(detail, { childList: true, subtree: true });
  }

  async function refresh() {
    if (runtime.loading) return runtime.loading;
    runtime.loading = Promise.all([loadJSON(INDEX_URL), loadJSON(RECORDS_URL)])
      .then(async ([index, recordIndex]) => {
        runtime.coverage = index.coverage || null;
        runtime.records = await loadRuntimeRecords(recordIndex);
        runtime.ready = true;
        renderCoverage();
        renderSelectedReward();
        return runtime;
      })
      .catch(error => {
        console.warn('[Atlas Rewards] 奖励证据数据加载失败', error);
        runtime.ready = true;
        renderSelectedReward();
        return runtime;
      })
      .finally(() => { runtime.loading = null; });
    return runtime.loading;
  }

  window.AtlasRewards = {
    refresh,
    getRecord: locationId => runtime.records.get(String(locationId)) || null,
    getCoverage: () => runtime.coverage
  };

  document.addEventListener('DOMContentLoaded', () => {
    observeDetails();
    refresh();
  }, { once: true });
})();
