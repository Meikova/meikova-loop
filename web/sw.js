const CACHE_NAME = "mashloop-v1";
const STATIC_ASSETS = [
  "/",
  "/css/app.css",
  "/img/favicon.svg",
  "/img/og.png",
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
  e.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS)).catch(() => {})
  );
  self.skipWaiting();
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

  // Never intercept API requests or audio streams
  if (url.pathname.startsWith("/api/")) {
    return;
  }

  // Cache-first for static UI assets and fonts
  e.respondWith(
    caches.match(e.request).then((hit) => {
      if (hit) return hit;
      return fetch(e.request).then((resp) => {
        if (!resp || resp.status !== 200) {
          return resp;
        }
        const toCache = resp.clone();
        caches.open(CACHE_NAME).then((cache) => cache.put(e.request, toCache)).catch(() => {});
        return resp;
      });
    })
  );
});
