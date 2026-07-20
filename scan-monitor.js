(() => {
  'use strict';

  const VERSION = '0.6.1';
  const REPO = 'Justin-160inteva/atlas-web';
  const BRANCH = 'main';
  const RAW = `https://raw.githubusercontent.com/${REPO}/${BRANCH}/`;
  const API = `https://api.github.com/repos/${REPO}/contents/`;
  const RAW_POLL_MS = 5000;
  const API_POLL_MS = 180000;
  const APPLY_TICK_MS = 1000;
  const TIMEOUT_MS = 6000;
  const HEARTBEAT_EXPECTED = 30;
  const HEARTBEAT_WARN = 75;
  const HEARTBEAT_FAIL = 150;
  const SUPERVISOR_STALE = 600;
  const MAX_PROJECT_SECONDS = 20;

  const paths = {
    status: 'data/batch-analysis/eleven-pilot-scan-status.json',
    queue: 'data/batch-analysis/eleven-pilot-scan-queue.json',
    catalog: 'data/eleven-game-world-ac-shadows-catalog.json',
    runtime: 'data/runtime-progress/eleven-pilot-progress.json',
    recovery: 'data/batch-analysis/eleven-pilot-recovery-report.json',
    watchdog: 'data/batch-analysis/eleven-pilot-watchdog-state.json',
    supervisor: 'data/batch-analysis/eleven-heartbeat-supervisor-state.json'
  };

  const state = {
    data: {},
    origin: {},
    previousRuntime: null,
    lastMeasuredRuntime: null,
    lastSync: 0,
    nextRawPoll: 0,
    rawRefreshing: false,
    apiRefreshing: false,
    rawCycles: 0,
    rawTimer: 0,
    apiTimer: 0,
    tickTimer: 0,
    clockTimer: 0
  };

  const $ = id => document.getElementById(id);
  const esc = value => String(value ?? '').replace(/[&<>'"]/g, character => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;'
  })[character]);
  const validRuntime = value => value
    && Number(value.schemaVersion) >= 2
    && typeof value.state === 'string'
    && typeof value.stage === 'string'
    && Number.isFinite(Date.parse(value.updatedAt || ''));
  const ageSeconds = value => {
    const time = Date.parse(value || '');
    return Number.isFinite(time) ? Math.max(0, Math.round((Date.now() - time) / 1000)) : null;
  };
  const ageLabel = value => {
    const seconds = ageSeconds(value);
    if (seconds === null) return '—';
    if (seconds < 5) return '刚刚';
    if (seconds < 60) return `${seconds}秒前`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}分钟前`;
    return `${Math.floor(seconds / 3600)}小时前`;
  };
  const mb = value => Number.isFinite(Number(value)) ? `${(Number(value) / 1048576).toFixed(1)} MB` : '—';
  const speed = value => Number.isFinite(Number(value)) ? `${(Number(value) / 1048576).toFixed(2)} MB/s` : '—';
  const eta = value => {
    const seconds = Math.max(0, Number(value) || 0);
    if (!seconds) return '—';
    if (seconds < 60) return `${Math.ceil(seconds)}秒`;
    if (seconds < 3600) return `${Math.ceil(seconds / 60)}分钟`;
    return `${Math.floor(seconds / 3600)}小时 ${Math.ceil((seconds % 3600) / 60)}分钟`;
  };
  const stateLabel = value => ({
    running: '运行中', queued: '排队中', recovery: '自动恢复', blocked: '需要人工检查',
    failed: '失败', complete: '批次完成', idle: '等待任务'
  })[value] || '等待任务';
  const queueLabel = value => ({
    pending: '等待', queued: '排队', running: '运行中', recovery: '自动恢复',
    failed: '重试等待', imported: '已导入'
  })[value] || value || '等待';
  const timestamp = value => Date.parse(value?.updatedAt || value?.generatedAt || value?.lastFinishedAt || '') || 0;
  const batchKey = value => String(value?.queueId || value?.batchId || value?.pilotRegion || '');

  function withTimeout(promise, milliseconds = TIMEOUT_MS) {
    return Promise.race([
      promise,
      new Promise((_, reject) => setTimeout(() => reject(new Error('timeout')), milliseconds))
    ]);
  }

  async function fetchJson(url) {
    const separator = url.includes('?') ? '&' : '?';
    const response = await withTimeout(fetch(`${url}${separator}t=${Date.now()}`, {
      cache: 'no-store',
      headers: { Accept: 'application/json' }
    }));
    if (!response.ok) throw new Error(String(response.status));
    return response.json();
  }

  function decodeBase64(content) {
    const binary = atob(String(content || '').replace(/\s+/g, ''));
    return new TextDecoder().decode(Uint8Array.from(binary, character => character.charCodeAt(0)));
  }

  async function readRaw(path) {
    for (const [origin, url] of [['GitHub Raw', `${RAW}${path}`], ['站点回退', path]]) {
      try {
        return { data: await fetchJson(url), origin };
      } catch (_) {
      }
    }
    return { data: null, origin: '不可用' };
  }

  async function readApi(path) {
    try {
      const payload = await fetchJson(`${API}${path}?ref=${BRANCH}`);
      return { data: JSON.parse(decodeBase64(payload.content)), origin: 'GitHub Contents API' };
    } catch (_) {
      return { data: null, origin: '不可用' };
    }
  }

  function runtimeNewer(first, second) {
    if (!validRuntime(first)) return second;
    if (!validRuntime(second)) return first;
    const firstTime = Date.parse(first.updatedAt);
    const secondTime = Date.parse(second.updatedAt);
    if (first.externalSourceId !== second.externalSourceId) return firstTime >= secondTime ? first : second;
    const firstHeartbeat = Number(first.heartbeatSequence || 0);
    const secondHeartbeat = Number(second.heartbeatSequence || 0);
    return firstHeartbeat !== secondHeartbeat
      ? (firstHeartbeat > secondHeartbeat ? first : second)
      : (firstTime >= secondTime ? first : second);
  }

  function accept(key, packet) {
    if (!packet?.data) return;
    if (key === 'runtime') {
      const chosen = runtimeNewer(packet.data, state.data.runtime);
      if (chosen === packet.data) {
        state.previousRuntime = state.data.runtime;
        state.data.runtime = packet.data;
        state.origin.runtime = packet.origin;
        if (Number(packet.data.totalBytes || 0) > 0) state.lastMeasuredRuntime = { ...packet.data };
      }
      return;
    }
    if (timestamp(packet.data) >= timestamp(state.data[key])) {
      state.data[key] = packet.data;
      state.origin[key] = packet.origin;
    }
  }

  function taskPercent(runtime) {
    const total = Number(runtime?.totalBytes || 0);
    const downloaded = Number(runtime?.downloadedBytes || 0);
    if (runtime?.stage === 'download' && total > 0) return Math.min(100, downloaded / total * 100);
    return Math.min(100, Math.max(0, Number(runtime?.progressPercent || 0)));
  }

  function completedStatus(status) {
    const total = Number(status?.summary?.total || 0);
    const imported = Number(status?.summary?.imported || 0);
    return Boolean(status?.complete && total > 0 && imported >= total && Array.isArray(status.items));
  }

  function chooseDurableBatch(queue, status, runtime, catalog) {
    const queueItems = Array.isArray(queue?.items) ? queue.items : [];
    const statusItems = Array.isArray(status?.items) ? status.items : [];
    const queueBatch = batchKey(queue);
    const statusBatch = batchKey(status);
    const mismatch = Boolean(queueItems.length && statusItems.length && queueBatch && statusBatch && queueBatch !== statusBatch);
    const runtimeRegion = String(runtime?.pilotRegion || '');
    const runtimeMatchesStatus = Boolean(runtimeRegion && runtimeRegion === String(status?.pilotRegion || ''));
    const runtimeMatchesQueue = Boolean(runtimeRegion && runtimeRegion === String(queue?.pilotRegion || ''));
    const statusTerminal = completedStatus(status);

    let document = queue;
    let source = 'queue';
    let items = queueItems;

    if (statusItems.length && (
      statusTerminal
      || !queueItems.length
      || (mismatch && (runtimeMatchesStatus || runtime?.state === 'complete'))
      || (!runtimeMatchesQueue && timestamp(status) >= timestamp(queue))
    )) {
      document = status;
      source = 'status';
      items = statusItems;
    }

    const catalogItems = new Map((catalog?.items || []).map(item => [item.id || item.externalSourceId, item]));
    const enriched = items.map(item => ({ ...(catalogItems.get(item.externalSourceId) || {}), ...item }));

    return {
      document,
      source,
      items: enriched,
      region: document?.pilotRegion || status?.pilotRegion || queue?.pilotRegion || '当前批次',
      batchId: batchKey(document),
      mismatch,
      ignoredSource: mismatch ? (source === 'status' ? 'queue' : 'status') : null,
      complete: source === 'status'
        ? statusTerminal
        : Boolean(queue?.status === 'complete' || (enriched.length && enriched.every(item => item.state === 'imported')))
    };
  }

  function runtimeContext(items, runtime) {
    const durable = validRuntime(runtime)
      ? items.find(item => item.externalSourceId === runtime.externalSourceId)
      : null;
    const actionable = Boolean(validRuntime(runtime)
      && durable
      && durable.state !== 'imported'
      && ['running', 'recovery', 'failed'].includes(runtime.state));
    return {
      durable,
      actionable,
      runtime: actionable ? runtime : null,
      terminal: Boolean(validRuntime(runtime) && durable?.state === 'imported')
    };
  }

  function relevantRecovery(recovery, items) {
    if (!recovery?.activeExternalSourceId) return recovery || null;
    const item = items.find(entry => entry.externalSourceId === recovery.activeExternalSourceId);
    if (!item || item.state === 'imported') return null;
    return recovery;
  }

  function deriveSnapshot() {
    const status = state.data.status || {};
    const queue = state.data.queue || {};
    const runtime = state.data.runtime;
    const catalog = state.data.catalog || {};
    const authority = chooseDurableBatch(queue, status, runtime, catalog);
    const items = authority.items;
    const context = runtimeContext(items, runtime);
    const recovery = relevantRecovery(state.data.recovery, items);

    if (context.actionable) {
      const item = items.find(entry => entry.externalSourceId === runtime.externalSourceId);
      if (item) {
        item.state = runtime.state === 'recovery' ? 'recovery' : runtime.state;
        item.livePercent = taskPercent(runtime);
        item.heartbeatSequence = runtime.heartbeatSequence;
      }
    }

    const imported = items.filter(item => item.state === 'imported').length;
    const total = items.length || Number(status?.summary?.total || 0);
    const pending = items.find(item => ['pending', 'queued', 'failed'].includes(item.state));
    const current = context.actionable
      ? items.find(item => item.externalSourceId === runtime.externalSourceId)
      : items.find(item => ['running', 'recovery'].includes(item.state)) || pending || null;

    let mode = 'idle';
    if (authority.complete || (items.length && imported === items.length)) mode = 'complete';
    else if (recovery?.requiresHumanReview || items.some(item => item.state === 'blocked')) mode = 'blocked';
    else if (context.actionable && ['recovery', 'failed'].includes(runtime.state)) mode = 'recovery';
    else if (context.actionable && runtime.state === 'running') mode = 'running';
    else if (pending) mode = 'queued';

    const percent = context.actionable ? taskPercent(runtime) : 0;
    const batchPercent = total
      ? Math.min(100, (imported + (['running', 'recovery'].includes(mode) ? percent / 100 : 0)) / total * 100)
      : 0;
    const heartbeatAt = context.actionable ? runtime.updatedAt : authority.document?.updatedAt || status.updatedAt || queue.updatedAt;

    return {
      status,
      queue,
      runtime,
      recovery,
      authority,
      items,
      context,
      current,
      mode,
      imported,
      total,
      percent,
      batchPercent,
      heartbeatAt,
      pending
    };
  }

  function renderQueue(snapshot, region) {
    $('queueSummary').textContent = `${snapshot.items.length} 个任务`;
    $('queueList').innerHTML = snapshot.items.length
      ? snapshot.items.map(item => {
        const title = item.partTitle || item.title || `第${item.sequence || item.page || '—'}期`;
        const detail = [
          item.regionGuess || region,
          item.durationSeconds ? `${Math.round(item.durationSeconds / 60)}分钟` : null,
          item.attemptCount ? `尝试 ${item.attemptCount}` : null,
          item.livePercent != null ? `本期 ${item.livePercent.toFixed(1)}%` : null,
          item.heartbeatSequence ? `心跳 #${item.heartbeatSequence}` : null,
          item.lastFinishedAt ? `完成于 ${ageLabel(item.lastFinishedAt)}` : null
        ].filter(Boolean).join(' · ');
        return `<article class="queue-item"><span class="queue-page">P${esc(item.page || item.sequence || '—')}</span><span class="queue-copy"><b>${esc(title)}</b><small>${esc(detail)}</small></span><span class="queue-state ${esc(item.state)}">${esc(queueLabel(item.state))}</span></article>`;
      }).join('')
      : '<div class="empty">队列为空。</div>';
  }

  function renderStages(snapshot) {
    const order = ['queued', 'download', 'remux', 'analysis', 'index', 'cleanup', 'persist'];
    const labels = {
      queued: '任务排队', download: '临时下载', remux: '媒体转封装', analysis: '抽帧与数值分析',
      index: '写入分析索引', cleanup: '删除临时媒体', persist: '持久化状态'
    };
    const alias = {
      queued: 'queued', download: 'download', downloading: 'download', remuxing: 'remux',
      transcoding: 'remux', analysis: 'analysis', 'frame-analysis': 'analysis', analyzing: 'analysis',
      indexing: 'index', cleanup: 'cleanup', persisting: 'persist', complete: 'persist', recovery: 'download'
    };
    const active = snapshot.mode === 'complete'
      ? 'persist'
      : snapshot.context.actionable ? (alias[String(snapshot.runtime?.stage)] || 'queued') : 'queued';
    const activeIndex = order.indexOf(active);
    $('stageList').innerHTML = order.map((key, index) => `<div class="stage ${snapshot.mode === 'complete' || index < activeIndex ? 'done' : index === activeIndex ? 'active' : ''}"><i></i><span>${labels[key]}</span></div>`).join('');
  }

  function renderTelemetry(snapshot) {
    const live = snapshot.context.actionable && snapshot.runtime?.stage === 'download';
    const telemetry = (Number(snapshot.runtime?.totalBytes || 0) > 0 ? snapshot.runtime : null) || state.lastMeasuredRuntime;
    $('downloadTelemetry').dataset.active = live ? 'true' : 'false';

    if (!validRuntime(telemetry) || Number(telemetry.totalBytes || 0) <= 0) {
      $('downloadedAmount').textContent = '—';
      $('downloadSpeed').textContent = '—';
      $('downloadSegment').textContent = '—';
      $('downloadEta').textContent = '—';
      $('downloadBar').style.width = '0%';
      $('segmentBar').style.width = '0%';
      $('downloadHeartbeatMeta').textContent = snapshot.mode === 'complete' ? '批次已完成' : '等待首个下载实测';
      $('downloadDetail').textContent = snapshot.mode === 'complete' ? '当前没有活动下载；全部结果已持久化。' : '当前没有可用下载遥测';
      return;
    }

    const total = Number(telemetry.totalBytes || 0);
    const actual = Number(telemetry.downloadedBytes || 0);
    const rate = Math.max(0, Number(telemetry.speedBytesPerSecond || telemetry.averageSpeedBytesPerSecond || 0));
    const measuredAt = telemetry.telemetryMeasuredAt || telemetry.updatedAt;
    const elapsed = Math.min(MAX_PROJECT_SECONDS, Math.max(0, (Date.now() - Date.parse(measuredAt || 0)) / 1000));
    const estimated = live && elapsed > 1 && elapsed < MAX_PROJECT_SECONDS && rate > 0;
    const shown = Math.min(total, actual + (estimated ? rate * elapsed : 0));
    const segmentTotal = Number(telemetry.segmentTotalBytes || 0);
    const segmentActual = Number(telemetry.segmentDownloadedBytes || 0);
    const shownSegment = Math.min(segmentTotal, segmentActual + Math.max(0, shown - actual));
    const ratio = total ? shown / total * 100 : 0;
    const segmentRatio = segmentTotal ? shownSegment / segmentTotal * 100 : 0;

    $('downloadedAmount').textContent = `${estimated ? '≈ ' : ''}${mb(shown)} / ${mb(total)}`;
    $('downloadSpeed').textContent = `${speed(telemetry.speedBytesPerSecond)} · 平均 ${speed(telemetry.averageSpeedBytesPerSecond)}`;
    $('downloadSegment').textContent = telemetry.segmentCount ? `${telemetry.segmentIndex || 0} / ${telemetry.segmentCount}` : '—';
    $('downloadEta').textContent = live ? eta((total - shown) / Math.max(1, rate)) : '—';
    $('downloadBar').style.width = `${Math.min(100, ratio)}%`;
    $('segmentBar').style.width = `${Math.min(100, segmentRatio)}%`;
    $('downloadHeartbeatMeta').textContent = live
      ? `实测心跳 #${telemetry.heartbeatSequence || '—'} · ${ageLabel(measuredAt)}`
      : `上一任务最终实测 · ${ageLabel(measuredAt)}`;
    $('downloadDetail').textContent = live
      ? `${estimated ? '短期实时估算' : '最近实测'} · 已下载 ${mb(actual)} · 总进度 ${ratio.toFixed(1)}%`
      : `下载遥测已封存，不再作为当前任务心跳；当前状态：${stateLabel(snapshot.mode)}`;
  }

  function renderRecovery(snapshot) {
    const recovery = snapshot.recovery;
    if (!recovery) {
      $('recoveryCategory').textContent = '未触发';
      $('recoveryPanel').innerHTML = '<div class="empty">当前没有活动恢复事件；已完成任务的旧错误不会继续阻塞队列。</div>';
      return;
    }
    $('recoveryCategory').textContent = recovery.dictionaryEntryId || recovery.category || 'unknown';
    $('recoveryPanel').innerHTML = `<div class="event"><b>${esc(recovery.action || 'none')}</b><small>${recovery.retryScheduled ? '已安排安全重试' : '未安排重试'} · ${recovery.requiresHumanReview ? '需要人工检查' : '无需人工介入'}</small><small>${esc(recovery.diagnosis || '')}</small></div>`;
  }

  function renderEvents(snapshot) {
    const events = [];
    const supervisor = state.data.supervisor;
    const watchdog = state.data.watchdog;
    if (snapshot.context.actionable) events.push({
      title: `P${snapshot.runtime.page || '—'}：${stateLabel(snapshot.runtime.state)}`,
      detail: `${snapshot.runtime.message || snapshot.runtime.stage} · ${ageLabel(snapshot.runtime.updatedAt)}`
    });
    if (snapshot.authority.mismatch) events.push({
      title: '批次冲突已自动隔离',
      detail: `采用${snapshot.authority.source === 'status' ? '完成状态' : '当前队列'}；忽略不同批次的旧${snapshot.authority.ignoredSource === 'queue' ? '队列' : '状态'}。`
    });
    if (supervisor?.decision) events.push({
      title: `心跳监督：${supervisor.decision}`,
      detail: `${supervisor.repair || 'none'} · ${ageLabel(supervisor.generatedAt)}`
    });
    if (snapshot.recovery?.action && snapshot.recovery.action !== 'none') events.push({
      title: `自动恢复：${snapshot.recovery.action}`,
      detail: `${snapshot.recovery.dictionaryEntryId || snapshot.recovery.category || 'unknown'} · ${ageLabel(snapshot.recovery.generatedAt)}`
    });
    if (watchdog?.decision && watchdog.decision !== 'no_action') events.push({
      title: `看门狗：${watchdog.decision}`,
      detail: `${watchdog.reason || ''} · ${ageLabel(watchdog.generatedAt)}`
    });
    for (const event of [...(snapshot.status.events || [])].reverse().slice(0, 3)) events.push({
      title: event.completed ? '扫描已完成' : '扫描事件',
      detail: `P${event.page || event.sequence || '—'} · ${event.analysisStatus || event.error || '状态更新'} · ${ageLabel(event.finishedAt || event.startedAt)}`
    });
    $('eventList').innerHTML = events.length
      ? events.slice(0, 5).map(event => `<div class="event"><b>${esc(event.title)}</b><small>${esc(event.detail)}</small></div>`).join('')
      : '<div class="empty">等待扫描事件。</div>';
  }

  function render() {
    const snapshot = deriveSnapshot();
    const catalog = state.data.catalog || {};
    const region = snapshot.authority.region;
    const catalogTotal = Number(catalog?.catalogStatus?.matchedScanItems || catalog?.items?.length || 80);
    const catalogImported = Math.max(
      Number(catalog?.catalogStatus?.analysisImported || 0),
      Array.isArray(catalog?.items) ? catalog.items.filter(item => item.analysisStatus === 'imported').length : 0,
      3 + snapshot.imported
    );

    $('statusBadge').dataset.state = snapshot.mode;
    $('statusBadge').querySelector('b').textContent = stateLabel(snapshot.mode);
    $('heroPercent').textContent = `${Math.round(snapshot.batchPercent)}%`;
    $('heroBar').style.width = `${snapshot.batchPercent}%`;
    $('pilotProgress').textContent = `${snapshot.imported} / ${snapshot.total}`;
    $('catalogProgress').textContent = `${catalogImported} / ${catalogTotal}`;
    $('attemptCount').textContent = `${Number(snapshot.current?.attemptCount || snapshot.recovery?.attemptCount || 0)} / ${Number(snapshot.recovery?.maxAttempts || 3)}`;
    $('activeTitle').textContent = snapshot.current
      ? `P${snapshot.current.page || snapshot.current.sequence || '—'} · ${snapshot.current.partTitle || snapshot.current.title || '当前任务'}`
      : snapshot.mode === 'complete' ? `${region}已完成` : '当前没有活动任务';
    $('activeDetail').textContent = snapshot.context.actionable
      ? `本期 ${snapshot.percent.toFixed(1)}% · ${snapshot.runtime.message || snapshot.runtime.stage}`
      : snapshot.mode === 'queued'
        ? (snapshot.pending ? `上一任务已持久化；P${snapshot.pending.page || snapshot.pending.sequence} 正在等待自动调度。` : '任务已排队。')
        : snapshot.mode === 'complete' ? '全部任务已持久化完成。' : '等待新的任务事件。';
    $('heartbeatAge').textContent = ageLabel(snapshot.heartbeatAt);

    const heartbeatAge = snapshot.context.actionable ? ageSeconds(snapshot.runtime.updatedAt) : null;
    const supervisor = state.data.supervisor;
    const supervisorAge = ageSeconds(supervisor?.generatedAt);
    const notice = $('freshnessNotice');

    if (snapshot.authority.mismatch) {
      notice.dataset.level = snapshot.mode === 'complete' ? 'live' : 'warn';
      notice.textContent = `检测到不同批次文件冲突：已采用${snapshot.authority.source === 'status' ? '10项完成状态' : '当前活动队列'}，旧${snapshot.authority.ignoredSource === 'queue' ? '队列' : '状态'}不会覆盖真实导入结果。`;
    } else if (snapshot.mode === 'complete') {
      notice.dataset.level = 'live';
      notice.textContent = `当前批次已完成；持久状态更新于${ageLabel(snapshot.heartbeatAt)}。`;
    } else if (snapshot.context.actionable && heartbeatAge !== null && heartbeatAge <= HEARTBEAT_WARN) {
      notice.dataset.level = 'live';
      notice.textContent = `${HEARTBEAT_EXPECTED}秒心跳链路正常；当前实测心跳${ageLabel(snapshot.runtime.updatedAt)}。`;
    } else if (snapshot.context.actionable && heartbeatAge > HEARTBEAT_FAIL) {
      notice.dataset.level = 'danger';
      notice.textContent = `当前运行心跳已中断 ${heartbeatAge} 秒；监督器${supervisorAge !== null && supervisorAge <= SUPERVISOR_STALE ? `已报告 ${supervisor.decision}` : '状态也已过期，发布门禁将阻止继续假运行'}。`;
    } else if (snapshot.mode === 'queued') {
      notice.dataset.level = supervisorAge !== null && supervisorAge <= SUPERVISOR_STALE ? 'live' : 'warn';
      notice.textContent = `持久状态优先：上一任务已完成，${snapshot.pending ? `P${snapshot.pending.page || snapshot.pending.sequence} 等待调度` : '队列等待调度'}；${supervisorAge !== null && supervisorAge <= SUPERVISOR_STALE ? `监督器 ${supervisor.decision}，${ageLabel(supervisor.generatedAt)}` : '监督器报告超过10分钟未更新'}。`;
    } else {
      notice.dataset.level = 'info';
      notice.textContent = '页面已连接；正在等待新的持久任务状态。';
    }

    renderQueue(snapshot, region);
    renderStages(snapshot);
    renderTelemetry(snapshot);
    renderRecovery(snapshot);
    renderEvents(snapshot);

    const selectedOrigin = snapshot.authority.source === 'status' ? state.origin.status : state.origin.queue;
    $('dataOrigin').textContent = snapshot.context.actionable
      ? `数据源：${state.origin.runtime || '实时源'} · 心跳 #${snapshot.runtime.heartbeatSequence || '—'}`
      : `权威批次：${snapshot.authority.source === 'status' ? '完成状态' : '当前队列'} · ${selectedOrigin || '混合权威源'}${snapshot.authority.mismatch ? ' · 已隔离旧批次' : ''}${supervisor?.decision ? ` · 监督 ${supervisor.decision}` : ''}`;
  }

  function updateClocks() {
    if (state.lastSync) $('lastSync').textContent = `页面同步 ${ageLabel(new Date(state.lastSync).toISOString())}`;
    const remaining = Math.max(0, Math.ceil((state.nextRawPoll - Date.now()) / 1000));
    $('nextPoll').textContent = state.rawRefreshing || state.apiRefreshing
      ? '正在核对实时与权威状态'
      : `下次实时核对 ${remaining}秒`;
  }

  async function pollRaw(manual = false) {
    if (state.rawRefreshing) return;
    state.rawRefreshing = true;
    if (manual || !state.lastSync) {
      $('syncState').textContent = '同步中';
      $('syncState').dataset.state = 'syncing';
    }
    updateClocks();
    try {
      const coreKeys = ['status', 'queue', 'runtime', 'supervisor'];
      const core = await Promise.all(coreKeys.map(key => readRaw(paths[key])));
      coreKeys.forEach((key, index) => accept(key, core[index]));
      state.rawCycles += 1;
      if (manual || state.rawCycles % 3 === 1) {
        const extraKeys = ['catalog', 'recovery', 'watchdog'];
        const extra = await Promise.all(extraKeys.map(key => readRaw(paths[key])));
        extraKeys.forEach((key, index) => accept(key, extra[index]));
      }
      state.lastSync = Date.now();
      $('syncState').textContent = '已连接';
      $('syncState').dataset.state = 'connected';
      render();
    } catch (error) {
      $('syncState').textContent = '连接异常';
      $('syncState').dataset.state = 'failed';
      $('freshnessNotice').dataset.level = 'danger';
      $('freshnessNotice').textContent = `实时状态读取失败：${error.message || error}。5秒后自动重试。`;
    } finally {
      state.rawRefreshing = false;
      state.nextRawPoll = Date.now() + RAW_POLL_MS;
      updateClocks();
    }
  }

  async function pollApi() {
    if (state.apiRefreshing) return;
    state.apiRefreshing = true;
    updateClocks();
    try {
      const keys = ['status', 'queue', 'runtime'];
      const packets = await Promise.all(keys.map(key => readApi(paths[key])));
      keys.forEach((key, index) => accept(key, packets[index]));
      state.lastSync = Date.now();
      render();
    } finally {
      state.apiRefreshing = false;
      updateClocks();
    }
  }

  function forceRefresh() {
    pollRaw(true);
    pollApi();
  }

  function start() {
    clearInterval(state.rawTimer);
    clearInterval(state.apiTimer);
    clearInterval(state.tickTimer);
    clearInterval(state.clockTimer);
    state.nextRawPoll = Date.now();
    pollRaw(true);
    pollApi();
    state.rawTimer = setInterval(pollRaw, RAW_POLL_MS);
    state.apiTimer = setInterval(pollApi, API_POLL_MS);
    state.tickTimer = setInterval(render, APPLY_TICK_MS);
    state.clockTimer = setInterval(updateClocks, 1000);
  }

  $('forceRefresh')?.addEventListener('click', forceRefresh);
  document.addEventListener('visibilitychange', () => { if (!document.hidden) forceRefresh(); });
  addEventListener('online', forceRefresh);
  addEventListener('message', event => { if (event.data?.type === 'atlas-monitor-refresh') forceRefresh(); });
  addEventListener('pagehide', () => {
    clearInterval(state.rawTimer);
    clearInterval(state.apiTimer);
    clearInterval(state.tickTimer);
    clearInterval(state.clockTimer);
  }, { once: true });

  window.AtlasScanMonitor = {
    refresh: forceRefresh,
    version: VERSION,
    snapshot: deriveSnapshot,
    chooseDurableBatch
  };

  start();
})();
