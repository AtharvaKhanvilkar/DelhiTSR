const CACHE_NAME = 'tsr-engine-v2';

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

// ACTIVATE (delete old caches)
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
  return self.clients.claim();
});

// FETCH (FIXED STRATEGY)
self.addEventListener('fetch', (event) => {
  const request = event.request;

  // 🔥 IMPORTANT: HTML → network first
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

  // ⚡ Assets → cache first
  event.respondWith(
    caches.match(request).then(response => {
      return response || fetch(request).then(fetchRes => {
        const copy = fetchRes.clone();
        caches.open(CACHE_NAME).then(cache => cache.put(request, copy));
        return fetchRes;
      });
    })
  );
});

