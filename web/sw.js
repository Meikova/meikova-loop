const CACHE_NAME = "mashloop-v26";
const STATIC_ASSETS = [
  "/",
  "/css/app.css",
  "/img/favicon.svg",
  "/img/icon-192.png",
  "/img/icon-512.png",
  "/img/apple-touch-icon.png",
  "/audio/silence.mp3",
  "/js/main.js",
  "/js/api.js",
  "/js/engine.js",
  "/js/player.js",
  "/js/viz.js",
  "/js/theme.js",
  "/js/graph.js",
  "/js/mediasession.js",
  "/vendor/signalsmith-stretch-1.3.2.mjs"
];

self.addEventListener("install", (e) => {
  self.skipWaiting();
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
});

self.addEventListener("activate", (e) => {
  e.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // Never intercept API requests, dynamic range audio streams, or websockets
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/audio/stream")) {
    return;
  }

  // Network-first strategy: always fetch latest from server, fallback to cache if offline
  e.respondWith(
    fetch(e.request)
      .then((resp) => {
        if (resp && resp.status === 200) {
          const toCache = resp.clone();
          caches.open(CACHE_NAME).then((cache) => cache.put(e.request, toCache)).catch(() => {});
        }
        return resp;
      })
      .catch(() => caches.match(e.request))
  );
});
