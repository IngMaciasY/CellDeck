/*
 * PhoneDeck - OBS: un botón por escena. La PC hace de puente con OBS (ver src/phonedeck/obs.py).
 *
 * Los botones solo se rehacen si cambia la lista de escenas; al cambiar la escena activa
 * únicamente se mueve la clase "active". El nombre de una escena siempre va como texto.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const api = global.PD.api;

  function textField(form, label, type, maxLength) {
    const row = form.appendChild(u.el('label', 'obs-field'));
    row.appendChild(u.el('span', '', label));
    const input = row.appendChild(document.createElement('input'));
    input.type = type;
    if (maxLength) input.maxLength = maxLength;
    return input;
  }

  /** Formulario de conexión: solo existe desde la PC o con el celular por USB. */
  function createSettings() {
    const box = u.el('details', 'obs-settings');
    box.appendChild(u.el('summary', '', 'Configurar conexión'));
    const form = box.appendChild(u.el('div', 'obs-form'));
    form.appendChild(u.el('p', 'obs-hint',
      'En OBS abre Herramientas, entra a los ajustes de WebSocket, activa el servidor y copia aquí la contraseña.'));
    const host = textField(form, 'Equipo', 'text', 253);
    const port = textField(form, 'Puerto', 'number');
    const password = textField(form, 'Contraseña', 'password', 200);
    password.autocomplete = 'off';
    const save = form.appendChild(u.el('button', 'btn', 'Guardar y conectar'));
    save.type = 'button';

    function fill(data) {
      host.value = data.host;
      port.value = String(data.port);
      password.value = '';
      password.placeholder = data.has_password ? 'Sin cambios' : 'Sin contraseña';
    }

    box.addEventListener('toggle', function () {
      if (!box.open) return;
      api.obsSettings().then(fill, function (err) { u.toast(err.message, 'error'); });
    });

    save.addEventListener('click', function () {
      const body = { host: host.value.trim(), port: Number(port.value) };
      if (password.value) body.password = password.value;
      save.disabled = true;
      api.saveObsSettings(body).then(function (data) {
        save.disabled = false;
        fill(data);
        box.open = false;
        u.toast('Guardado', 'ok');
      }, function (err) {
        save.disabled = false;
        u.toast(err.status === 422 ? 'Revisa el equipo y el puerto' : err.message, 'error');
      });
    });

    return box;
  }

  function createObs(item, ctx) {
    const el = u.el('div', 'widget w-obs');
    const status = el.appendChild(u.el('div', 'obs-status'));
    const dot = status.appendChild(u.el('span', 'obs-dot'));
    const text = status.appendChild(u.el('span', '', 'Conectando con OBS…'));
    const list = el.appendChild(u.el('div', 'obs-scenes'));
    const info = global.PD.app && global.PD.app.state.info;
    if (info && info.loopback) el.appendChild(createSettings());

    let listKey = null;
    let buttons = {};

    function select(name) {
      u.vibrate(15);
      if (!ctx.send('obs.scene', { name: name })) u.toast('Sin conexión con la PC', 'error');
    }

    function renderScenes(scenes) {
      const key = JSON.stringify(scenes);
      if (key === listKey) return;
      listKey = key;
      list.innerHTML = '';
      buttons = {};
      scenes.forEach(function (name) {
        const btn = list.appendChild(u.el('button', 'obs-scene', name));
        btn.type = 'button';
        btn.addEventListener('click', function () { select(name); });
        buttons[name] = btn;
      });
    }

    function render(data) {
      const online = data.status === 'online';
      dot.className = 'obs-dot ' + data.status;
      const scenes = data.scenes || [];
      u.setText(text, online ? (data.current || 'Sin escena activa') : data.message);
      if (online && !scenes.length) u.setText(text, 'OBS no tiene escenas');
      renderScenes(scenes);
      Object.keys(buttons).forEach(function (name) {
        const active = name === data.current;
        buttons[name].classList.toggle('active', active);
        buttons[name].setAttribute('aria-pressed', active ? 'true' : 'false');
      });
    }

    return {
      el: el,
      update: function (type, data) {
        if (type === 'obs' && data) render(data);
      },
      destroy: function () {}
    };
  }

  global.PD.widgets.register('obs', createObs);
})(window);
