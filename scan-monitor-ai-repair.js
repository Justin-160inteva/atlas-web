(() => {
  'use strict';

  const VERSION = '0.1.1';
  const POLL_MS = 5000;
  const paths = {
    report: 'data/batch-analysis/scan-autonomous-repair-report.json',
    recovery: 'data/batch-analysis/eleven-pilot-recovery-report.json',
    queue: 'data/batch-analysis/eleven-pilot-scan-queue.json',
    runtime: 'data/runtime-progress/eleven-pilot-progress.json'
  };
  let timer = 0;
  let activeRefresh = null;
  let forceQueued = false;

  const $ = id => document.getElementById(id);
  const age = value => {
    const time = Date.parse(value || '');
    if (!Number.isFinite(time)) return '—';
    const seconds = Math.max(0, Math.round((Date.now() - time) / 1000));
    if (seconds < 5) return '刚刚';
    if (seconds < 60) return `${seconds}秒前`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
    return `${Math.floor(seconds / 3600)}小时前`;
  };

  async function read(path) {
    const response = await fetch(`${path}?t=${Date.now()}`, {
      cache: 'no-store',
      headers: {
        Accept: 'application/json',
        'Cache-Control': 'no-cache, no-store, max-age=0',
        Pragma: 'no-cache'
      }
    });
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function targetItem(queue, report, recovery) {
    const id = report?.targetExternalSourceId
      || recovery?.automaticAiRepair?.targetExternalSourceId
      || recovery?.activeExternalSourceId;
    return (queue?.items || []).find(item => item.externalSourceId === id)
      || (queue?.items || []).find(item => item.autonomousRepairPasses || item.lastAutonomousRepairAt)
      || null;
  }

  function derive(queue, report, recovery, runtime) {
    const item = targetItem(queue, report, recovery);
    const runtimeMatches = Boolean(item && runtime?.externalSourceId === item.externalSourceId);
    const humanReview = Boolean(recovery?.requiresHumanReview)
      && report?.outcome !== 'repaired'
      && item?.state !== 'pending'
      && item?.state !== 'running'
      && item?.state !== 'recovery';

    let state = 'idle';
    let label = '等待异常';
    let progress = 0;
    let headline = '当前没有自动修复任务';
    let detail = '检测到可安全修复的扫描异常后，将自动进入此栏，不再默认停在人工检查。';

    if (item?.state === 'imported') {
      state = 'complete';
      label = '修复完成';
      progress = 100;
      headline = `P${item.page || item.sequence} 已修复并成功导入`;
      detail = '修复后的任务已通过分析与持久化，队列将继续处理下一期。';
    } else if (runtimeMatches && ['running', 'recovery'].includes(runtime?.state)) {
      state = runtime.state === 'running' ? 'running' : 'repairing';
      label = runtime.state === 'running' ? '自动重试中' : 'AI 修复执行中';
      progress = runtime.state === 'running'
        ? Math.max(58, Math.min(96, Number(runtime.progressPercent || 0)))
        : 68;
      headline = `P${item.page || item.sequence} 正在自动重试`;
      detail = runtime.message || '修复已通过安全门禁，正在重新执行当前授权任务。';
    } else if (report?.outcome === 'investigating') {
      state = 'repairing';
      label = 'AI 正在分析';
      progress = 35;
      headline = `P${item?.page || report?.targetPage || '—'} 正在生成安全修复`;
      detail = '模型仅接收脱敏、压缩后的相关函数片段；授权范围、队列顺序和媒体保留策略不可修改。';
    } else if (report?.outcome === 'repaired' && item) {
      state = 'queued';
      label = '已修复，等待重试';
      progress = Math.max(55, Number(report.progressPercent || 55));
      headline = `P${item.page || item.sequence} 已进入自动 AI 修复队列`;
      detail = report.summary || recovery?.diagnosis || '修复已应用并等待严格串行调度。';
    } else if (report?.outcome === 'repair_failed' && !humanReview) {
      state = 'repairing';
      label = '切换确定性修复';
      progress = 22;
      headline = `P${item?.page || report?.targetPage || '—'} 正在自动降级处理`;
      detail = 'AI 模型调用未完成，但系统会继续使用错误词典和确定性修复，不会直接要求人工检查。';
    } else if (humanReview) {
      state = 'blocked';
      label = '安全边界阻止自动修改';
      progress = 0;
      headline = `P${item?.page || '—'} 仅因授权或身份安全问题暂停`;
      detail = recovery?.diagnosis || '只有授权、身份或隐私边界异常才允许进入人工检查。';
    }

    return { item, state, label, progress, headline, detail, humanReview };
  }

  function render(data, report, recovery) {
    const card = $('aiRepairCard');
    if (!card) return;
    card.dataset.state = data.state;
    $('aiRepairBadge').textContent = data.label;
    $('aiRepairHeadline').textContent = data.headline;
    $('aiRepairTarget').textContent = data.item
      ? `P${data.item.page || data.item.sequence} · 第 ${Number(data.item.autonomousRepairPasses || 1)} 次自动修复`
      : '尚无目标';
    $('aiRepairBar').style.width = `${Math.max(0, Math.min(100, data.progress))}%`;
    $('aiRepairPercent').textContent = `${Math.round(data.progress)}%`;
    $('aiRepairAction').textContent = recovery?.action || report?.nextAction || '等待异常';
    $('aiRepairFiles').textContent = Array.isArray(report?.changedFiles) ? `${report.changedFiles.length} 个文件` : '0 个文件';
    $('aiRepairUpdated').textContent = age(report?.generatedAt || recovery?.generatedAt);
    $('aiRepairDetail').textContent = data.detail;

    if (!data.humanReview) {
      const badge = $('statusBadge');
      if (badge?.dataset.state === 'blocked') {
        badge.dataset.state = data.state === 'running' ? 'running' : 'recovery';
        const text = badge.querySelector('b');
        if (text) text.textContent = data.state === 'running' ? '自动重试中' : '自动 AI 修复';
      }
    }
  }

  async function executeRefresh() {
    try {
      const [report, recovery, queue, runtime] = await Promise.all([
        read(paths.report), read(paths.recovery), read(paths.queue), read(paths.runtime)
      ]);
      render(derive(queue, report, recovery, runtime), report, recovery);
    } catch (error) {
      const card = $('aiRepairCard');
      if (card) {
        card.dataset.state = 'idle';
        $('aiRepairBadge').textContent = '状态读取重试中';
        $('aiRepairDetail').textContent = `自动 AI 修复状态暂时读取失败：${error.message || error}。5秒后重试。`;
      }
    }
  }

  function refresh(options = {}) {
    const force = options === true || options?.force === true;
    if (activeRefresh) {
      if (force) forceQueued = true;
      return activeRefresh;
    }
    activeRefresh = executeRefresh().finally(() => {
      activeRefresh = null;
      if (forceQueued) {
        forceQueued = false;
        refresh({ force: true });
      }
    });
    return activeRefresh;
  }

  function start() {
    clearInterval(timer);
    refresh({ force: true });
    timer = window.setInterval(refresh, POLL_MS);
    document.addEventListener('visibilitychange', () => { if (!document.hidden) refresh({ force: true }); });
    window.addEventListener('online', () => refresh({ force: true }), { passive: true });
    window.addEventListener('atlas-authoritative-refresh', () => refresh({ force: true }));
    window.AtlasScanAiRepair = { version: VERSION, refresh };
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start, { once: true });
  else start();
})();
