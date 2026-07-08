// ============================================================================
// service-worker.js
// Mise en cache des assets statiques pour un fonctionnement offline basique.
// Strategie : "cache first, fallback network" pour les assets statiques
// (CSS/JS/icones), et "network first" pour les appels API (/api/*) puisque
// la generation doit toujours utiliser des donnees fraiches.
// ============================================================================

const CACHE_NAME = "opsforge-v1";

const STATIC_ASSETS = [
  "/",
  "/static/style.css",
  "/static/script.js",
  "/static/logo.svg",
  "/static/manifest.json",
  "/static/icons/icon-192.png",
  "/static/icons/icon-512.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) => cache.addAll(STATIC_ASSETS))
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((key) => key !== CACHE_NAME)
          .map((key) => caches.delete(key))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const url = new URL(event.request.url);

  // Les appels API doivent toujours passer par le reseau : jamais de
  // generation "perimee" servie depuis un cache.
  if (url.pathname.startsWith("/api/")) {
    event.respondWith(
      fetch(event.request).catch(() =>
        new Response(
          JSON.stringify({ error: "Hors ligne : impossible de generer un pipeline sans connexion au serveur local." }),
          { status: 503, headers: { "Content-Type": "application/json" } }
        )
      )
    );
    return;
  }

  // Assets statiques : cache d'abord, reseau en secours (et mise a jour du cache).
  event.respondWith(
    caches.match(event.request).then((cachedResponse) => {
      const networkFetch = fetch(event.request)
        .then((networkResponse) => {
          if (networkResponse && networkResponse.status === 200) {
            const clone = networkResponse.clone();
            caches.open(CACHE_NAME).then((cache) => cache.put(event.request, clone));
          }
          return networkResponse;
        })
        .catch(() => cachedResponse);

      return cachedResponse || networkFetch;
    })
  );
});
