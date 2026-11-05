/*
 * PhoneDeck - service worker mínimo (solo se registra en http://localhost, contexto seguro).
 * Estrategia "red primero": siempre se usa la versión de la PC; la caché solo sirve
 * para mostrar la interfaz (y su aviso de reconexión) si la PC no responde.
 * Nunca se cachea /api/ ni /ws.
 */
'use strict';

const CACHE = 'phonedeck-shell-v1';
const SHELL = [
  './',
  'index.html',
  'manifest.json',
  'css/app.css',
  'js/util.js',
  'js/icons.js',
  'js/api.js',
  'js/ws.js',
  'js/nosleep.js',
  'js/widgets.js',
  'js/grid.js',
  'js/app.js',
  'icons/app-192.png',
  'media/nosleep.webm'
];

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

self.addEventListener('fetch', function (event) {
  const req = event.request;
  const url = new URL(req.url);
  if (req.method !== 'GET' || url.origin !== self.location.origin) return;
  if (url.pathname.indexOf('/api/') === 0 || url.pathname === '/ws') return;

  event.respondWith(
    fetch(req)
      .then(function (res) {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then(function (cache) { cache.put(req, copy); });
        }
        return res;
      })
      .catch(function () {
        return caches.match(req).then(function (hit) { return hit || caches.match('index.html'); });
      })
  );
});
