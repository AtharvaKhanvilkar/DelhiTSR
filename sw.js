const CACHE_NAME = 'tsr-engine-v3';

const urlsToCache = [
  '/',
  '/projects',
  '/manifest.json',
  '/static/TR-logo 1.png'
];

// INSTALL
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME)
      .then(cache => cache.addAll(urlsToCache))
  );
});

// ACTIVATE
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then(keys =>
      Promise.all(
        keys.map(key => {
          if (key !== CACHE_NAME) {
            return caches.delete(key);
          }
        })
      )
    )
  );
  self.clients.claim();
});

// FETCH
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 🚫 NEVER cache API calls (CRITICAL FIX)
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

  // 🌐 HTML pages → network first
  if (request.mode === 'navigate') {
    event.respondWith(
      fetch(request)
        .then(response => {
          const copy = response.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return response;
        })
        .catch(() => caches.match(request))
    );
    return;
  }

  // ⚡ Static assets → cache first
  event.respondWith(
    caches.match(request).then(response => {
      if (response) return response;

      return fetch(request)
        .then(fetchRes => {
          const copy = fetchRes.clone();
          caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
          return fetchRes;
        })
        .catch(() => {
          return new Response('Offline', { status: 503 });
        });
    })
  );
});

