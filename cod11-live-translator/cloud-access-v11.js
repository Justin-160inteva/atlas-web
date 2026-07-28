'use strict';

(() => {
  const originalFetch = window.fetch.bind(window);

  window.fetch = async function securedFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : input?.url || '';
    const isRealtimeCall = /\/api\/realtime\/call(?:\?|$)/i.test(url);

    if (isRealtimeCall) {
      const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
      headers.set('X-App-Token', localStorage.getItem('cod11-realtime-access-token') || '');
      init = { ...init, headers };
    }

    const response = await originalFetch(input, init);
    if (!isRealtimeCall || response.ok) return response;

    // The Worker returns both a short error and OpenAI's detailed upstream body.
    // Older UI code only reads the `error` field, so merge the detail into it.
    try {
      const raw = await response.clone().text();
      const data = JSON.parse(raw);
      let detail = data?.detail;

      if (typeof detail === 'string') {
        try {
          const nested = JSON.parse(detail);
          detail = nested?.error?.message || nested?.message || detail;
        } catch (_) {}
      }

      const combined = [data?.error, detail]
        .filter(Boolean)
        .map(String)
        .filter((value, index, all) => all.indexOf(value) === index)
        .join('：');

      return new Response(JSON.stringify({ ...data, error: combined || `Worker 返回 ${response.status}` }), {
        status: response.status,
        statusText: response.statusText,
        headers: response.headers,
      });
    } catch (_) {
      return response;
    }
  };

  const grid = document.querySelector('#realtimeCloudSettings .settings-grid');
  const endpoint = document.getElementById('realtimeEndpoint');
  if (!grid || !endpoint) return;

  const label = document.createElement('label');
  label.textContent = '私人访问口令';
  const input = document.createElement('input');
  input.id = 'realtimeAccessToken';
  input.type = 'password';
  input.autocomplete = 'off';
  input.placeholder = '与 Worker 的 APP_ACCESS_TOKEN 一致';
  input.value = localStorage.getItem('cod11-realtime-access-token') || '';
  input.addEventListener('change', () => {
    localStorage.setItem('cod11-realtime-access-token', input.value.trim());
  });
  label.appendChild(input);
  endpoint.closest('label')?.insertAdjacentElement('afterend', label);
})();