const CACHE = 'cod11-realtime-vision-v11b';
const CORE = [
  './', './index.html', './styles.css', './app.js', './chapter6-library.js',
  './focus-mode-v10.js', './cloud-realtime-v11.js', './cloud-access-v11.js',
  './manifest.webmanifest', './icon.svg'
];

self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(CORE)).catch(() => {}));
});

self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))),
    self.clients.claim()
  ]));
});

self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  const request = event.request;
  const url = new URL(request.url);
  const isAppAsset = url.origin === self.location.origin;

  if (request.mode === 'navigate' || isAppAsset) {
    event.respondWith(
      fetch(request, { cache: 'no-store' }).then(response => {
        const copy = response.clone();
        caches.open(CACHE).then(cache => cache.put(request, copy)).catch(() => {});
        return response;
      }).catch(() => caches.match(request).then(cached => cached || caches.match('./index.html')))
    );
    return;
  }

  event.respondWith(fetch(request).catch(() => caches.match(request)));
});
