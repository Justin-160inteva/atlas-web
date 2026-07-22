(() => {
  'use strict';

  const CATALOG_URL = 'data/rewards/reward-summary-catalog.json';
  const STATUS_LABELS = Object.freeze({
    official_confirmed: '官方确认',
    multi_source_confirmed: '多来源确认',
    high_confidence_inference: '高置信推断',
    unresolved: '尚未解决'
  });

  let catalog = null;
  let loading = null;
  let lastLocationId = null;

  const escapeHtml = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);

  async function loadCatalog(force = false) {
    if (catalog && !force) return catalog;
    if (loading && !force) return loading;
    loading = fetch(`${CATALOG_URL}?t=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' }
    }).then(response => {
      if (!response.ok) throw new Error(String(response.status));
      return response.json();
    }).then(payload => {
      if (Number(payload?.recordCount) !== 3430 || !payload?.records) {
        throw new Error('invalid reward catalog');
      }
      catalog = payload;
      return payload;
    }).catch(() => catalog).finally(() => {
      loading = null;
    });
    return loading;
  }

  function selectedLocationId() {
    try {
      return typeof state !== 'undefined' ? state?.selected?.id || null : null;
    } catch (_) {
      return null;
    }
  }

  function applyRecord(locationId = selectedLocationId()) {
    if (!locationId || !catalog?.records) return false;
    const record = catalog.records[locationId];
    const content = document.getElementById('detailContent');
    if (!record || !content) return false;

    let block = content.querySelector('.sheet-highlight');
    if (!block) {
      block = document.createElement('div');
      block.className = 'sheet-highlight';
      const actions = content.querySelector('.sheet-actions');
      if (actions?.nextSibling) content.insertBefore(block, actions.nextSibling);
      else content.appendChild(block);
    }

    const status = STATUS_LABELS[record.status] || '尚未解决';
    const confidence = Math.round(Math.max(0, Math.min(1, Number(record.confidence) || 0)) * 100);
    const sourceCount = Array.isArray(record.sources) ? record.sources.length : 0;
    const conflictCount = Array.isArray(record.conflicts)
      ? record.conflicts.filter(conflict => conflict?.status === 'open').length
      : 0;
    const reviewState = record.review?.state === 'locked'
      ? '已锁定'
      : record.review?.state === 'human_reviewed' ? '人工复核' : '机器校验';
    const signature = [
      locationId,
      record.status,
      confidence,
      sourceCount,
      conflictCount,
      reviewState,
      record.summaryZhCN || '奖励尚未确认'
    ].join('\u001f');

    if (block.dataset.rewardSignature === signature) {
      lastLocationId = locationId;
      return true;
    }

    block.classList.add('atlas-reward-evidence');
    block.dataset.status = record.status || 'unresolved';
    block.dataset.locationId = locationId;
    block.dataset.rewardSignature = signature;
    block.innerHTML = `
      <small><i aria-hidden="true"></i><span>奖励摘要</span><span>·</span><span>${escapeHtml(status)}</span></small>
      <b>${escapeHtml(record.summaryZhCN || '奖励尚未确认')}</b>
      <div class="reward-evidence-meta">
        <span>置信度 ${confidence}%</span>
        <span>证据 ${sourceCount} 条</span>
        <span>${escapeHtml(reviewState)}</span>
        ${conflictCount ? `<span>待解决冲突 ${conflictCount} 条</span>` : ''}
      </div>`;

    lastLocationId = locationId;
    return true;
  }

  async function refreshCurrent(force = false) {
    await loadCatalog(force);
    applyRecord();
  }

  function installObserver() {
    const content = document.getElementById('detailContent');
    if (!content) return;
    let queued = false;
    const observer = new MutationObserver(() => {
      if (queued) return;
      const locationId = selectedLocationId();
      if (!locationId) return;
      queued = true;
      queueMicrotask(() => {
        queued = false;
        applyRecord(locationId);
      });
    });
    observer.observe(content, { childList: true, subtree: true });

    document.addEventListener('visibilitychange', () => {
      if (!document.hidden) refreshCurrent(false);
    }, { passive: true });
    window.addEventListener('online', () => refreshCurrent(true), { passive: true });
    window.setInterval(() => loadCatalog(true).then(() => {
      const current = selectedLocationId();
      if (current && current === lastLocationId) applyRecord(current);
    }), 15 * 60 * 1000);
  }

  function start() {
    installObserver();
    refreshCurrent(false);
    document.documentElement.dataset.atlasRewardSummary = '0.9.4.8-reward-summary-2';
  }

  window.AtlasRewardSummary = Object.freeze({
    version: '0.9.4.8-reward-summary-2',
    refresh: () => refreshCurrent(true),
    current: () => {
      const locationId = selectedLocationId();
      return locationId ? catalog?.records?.[locationId] || null : null;
    },
    coverage: () => catalog?.coverage || null
  });

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', start, { once: true });
  } else {
    start();
  }
})();
