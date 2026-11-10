/*
 * CellDeck - service worker (solo se registra en http://localhost, contexto seguro).
 *
 * - Recursos versionados (?v=hash): "caché primero". Su contenido nunca cambia, así que
 *   tras la primera visita no se piden de nuevo a la PC.
 * - Páginas y demás: "red primero"; la caché solo sirve para mostrar la interfaz (y su
 *   aviso de reconexión) si la PC no responde.
 * - Nunca se cachea /api/ ni /ws.
 */
'use strict';

const CACHE = 'celldeck-v3';
const SHELL = ['./'];

self.addEventListener('install', function (event) {
  event.waitUntil(
    caches.open(CACHE)
      .then(function (cache) { return cache.addAll(SHELL); })
      .then(function () { return self.skipWaiting(); })
  );
});

self.addEventListener('activate', function (event) {
  event.waitUntil(
    caches.keys()
      .then(function (keys) {
        return Promise.all(keys.filter(function (k) { return k !== CACHE; }).map(function (k) {
          return caches.delete(k);
        }));
      })
      .then(function () { return self.clients.claim(); })
  );
});

const store = function (req, res) {
  if (res && res.ok) {
    const copy = res.clone();
    caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
  }
  return res;
};

self.addEventListener('fetch', function (event) {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.indexOf('/api/') === 0 || url.pathname === '/ws') return;

  if (url.searchParams.has('v')) {
    event.respondWith(
      caches.match(req).then(function (hit) {
        return hit || fetch(req).then(function (res) { return store(req, res); });
      })
    );
    return;
  }

  event.respondWith(
    fetch(req)
      .then(function (res) { return store(req, res); })
      .catch(function () {
        return caches.match(req).then(function (hit) { return hit || caches.match('./'); });
      })
  );
});
