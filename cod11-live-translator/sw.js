const CACHE = 'cod11-dialogue-recognizer-v5';
const FILES = [
  './', './index.html', './styles.css', './app.js', './chapter6-library.js', './recognizer-v3.js', './precision-v4.js', './manifest.webmanifest',
  './icon.svg'
];
self.addEventListener('install', event => {
  self.skipWaiting();
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(FILES)));
});
self.addEventListener('activate', event => {
  event.waitUntil(Promise.all([
    caches.keys().then(keys => Promise.all(keys.filter(key => key !== CACHE).map(key => caches.delete(key)))),
    self.clients.claim()
  ]));
});
self.addEventListener('fetch', event => {
  if (event.request.method !== 'GET') return;
  event.respondWith(caches.match(event.request).then(cached => cached || fetch(event.request).then(response => {
    const copy = response.clone();
    caches.open(CACHE).then(cache => cache.put(event.request, copy)).catch(() => {});
    return response;
  }).catch(() => event.request.mode === 'navigate' ? caches.match('./index.html') : undefined)));
});
