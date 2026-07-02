const CACHE_NAME = 'tsr-engine-v6';

const urlsToCache = [
  '/',
  '/projects',
  '/manifest.json',
  '/static/TR-logo 1.png'
];

self.addEventListener('install', (event) => {
  self.skipWaiting();

  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(urlsToCache))
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys.map((key) => {
          if (key !== CACHE_NAME) return caches.delete(key);
        })
      )
    )
  );

  self.clients.claim();
});

self.addEventListener('fetch', (event) => {
  const request = event.request;

  // ❌ IGNORE NON-WEB REQUESTS
  if (!request.url.startsWith('http')) return;

  // ❌ BYPASS SERVICE WORKER FOR ALL NON-GET REQUESTS (e.g. POST chat, edit, delete, clear)
  if (request.method !== 'GET') {
    event.respondWith(fetch(request));
    return;
  }

  // ❌ NEVER CACHE DYNAMIC API CALLS OR DOC PAYLOADS
  const url = request.url;
  if (
    url.includes('/events') ||
    url.includes('/entities') ||
    url.includes('/skeleton') ||
    url.includes('/errors') ||
    url.includes('/parse') ||
    url.includes('/result') ||
    url.includes('/pdf') ||
    url.includes('/workspace')
  ) {
    event.respondWith(fetch(request));
    return;
  }

  // 🌐 NAVIGATION → ALWAYS FRESH HTML
  if (request.mode === 'navigate') {
    event.respondWith(fetch(request, { cache: 'no-store' }));
    return;
  }

  // ⚡ STATIC FILES → SAFE CACHE
  event.respondWith(
    caches.match(request).then((cached) => {
      if (cached) return cached;

      return fetch(request).then((response) => {
        const clone = response.clone();

        caches.open(CACHE_NAME).then((cache) => {
          cache.put(request, clone);
        });

        return response;
      });
    })
  );
});