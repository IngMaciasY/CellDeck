/*
 * PhoneDeck - mantener la pantalla encendida.
 *
 * 1) Wake Lock API si existe (Chrome 84+).
 * 2) Si no (Chrome 60 del Redmi): técnica "NoSleep", un <video> mudo en bucle.
 *    Debe iniciarse dentro de un gesto del usuario (un toque).
 *
 * Alternativa más fiable en modo USB: Ajustes → Opciones de desarrollador →
 * "Pantalla activa" / "Mantener activo" (no se apaga mientras carga).
 */
(function (global) {
  'use strict';

  let wakeLock = null;
  let video = null;
  let wanted = false;
  let method = 'none';

  function hasWakeLockApi() {
    return 'wakeLock' in navigator;
  }

  function requestWakeLock() {
    // eslint-disable-next-line compat/compat -- detectado arriba con hasWakeLockApi()
    return navigator.wakeLock.request('screen').then(function (lock) {
      wakeLock = lock;
      method = 'wakelock';
      lock.addEventListener('release', function () { wakeLock = null; });
    });
  }

  function ensureVideo() {
    if (video) return video;
    video = document.createElement('video');
    video.className = 'nosleep-video';
    video.setAttribute('muted', '');
    video.setAttribute('playsinline', '');
    video.setAttribute('webkit-playsinline', '');
    video.setAttribute('loop', '');
    video.muted = true;
    video.loop = true;
    video.src = 'media/nosleep.webm';
    document.body.appendChild(video);
    return video;
  }

  function playVideo() {
    const v = ensureVideo();
    const result = v.play();
    method = 'video';
    if (result && typeof result.then === 'function') {
      return result.catch(function () { method = 'none'; });
    }
    return Promise.resolve();
  }

  /** Activa el bloqueo. Llamar desde un gesto del usuario la primera vez. */
  function enable() {
    wanted = true;
    if (hasWakeLockApi()) {
      return requestWakeLock().catch(playVideo);
    }
    return playVideo();
  }

  function disable() {
    wanted = false;
    method = 'none';
    if (wakeLock) {
      wakeLock.release();
      wakeLock = null;
    }
    if (video) video.pause();
  }

  // El bloqueo se pierde al pasar a segundo plano: se recupera al volver.
  document.addEventListener('visibilitychange', function () {
    if (wanted && document.visibilityState === 'visible') {
      if (hasWakeLockApi() && !wakeLock) {
        requestWakeLock().catch(function () { /* se reintenta en el próximo toque */ });
      } else if (video && video.paused) {
        playVideo();
      }
    }
  });

  global.PD = global.PD || {};
  global.PD.nosleep = {
    enable: enable,
    disable: disable,
    isWanted: function () { return wanted; },
    method: function () { return method; },
    isActive: function () {
      if (wakeLock) return true;
      return !!video && !video.paused;
    }
  };
})(window);
