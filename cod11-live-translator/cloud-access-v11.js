'use strict';

(() => {
  const originalFetch = window.fetch.bind(window);
  window.fetch = function securedFetch(input, init = {}) {
    const url = typeof input === 'string' ? input : input?.url || '';
    if (/\/api\/realtime\/call(?:\?|$)/i.test(url)) {
      const headers = new Headers(init.headers || (typeof input !== 'string' ? input.headers : undefined));
      headers.set('X-App-Token', localStorage.getItem('cod11-realtime-access-token') || '');
      init = { ...init, headers };
    }
    return originalFetch(input, init);
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
