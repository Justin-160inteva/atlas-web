(() => {
  'use strict';

  const VERSION = '0.1.1';
  const REPO = 'Justin-160inteva/atlas-web';
  const BRANCH = 'main';
  const API_ROOT = `https://api.github.com/repos/${REPO}`;
  const RAW_ROOT = `https://raw.githubusercontent.com/${REPO}`;
  const MANUAL_WINDOW_MS = 14000;
  const nativeFetch = window.fetch.bind(window);

  const livePaths = new Set([
    'data/batch-analysis/eleven-pilot-scan-status.json',
    'data/batch-analysis/eleven-pilot-scan-queue.json',
    'data/eleven-game-world-ac-shadows-catalog.json',
    'data/runtime-progress/eleven-pilot-progress.json',
    'data/batch-analysis/eleven-pilot-recovery-report.json',
    'data/batch-analysis/scan-autonomous-repair-report.json',
    'data/batch-analysis/eleven-pilot-watchdog-state.json',
    'data/batch-analysis/eleven-heartbeat-supervisor-state.json',
    'data/batch-analysis/scan-system-health.json',
    'data/analysis-index.json'
  ]);

  let generation = 0;
  let manualUntil = 0;
  let headPromise = null;
  let pinnedSha = null;
  let packetCache = new Map();
  let refreshChain = Promise.resolve();

  const delay = milliseconds => new Promise(resolve => setTimeout(resolve, milliseconds));

  function requestUrl(input) {
    try {
      return new URL(typeof input === 'string' ? input : input.url, location.href);
    } catch (_) {
      return null;
    }
  }

  function pathFromRequest(url) {
    if (!url) return null;
    const pathname = decodeURIComponent(url.pathname);
    const contentsPrefix = `/repos/${REPO}/contents/`;
    if (url.hostname === 'api.github.com' && pathname.startsWith(contentsPrefix)) {
      return pathname.slice(contentsPrefix.length).replace(/^\/+/, '');
    }
    if (url.hostname === 'raw.githubusercontent.com') {
      const prefix = `/${REPO}/`;
      if (!pathname.startsWith(prefix)) return null;
      const rest = pathname.slice(prefix.length);
      const slash = rest.indexOf('/');
      return slash >= 0 ? rest.slice(slash + 1) : null;
    }
    if (url.origin === location.origin) return pathname.replace(/^\/+/, '');
    return null;
  }

  function isContentsRequest(url) {
    return Boolean(url && url.hostname === 'api.github.com' && url.pathname.includes(`/repos/${REPO}/contents/`));
  }

  function safeHeaders(headers, accept = 'application/json') {
    const result = new Headers(headers || {});
    if (!result.has('Accept')) result.set('Accept', accept);
    return result;
  }

  function utf8ToBase64(text) {
    const bytes = new TextEncoder().encode(text);
    let binary = '';
    const chunkSize = 0x8000;
    for (let index = 0; index < bytes.length; index += chunkSize) {
      binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
    }
    return btoa(binary);
  }

  async function resolveLatestHead(currentGeneration) {
    const response = await nativeFetch(`${API_ROOT}/commits/${BRANCH}?atlas_refresh=${Date.now()}-${currentGeneration}`, {
      cache: 'no-store',
      headers: safeHeaders({ Accept: 'application/vnd.github+json' })
    });
    if (!response.ok) throw new Error(`HEAD ${response.status}`);
    const payload = await response.json();
    if (!/^[0-9a-f]{40}$/i.test(String(payload.sha || ''))) throw new Error('invalid HEAD sha');
    return payload.sha;
  }

  function beginAuthoritativeWindow() {
    generation += 1;
    const currentGeneration = generation;
    manualUntil = Date.now() + MANUAL_WINDOW_MS;
    pinnedSha = null;
    packetCache = new Map();
    headPromise = resolveLatestHead(currentGeneration)
      .then(sha => {
        if (currentGeneration === generation) pinnedSha = sha;
        return sha;
      })
      .catch(() => null);
    return headPromise;
  }

  async function pinnedText(path, sha) {
    const key = `${generation}:${sha}:${path}`;
    if (!packetCache.has(key)) {
      packetCache.set(key, nativeFetch(`${RAW_ROOT}/${sha}/${path}?atlas_refresh=${generation}-${Date.now()}`, {
        cache: 'no-store',
        headers: safeHeaders({ Accept: 'application/json' })
      }).then(async response => {
        if (!response.ok) throw new Error(`${path} ${response.status}`);
        return response.text();
      }));
    }
    return packetCache.get(key);
  }

  window.fetch = async function atlasFreshFetch(input, init = {}) {
    const url = requestUrl(input);
    const path = pathFromRequest(url);
    const isLive = Boolean(path && livePaths.has(path));
    const manual = isLive && headPromise && Date.now() <= manualUntil;

    if (manual) {
      const sha = pinnedSha || await headPromise;
      if (sha) {
        try {
          const text = await pinnedText(path, sha);
          if (isContentsRequest(url)) {
            return new Response(JSON.stringify({
              type: 'file',
              encoding: 'base64',
              content: utf8ToBase64(text),
              sha,
              path
            }), {
              status: 200,
              headers: { 'Content-Type': 'application/json', 'X-Atlas-Commit': sha }
            });
          }
          return new Response(text, {
            status: 200,
            headers: { 'Content-Type': 'application/json', 'X-Atlas-Commit': sha }
          });
        } catch (_) {
          // Fall through to a direct cache-busted request if pinned raw delivery is temporarily unavailable.
        }
      }
    }

    if (isLive && url) {
      url.searchParams.set('atlas_nocache', `${Date.now()}-${generation}`);
      return nativeFetch(url.href, {
        ...init,
        cache: 'no-store',
        headers: safeHeaders(init.headers)
      });
    }
    return nativeFetch(input, init);
  };

  function markSyncing() {
    const sync = document.getElementById('syncState');
    if (sync) {
      sync.textContent = '正在读取最新提交';
      sync.dataset.state = 'syncing';
    }
    const next = document.getElementById('nextPoll');
    if (next) next.textContent = '正在全量刷新遥测与任务状态';
  }

  function callControllers() {
    try { window.AtlasScanMonitor?.refresh?.(); } catch (_) {}
    try { window.AtlasScanAiRepair?.refresh?.({ force: true }); } catch (_) {}
    try { window.AtlasAuthorCountRefresh?.({ force: true }); } catch (_) {}
  }

  async function performRefresh(reason = 'manual') {
    refreshChain = refreshChain.then(async () => {
      markSyncing();
      await beginAuthoritativeWindow();
      window.dispatchEvent(new CustomEvent('atlas-authoritative-refresh', { detail: { reason, generation } }));
      callControllers();
      for (const wait of [350, 900, 1800, 3500]) {
        await delay(wait);
        callControllers();
      }
    }).catch(() => {
      callControllers();
    });
    return refreshChain;
  }

  function isRefreshControl(target) {
    const button = target?.closest?.('button, [role="button"]');
    if (!button) return false;
    if (button.id === 'forceRefresh') return true;
    const label = [
      button.id,
      button.getAttribute('aria-label'),
      button.getAttribute('title'),
      button.textContent
    ].filter(Boolean).join(' ');
    return /(?:刷新|立即核对|refresh|reload|↻|⟳|↺|⭮)/i.test(label);
  }

  function attachClickBridge(doc) {
    if (!doc || doc.__atlasFreshRefreshAttached) return;
    doc.__atlasFreshRefreshAttached = true;
    doc.addEventListener('click', event => {
      if (!isRefreshControl(event.target)) return;
      event.preventDefault();
      event.stopImmediatePropagation();
      performRefresh('button');
    }, true);
  }

  attachClickBridge(document);
  try {
    if (window.parent && window.parent !== window && window.parent.location.origin === location.origin) {
      attachClickBridge(window.parent.document);
    }
  } catch (_) {}

  window.addEventListener('message', event => {
    if (event.data?.type !== 'atlas-monitor-refresh') return;
    event.stopImmediatePropagation();
    performRefresh('message');
  }, true);

  window.addEventListener('pageshow', event => {
    if (event.persisted) performRefresh('pageshow');
  });

  window.AtlasMonitorFreshRefresh = {
    version: VERSION,
    refresh: performRefresh,
    get pinnedSha() { return pinnedSha; },
    get generation() { return generation; }
  };

  // The first render is authoritative as well, including a normal reload from the top-right control.
  beginAuthoritativeWindow();
})();
