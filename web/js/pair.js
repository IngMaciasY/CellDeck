/*
 * CellDeck - página de emparejamiento (PC). Muestra PIN, dirección y QR para el modo WiFi.
 * Las rutas /api/pairing solo responden a la propia PC.
 */
(function (global) {
  'use strict';

  function $(id) { return document.getElementById(id); }
  function show(id, visible) { $(id).classList.toggle('hidden', !visible); }

  async function getJson(path, token) {
    const res = await fetch(path, { headers: token ? { 'X-CellDeck-Token': token } : {}, cache: 'no-store' });
    if (!res.ok) throw new Error('HTTP ' + res.status);
    return res.json();
  }

  async function load() {
    const msg = $('pair-msg');
    try {
      const session = await getJson('/api/session');
      const token = session.token;
      if (!token) throw new Error('Abre esta página en la propia PC (http://127.0.0.1:8765/pair.html)');
      const info = await getJson('/api/pairing', token);
      $('usb-url').textContent = info.usb_url;
      if (info.mode !== 'wifi') {
        msg.textContent = 'Modo USB activo.';
        show('usb-only', true);
        return;
      }
      msg.textContent = 'Modo WiFi activo.' + (info.allow_remote_edit
        ? ' ⚠ La edición por WiFi está permitida.' : '');
      show('wifi-box', true);
      $('pin').textContent = info.pin;
      if (!info.urls.length) {
        $('url').textContent = 'No se encontró ninguna red local activa.';
        return;
      }
      const main = info.urls[0];
      $('url').textContent = main.split('#')[0];
      const others = info.urls.slice(1).map(function (u) { return u.split('#')[0]; });
      $('other-urls').textContent = others.length ? 'Otras redes: ' + others.join(' · ') : '';
      // El QR se pide con la cabecera del token (una <img> no puede enviarla).
      const res = await fetch('/api/pairing/qr.png?url=' + encodeURIComponent(main),
        { headers: { 'X-CellDeck-Token': token } });
      if (res.ok) $('qr').src = URL.createObjectURL(await res.blob());
    } catch (err) {
      msg.textContent = 'No se pudo cargar: ' + err.message;
    }
  }

  global.addEventListener('load', load);
})(window);
