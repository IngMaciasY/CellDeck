/*
 * PhoneDeck - Volume Mixer: un slider y un botón de silencio por aplicación.
 *
 * La lista viene de la PC (mensaje "mixer"). Las filas se reutilizan entre mensajes: solo se
 * toca el DOM de lo que cambió. Mientras se arrastra un slider se ignoran los ecos de esa fila.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const icon = global.PD.icons.icon;
  const RELEASE_MS = 700;

  function iconNode(app) {
    const box = u.el('span', 'mixer-icon');
    box.appendChild(icon(app.key === 'system' ? 'bell' : 'music'));
    if (!app.icon) return box;
    const img = document.createElement('img');
    img.alt = '';
    img.addEventListener('load', function () {
      box.innerHTML = '';
      box.appendChild(img);
    });
    img.src = '/api/mixer/icon/' + encodeURIComponent(app.key) +
      '?token=' + encodeURIComponent(global.PD.api.getToken() || '');
    return box;
  }

  function createRow(app, ctx) {
    const el = u.el('div', 'mixer-row');
    el.appendChild(iconNode(app));
    const main = el.appendChild(u.el('div', 'mixer-main'));
    const head = main.appendChild(u.el('div', 'mixer-head'));
    const name = head.appendChild(u.el('span', 'mixer-name', app.name));
    const value = head.appendChild(u.el('span', 'mixer-value', ''));
    const slider = main.appendChild(document.createElement('input'));
    slider.type = 'range';
    slider.min = '0';
    slider.max = '100';
    slider.step = '1';
    slider.setAttribute('aria-label', 'Volumen de ' + app.name);
    const muteBtn = el.appendChild(u.el('button', 'icon-btn'));
    muteBtn.type = 'button';

    let muted = null;
    let dragging = false;
    let releaseTimer = null;

    const sendLevel = u.throttle(function (level) {
      ctx.send('mixer.set', { key: app.key, value: level });
    }, 80);

    function setMuted(next) {
      if (next === muted) return;
      muted = next;
      el.classList.toggle('muted', muted);
      muteBtn.innerHTML = '';
      muteBtn.appendChild(icon(muted ? 'volume-x' : 'volume-2'));
      muteBtn.setAttribute('aria-label', (muted ? 'Activar ' : 'Silenciar ') + app.name);
    }

    slider.addEventListener('input', function () {
      dragging = true;
      clearTimeout(releaseTimer);
      u.setText(value, slider.value + '%');
      sendLevel(parseInt(slider.value, 10));
    });
    slider.addEventListener('change', function () {
      releaseTimer = setTimeout(function () { dragging = false; }, RELEASE_MS);
    });
    muteBtn.addEventListener('click', function () {
      u.vibrate(15);
      if (!ctx.send('mixer.mute', { key: app.key, muted: !muted })) {
        u.toast('Sin conexión con la PC', 'error');
      }
    });

    return {
      el: el,
      update: function (data) {
        u.setText(name, data.name);
        setMuted(!!data.muted);
        if (!dragging) {
          if (slider.value !== String(data.level)) slider.value = String(data.level);
          u.setText(value, data.level + '%');
        }
      },
      destroy: function () { clearTimeout(releaseTimer); }
    };
  }

  function createMixer(item, ctx) {
    const el = u.el('div', 'widget w-mixer');
    const list = el.appendChild(u.el('div', 'mixer-list'));
    const message = el.appendChild(u.el('p', 'widget-message', 'Leyendo el audio de la PC…'));
    let rows = {};

    function showMessage(text) {
      u.setText(message, text || '');
      u.show(message, !!text);
    }

    function render(data) {
      const apps = data.apps || [];
      const next = {};
      apps.forEach(function (app) {
        const row = rows[app.key] || createRow(app, ctx);
        row.update(app);
        next[app.key] = row;
      });
      Object.keys(rows).forEach(function (key) {
        if (next[key]) return;
        rows[key].destroy();
        list.removeChild(rows[key].el);
      });
      // Reordena solo si hace falta: mover un nodo interrumpiría el arrastre de su slider.
      apps.forEach(function (app, index) {
        const node = next[app.key].el;
        if (list.children[index] !== node) list.insertBefore(node, list.children[index] || null);
      });
      rows = next;
      showMessage(data.error || (apps.length ? '' : 'Ninguna aplicación está usando el audio'));
    }

    return {
      el: el,
      update: function (type, data) {
        if (type === 'mixer' && data) render(data);
      },
      destroy: function () {
        Object.keys(rows).forEach(function (key) { rows[key].destroy(); });
      }
    };
  }

  global.PD.widgets.register('mixer', createMixer);
})(window);
