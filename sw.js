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

  // ❌ IGNORE NON-WEB REQUESTS (THIS FIXES YOUR ERROR)
  if (!request.url.startsWith('http')) return;

  // ❌ NEVER CACHE API CALLS
  if (
    request.url.includes('/events') ||
    request.url.includes('/parse') ||
    request.url.includes('/result') ||
    request.url.includes('/delete') ||
    request.url.includes('/workspace')
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