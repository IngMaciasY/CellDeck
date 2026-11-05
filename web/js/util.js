/*
 * PhoneDeck - utilidades comunes.
 * Compatibilidad Chrome 60: ES2017 como máximo (sin ?. ni ??, sin spread de objetos,
 * sin Promise.finally ni AbortController). Lo verifica ESLint en CI.
 */
(function (global) {
  'use strict';

  const PD = global.PD = global.PD || {};

  /** Crea un elemento con clase y texto opcionales (el texto siempre como textContent). */
  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  /** Ejecuta fn como mucho una vez cada `wait` ms, garantizando la última llamada. */
  function throttle(fn, wait) {
    let last = 0;
    let timer = null;
    let pendingArgs = null;
    return function () {
      pendingArgs = arguments;
      const now = Date.now();
      const remaining = wait - (now - last);
      if (remaining <= 0) {
        last = now;
        fn.apply(null, pendingArgs);
      } else if (!timer) {
        timer = setTimeout(function () {
          timer = null;
          last = Date.now();
          fn.apply(null, pendingArgs);
        }, remaining);
      }
    };
  }

  /** localStorage con tolerancia a errores (modo incógnito, cuota...). */
  const store = {
    get: function (key, fallback) {
      try {
        const raw = global.localStorage.getItem('phonedeck.' + key);
        return raw === null ? fallback : JSON.parse(raw);
      } catch (e) {
        return fallback;
      }
    },
    set: function (key, value) {
      try {
        global.localStorage.setItem('phonedeck.' + key, JSON.stringify(value));
      } catch (e) { /* sin almacenamiento: se ignora */ }
    },
    remove: function (key) {
      try {
        global.localStorage.removeItem('phonedeck.' + key);
      } catch (e) { /* idem */ }
    }
  };

  /** Vibración corta si está activada y el dispositivo la soporta. */
  function vibrate(ms) {
    if (!store.get('haptics', true)) return;
    if (navigator.vibrate) {
      try { navigator.vibrate(ms); } catch (e) { /* no soportado */ }
    }
  }

  /** "3:07" a partir de segundos. */
  function formatTime(seconds) {
    if (typeof seconds !== 'number' || !isFinite(seconds) || seconds < 0) return '';
    const s = Math.floor(seconds % 60);
    const m = Math.floor(seconds / 60);
    return m + ':' + (s < 10 ? '0' : '') + s;
  }

  /** true si el color hex es claro (para elegir texto oscuro encima). */
  function isLightColor(hex) {
    const m = /^#([0-9a-f]{6})$/i.exec(hex || '');
    if (!m) return false;
    const n = parseInt(m[1], 16);
    const r = (n >> 16) & 255;
    const g = (n >> 8) & 255;
    const b = n & 255;
    return (0.299 * r + 0.587 * g + 0.114 * b) > 170;
  }

  /** Muestra una notificación breve. type: '' | 'ok' | 'error'. */
  function toast(message, type, ms) {
    const box = $('toasts');
    if (!box || !message) return;
    const node = el('div', 'toast' + (type ? ' ' + type : ''), message);
    box.appendChild(node);
    while (box.children.length > 3) box.removeChild(box.firstChild);
    setTimeout(function () {
      if (node.parentNode) node.parentNode.removeChild(node);
    }, ms || (type === 'error' ? 4000 : 2200));
  }

  function show(node, visible) {
    if (node) node.classList.toggle('hidden', !visible);
  }

  PD.util = {
    el: el,
    $: $,
    clamp: clamp,
    throttle: throttle,
    store: store,
    vibrate: vibrate,
    formatTime: formatTime,
    isLightColor: isLightColor,
    toast: toast,
    show: show
  };
})(window);
