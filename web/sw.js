const CACHE_NAME = "meikova-loop-v175";
const STATIC_ASSETS = [
  "/",
  "/css/app.css?v=173",
  "/img/favicon.svg",
  "/img/icon-192.png",
  "/img/icon-512.png",
  "/img/apple-touch-icon.png",
  "/audio/silence.mp3",
  "/js/main.js?v=173",
  "/js/api.js?v=173",
  "/js/engine.js?v=173",
  "/js/player.js?v=173",
  "/js/viz.js?v=173",
  "/js/stage_sync.js?v=173",
  "/js/harmonic.js?v=173",
  "/js/theme.js?v=173",
  "/js/graph.js?v=173",
  "/js/mediasession.js?v=173",
  "/js/recorder.js?v=173",
  "/js/mic.js?v=173",
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
    caches.keys().then(async (keys) => {
      const oldKeys = keys.filter((k) => k !== CACHE_NAME);
      await Promise.all(oldKeys.map((k) => caches.delete(k)));
      await self.clients.claim();
      if (oldKeys.length > 0) {
        const clients = await self.clients.matchAll({ type: "window" });
        for (const client of clients) {
          try {
            client.navigate(client.url);
          } catch (_) {}
        }
      }
    })
  );
});

self.addEventListener("fetch", (e) => {
  const url = new URL(e.request.url);

  // Never intercept API requests, dynamic range audio streams, or websockets
  if (url.pathname.startsWith("/api/") || url.pathname.startsWith("/audio/stream")) {
    return;
  }

  // Network-first strategy bypassing HTTP disk cache for JS/CSS/HTML
  const isCode = url.pathname === "/" || url.pathname.endsWith(".js") || url.pathname.endsWith(".css") || url.pathname.endsWith(".html");
  const fetchReq = isCode ? new Request(e.request, { cache: "no-store" }) : e.request;
  e.respondWith(
    fetch(fetchReq)
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
