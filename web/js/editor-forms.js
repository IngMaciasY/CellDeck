/*
 * PhoneDeck - piezas del editor visual: ventanas modales, campos y formularios por
 * tipo de acción. Los formularios modifican directamente el objeto que reciben.
 * Compatibilidad Chrome 60 (ES2017).
 */
(function (global) {
  'use strict';

  const PD = global.PD;
  const u = PD.util;
  const icon = PD.icons.icon;

  // ---------------------------------------------------------------- modal
  let modalDepth = 0;

  /**
   * Abre una ventana modal.
   * @param {{title: string, body: Node, actions: Array<{label: string, cls?: string,
   *          onClick?: function(): (boolean|Promise|undefined)}>, onClose?: function}} opts
   *   Si onClick devuelve false (o una promesa que resuelve false) la ventana no se cierra.
   */
  function modal(opts) {
    modalDepth++;
    const backdrop = u.el('div', 'modal-backdrop');
    backdrop.style.zIndex = String(50 + modalDepth * 2);
    const box = u.el('div', 'modal');
    box.style.zIndex = String(51 + modalDepth * 2);
    box.setAttribute('role', 'dialog');
    const head = box.appendChild(u.el('div', 'modal-head'));
    head.appendChild(u.el('h2', '', opts.title));
    const closeBtn = head.appendChild(u.el('button', 'icon-btn'));
    closeBtn.type = 'button';
    closeBtn.setAttribute('aria-label', 'Cerrar');
    closeBtn.appendChild(icon('x'));
    const body = box.appendChild(u.el('div', 'modal-body'));
    body.appendChild(opts.body);
    const foot = box.appendChild(u.el('div', 'modal-foot'));

    let closed = false;
    function close() {
      if (closed) return;
      closed = true;
      modalDepth--;
      document.body.removeChild(backdrop);
      document.body.removeChild(box);
      if (opts.onClose) opts.onClose();
    }

    (opts.actions || []).forEach(function (action) {
      const btn = foot.appendChild(u.el('button', 'btn' + (action.cls ? ' ' + action.cls : ''), action.label));
      btn.type = 'button';
      btn.addEventListener('click', function () {
        const result = action.onClick ? action.onClick() : undefined;
        Promise.resolve(result).then(function (keep) {
          if (keep !== false) close();
        });
      });
    });
    closeBtn.addEventListener('click', close);
    backdrop.addEventListener('click', close);
    document.body.appendChild(backdrop);
    document.body.appendChild(box);
    return { close: close, body: body, box: box };
  }

  /** Diálogo de confirmación. Devuelve una promesa con true/false. */
  function confirmDialog(title, message, okLabel, danger) {
    return new Promise(function (resolve) {
      let answered = false;
      modal({
        title: title,
        body: u.el('p', '', message),
        actions: [
          { label: 'Cancelar', onClick: function () { answered = true; resolve(false); } },
          { label: okLabel || 'Aceptar', cls: danger ? 'btn-danger' : 'btn-primary',
            onClick: function () { answered = true; resolve(true); } }
        ],
        onClose: function () { if (!answered) resolve(false); }
      });
    });
  }

  // --------------------------------------------------------------- campos
  function field(label, control, hint) {
    // div (no label): tocar el texto no debe activar el primer botón del control.
    const wrap = u.el('div', 'field');
    wrap.appendChild(u.el('span', 'field-label', label));
    wrap.appendChild(control);
    if (hint) wrap.appendChild(u.el('span', 'field-hint', hint));
    return wrap;
  }

  function input(value, onInput, opts) {
    const o = opts || {};
    const node = document.createElement('input');
    node.type = o.type || 'text';
    node.className = 'input';
    if (o.placeholder) node.placeholder = o.placeholder;
    if (o.min !== undefined) node.min = String(o.min);
    if (o.max !== undefined) node.max = String(o.max);
    if (o.maxLength) node.maxLength = o.maxLength;
    node.value = value === undefined || value === null ? '' : String(value);
    node.setAttribute('autocomplete', 'off');
    node.setAttribute('autocapitalize', 'off');
    node.setAttribute('spellcheck', 'false');
    node.addEventListener('input', function () {
      onInput(o.type === 'number' ? (node.value === '' ? null : Number(node.value)) : node.value);
    });
    return node;
  }

  function select(options, value, onChange) {
    const node = document.createElement('select');
    node.className = 'input';
    options.forEach(function (opt) {
      const o = document.createElement('option');
      o.value = opt[0];
      o.textContent = opt[1];
      node.appendChild(o);
    });
    node.value = value;
    node.addEventListener('change', function () { onChange(node.value); });
    return node;
  }

  function checkbox(label, checked, onChange) {
    const wrap = u.el('label', 'check');
    const box = document.createElement('input');
    box.type = 'checkbox';
    box.checked = !!checked;
    box.addEventListener('change', function () { onChange(box.checked); });
    wrap.appendChild(box);
    wrap.appendChild(u.el('span', '', label));
    return wrap;
  }

  function textarea(value, onInput, rows) {
    const node = document.createElement('textarea');
    node.className = 'input';
    node.rows = rows || 3;
    node.value = value || '';
    node.setAttribute('spellcheck', 'false');
    if (onInput) node.addEventListener('input', function () { onInput(node.value); });
    return node;
  }

  function chips(list) {
    const wrap = u.el('div', 'chips');
    list.forEach(function (c) {
      const b = wrap.appendChild(u.el('button', 'chip', c[0]));
      b.type = 'button';
      b.addEventListener('click', function (e) {
        e.preventDefault();
        c[1]();
      });
    });
    return wrap;
  }

  function stepper(value, min, max, onChange) {
    const wrap = u.el('div', 'stepper');
    const minus = wrap.appendChild(u.el('button', 'icon-btn', '−'));
    const out = wrap.appendChild(u.el('span', 'stepper-value', value));
    const plus = wrap.appendChild(u.el('button', 'icon-btn', '+'));
    minus.type = plus.type = 'button';
    function set(v) {
      value = u.clamp(v, min, max);
      out.textContent = value;
      onChange(value);
    }
    minus.addEventListener('click', function (e) { e.preventDefault(); set(value - 1); });
    plus.addEventListener('click', function (e) { e.preventDefault(); set(value + 1); });
    return wrap;
  }

  // ----------------------------------------------------- icono y color
  const PALETTE = ['#4f8cff', '#1db954', '#e8a33d', '#c0392b', '#9b59b6', '#16a085', '#e84393',
    '#2c3e50', '#f1c40f', '#00b4d8', '#ff6b35', '#7f8c8d', '#ffffff', '#000000'];

  function iconPicker(value, onChange) {
    const wrap = u.el('div', 'icon-picker');
    let current = value;
    function paint() {
      Array.prototype.forEach.call(wrap.children, function (b) {
        b.classList.toggle('selected', b.getAttribute('data-icon') === current);
      });
    }
    // Opción especial: logotipo oficial de la app (lo extrae la PC del programa instalado).
    const appChoice = wrap.appendChild(u.el('button', 'icon-choice icon-choice-app', 'Logo de la app'));
    appChoice.type = 'button';
    appChoice.setAttribute('data-icon', 'app');
    appChoice.addEventListener('click', function (e) {
      e.preventDefault();
      current = 'app';
      paint();
      onChange('app');
    });
    PD.icons.names.forEach(function (name) {
      const b = wrap.appendChild(u.el('button', 'icon-choice'));
      b.type = 'button';
      b.setAttribute('data-icon', name);
      b.setAttribute('aria-label', name);
      b.appendChild(icon(name));
      b.addEventListener('click', function (e) {
        e.preventDefault();
        current = name;
        paint();
        onChange(name);
      });
    });
    paint();
    return wrap;
  }

  function colorPicker(value, onChange, allowNone) {
    const wrap = u.el('div', 'color-picker');
    let current = value || '';
    const hex = input(current, function (v) {
      if (/^#[0-9a-fA-F]{6}$/.test(v)) { current = v.toLowerCase(); paint(); onChange(current); }
    }, { placeholder: '#rrggbb', maxLength: 7 });
    hex.classList.add('hex');
    function paint() {
      Array.prototype.forEach.call(wrap.querySelectorAll('.swatch'), function (s) {
        s.classList.toggle('selected', s.getAttribute('data-color') === current);
      });
      hex.value = current;
    }
    const row = wrap.appendChild(u.el('div', 'swatches'));
    const colors = allowNone ? [''].concat(PALETTE) : PALETTE;
    colors.forEach(function (c) {
      const s = row.appendChild(u.el('button', 'swatch' + (c ? '' : ' none')));
      s.type = 'button';
      s.setAttribute('data-color', c);
      s.setAttribute('aria-label', c || 'Sin color');
      if (c) s.style.background = c;
      s.addEventListener('click', function (e) {
        e.preventDefault();
        current = c;
        paint();
        onChange(c || null);
      });
    });
    wrap.appendChild(hex);
    paint();
    return wrap;
  }

  // ------------------------------------------------- formularios de acción
  const MEDIA = [['play_pause', 'Play / Pausa'], ['next', 'Siguiente'], ['prev', 'Anterior'],
    ['stop', 'Detener'], ['vol_up', 'Subir volumen'], ['vol_down', 'Bajar volumen'], ['mute', 'Silenciar']];
  const VOLUME = [['step', 'Subir / bajar un paso'], ['set', 'Fijar un nivel'],
    ['toggle_mute', 'Silenciar / activar'], ['mute', 'Silenciar'], ['unmute', 'Activar sonido']];
  const SYSTEM = [['lock', 'Bloquear sesión'], ['monitor_off', 'Apagar pantalla'], ['sleep', 'Suspender'],
    ['hibernate', 'Hibernar ⚠'], ['shutdown', 'Apagar el equipo ⚠'], ['restart', 'Reiniciar ⚠'],
    ['logoff', 'Cerrar sesión ⚠']];

  /** Orden y nombres de los tipos incluidos (los externos se añaden detrás). */
  const BUILTIN_TYPES = [['media', 'Multimedia'], ['volume', 'Volumen'], ['app', 'Abrir aplicación instalada'],
    ['launch', 'Abrir programa / carpeta'],
    ['url', 'Abrir web / URI'], ['keys', 'Atajo de teclado / texto'], ['macro', 'Macro (varios pasos)'],
    ['system', 'Sistema'], ['wait', 'Esperar']];

  function defaults(type) {
    switch (type) {
      case 'media': return { type: type, command: 'play_pause' };
      case 'volume': return { type: type, op: 'step', value: 5 };
      case 'app': return { type: type, app: 'steam' };
      case 'launch': return { type: type, path: '' };
      case 'url': return { type: type, url: 'https://' };
      case 'keys': return { type: type, combo: 'ctrl+c' };
      case 'macro': return { type: type, steps: [{ type: 'wait', ms: 500 }] };
      case 'wait': return { type: type, ms: 500 };
      case 'system': return { type: type, command: 'lock' };
      default: return { type: type };
    }
  }

  function replaceContents(target, source) {
    Object.keys(target).forEach(function (k) { delete target[k]; });
    Object.keys(source).forEach(function (k) { target[k] = source[k]; });
  }

  /** Traduce una pulsación (KeyboardEvent) al formato de PhoneDeck: "ctrl+shift+s". */
  const CODE_NAMES = {
    Escape: 'esc', Enter: 'enter', Tab: 'tab', Space: 'space', Backspace: 'backspace', Delete: 'delete',
    Insert: 'insert', Home: 'home', End: 'end', PageUp: 'pageup', PageDown: 'pagedown', ArrowUp: 'up',
    ArrowDown: 'down', ArrowLeft: 'left', ArrowRight: 'right', PrintScreen: 'printscreen', Minus: '-',
    Equal: '=', Comma: ',', Period: '.', Slash: '/', Backquote: '`', BracketLeft: '[', BracketRight: ']',
    Backslash: '\\', Quote: "'", Semicolon: ';', CapsLock: 'capslock', Pause: 'pause', ContextMenu: 'menu',
    NumpadAdd: 'add', NumpadSubtract: 'subtract', NumpadMultiply: 'multiply', NumpadDivide: 'divide',
    NumpadDecimal: 'decimal'
  };

  function comboFromEvent(e) {
    const code = e.code || '';
    if (/^(Control|Shift|Alt|Meta|OS)/.test(code) || /^(Control|Shift|Alt|Meta|OS)$/.test(e.key)) return null;
    let key = CODE_NAMES[code] || null;
    let m;
    if (!key && (m = /^Key([A-Z])$/.exec(code))) key = m[1].toLowerCase();
    if (!key && (m = /^Digit(\d)$/.exec(code))) key = m[1];
    if (!key && (m = /^F(\d{1,2})$/.exec(code))) key = 'f' + m[1];
    if (!key && (m = /^Numpad(\d)$/.exec(code))) key = 'numpad' + m[1];
    if (!key) return null;
    const parts = [];
    if (e.ctrlKey) parts.push('ctrl');
    if (e.shiftKey) parts.push('shift');
    if (e.altKey) parts.push('alt');
    if (e.metaKey) parts.push('win');
    parts.push(key);
    return parts.join('+');
  }

  const FORMS = {
    app: function (a, ctx) {
      const apps = ctx.apps || [];
      const options = apps.map(function (app) {
        return [app.id, app.name + (app.installed ? '  ✓' : '  (no encontrada en esta PC)')];
      });
      if (!options.length) options.push([a.app, a.app]);
      return field('Aplicación', select(options, a.app, function (v) {
        a.app = v;
        const app = apps.filter(function (x) { return x.id === v; })[0];
        if (app && ctx.onAppChosen) ctx.onAppChosen(app);
      }), 'PhoneDeck la busca donde Windows la tenga instalada (registro, accesos, carpetas): ' +
        'no hace falta escribir la ruta. ✓ = encontrada en esta PC.');
    },

    media: function (a) {
      return field('Acción', select(MEDIA, a.command, function (v) { a.command = v; }),
        'Teclas multimedia de Windows: funcionan con Spotify, el navegador y casi cualquier reproductor.');
    },

    volume: function (a) {
      const wrap = u.el('div');
      const valueField = field('Valor', input(a.value, function (v) { a.value = v === null ? 0 : v; },
        { type: 'number', min: -100, max: 100 }), '');
      function refresh() {
        const needsValue = a.op === 'set' || a.op === 'step';
        valueField.style.display = needsValue ? '' : 'none';
        valueField.querySelector('.field-hint').textContent =
          a.op === 'set' ? 'Nivel de 0 a 100.' : 'Cuánto sube (positivo) o baja (negativo), p. ej. 5 o -5.';
        if (!needsValue) delete a.value;
        else if (a.value === undefined) a.value = a.op === 'set' ? 50 : 5;
      }
      wrap.appendChild(field('Acción', select(VOLUME, a.op, function (v) {
        a.op = v;
        refresh();
        valueField.querySelector('input').value = a.value === undefined ? '' : a.value;
      })));
      wrap.appendChild(valueField);
      refresh();
      return wrap;
    },

    launch: function (a) {
      const wrap = u.el('div');
      wrap.appendChild(field('Programa, archivo o carpeta', input(a.path, function (v) { a.path = v; },
        { placeholder: 'C:\\Program Files\\...\\app.exe' }),
        'Ruta completa a un .exe, acceso directo (.lnk), documento o carpeta. Admite %USERPROFILE%, %APPDATA%...'));
      wrap.appendChild(chips([
        ['Explorador', function () { a.path = 'explorer.exe'; wrap.querySelector('input').value = a.path; }],
        ['Bloc de notas', function () { a.path = 'notepad.exe'; wrap.querySelector('input').value = a.path; }],
        ['Calculadora', function () { a.path = 'calc.exe'; wrap.querySelector('input').value = a.path; }],
        ['Descargas', function () { a.path = '%USERPROFILE%\\Downloads'; wrap.querySelector('input').value = a.path; }]
      ]));
      wrap.appendChild(field('Argumentos (uno por línea, opcional)', textarea((a.args || []).join('\n'), function (v) {
        const args = v.split('\n').map(function (s) { return s.trim(); }).filter(Boolean);
        if (args.length) a.args = args; else delete a.args;
      }, 2)));
      wrap.appendChild(field('Carpeta de trabajo (opcional)', input(a.cwd, function (v) {
        if (v.trim()) a.cwd = v.trim(); else delete a.cwd;
      })));
      return wrap;
    },

    url: function (a) {
      const wrap = u.el('div');
      const inp = input(a.url, function (v) { a.url = v.trim(); }, { placeholder: 'https://...' });
      wrap.appendChild(field('Dirección', inp,
        'Webs (https://) o apps: spotify:, steam://rungameid/570, ms-settings:display, discord://...'));
      function set(v) { a.url = v; inp.value = v; inp.focus(); }
      wrap.appendChild(chips([
        ['https://', function () { set('https://'); }],
        ['Spotify', function () { set('spotify:'); }],
        ['Steam', function () { set('steam://open/main'); }],
        ['Ajustes de Windows', function () { set('ms-settings:'); }]
      ]));
      return wrap;
    },

    keys: function (a) {
      const wrap = u.el('div');
      const mode = a.text !== undefined ? 'text' : 'combo';
      const comboInput = input(a.combo, function (v) { a.combo = v; }, { placeholder: 'ctrl+shift+esc' });
      const comboBox = u.el('div');
      comboBox.appendChild(field('Combinación', comboInput,
        'Teclas separadas por +. Ej.: ctrl+c, alt+tab, win+d, ctrl+shift+esc, f5, plus (para +).'));
      function addMod(m) {
        const parts = (comboInput.value || '').split('+').filter(Boolean);
        if (parts.indexOf(m) < 0) parts.unshift(m);
        comboInput.value = parts.join('+') + (parts.length === 1 ? '+' : '');
        a.combo = comboInput.value;
        comboInput.focus();
      }
      comboBox.appendChild(chips([
        ['Ctrl', function () { addMod('ctrl'); }], ['Shift', function () { addMod('shift'); }],
        ['Alt', function () { addMod('alt'); }], ['Win', function () { addMod('win'); }]
      ]));
      const record = comboBox.appendChild(u.el('button', 'btn btn-small', '⌨ Grabar desde el teclado de la PC'));
      record.type = 'button';
      let listening = false;
      function onKey(e) {
        const combo = comboFromEvent(e);
        if (!combo) return;   // solo modificadores: seguir esperando
        e.preventDefault();
        e.stopPropagation();
        a.combo = combo;
        comboInput.value = combo;
        stop();
      }
      function stop() {
        listening = false;
        record.textContent = '⌨ Grabar desde el teclado de la PC';
        document.removeEventListener('keydown', onKey, true);
      }
      record.addEventListener('click', function (e) {
        e.preventDefault();
        if (listening) { stop(); return; }
        listening = true;
        record.textContent = 'Pulsa la combinación… (toca aquí para cancelar)';
        document.addEventListener('keydown', onKey, true);
      });

      const textBox = field('Texto a escribir', textarea(a.text, function (v) { a.text = v; }, 3),
        'Se escribe en la ventana activa de la PC. Los saltos de línea pulsan Enter.');

      function apply(m) {
        if (m === 'text') {
          delete a.combo;
          if (a.text === undefined) a.text = '';
        } else {
          delete a.text;
          if (!a.combo) a.combo = comboInput.value || 'ctrl+c';
          comboInput.value = a.combo;
        }
        comboBox.style.display = m === 'combo' ? '' : 'none';
        textBox.style.display = m === 'text' ? '' : 'none';
      }
      wrap.appendChild(field('Tipo', select([['combo', 'Atajo de teclado'], ['text', 'Escribir texto']], mode, apply)));
      wrap.appendChild(comboBox);
      wrap.appendChild(textBox);
      apply(mode);
      return wrap;
    },

    system: function (a) {
      return field('Comando', select(SYSTEM, a.command, function (v) { a.command = v; }),
        'Los marcados con ⚠ siempre piden confirmación (doble toque) antes de ejecutarse.');
    },

    wait: function (a) {
      return field('Milisegundos', input(a.ms, function (v) { a.ms = v === null ? 0 : v; },
        { type: 'number', min: 0, max: 60000 }), '1000 ms = 1 segundo (máx. 60000).');
    },

    macro: function (a, ctx) {
      const wrap = u.el('div', 'macro');
      const list = wrap.appendChild(u.el('div', 'macro-steps'));
      const stepTypes = ctx.types.filter(function (t) { return t[0] !== 'macro'; });

      function render() {
        list.innerHTML = '';
        a.steps.forEach(function (step, i) {
          const card = list.appendChild(u.el('div', 'macro-step'));
          const head = card.appendChild(u.el('div', 'macro-step-head'));
          head.appendChild(u.el('span', 'macro-step-num', String(i + 1)));
          head.appendChild(select(stepTypes, step.type, function (v) {
            a.steps[i] = defaults(v);
            render();
          }));
          [['chevron-up', -1], ['chevron-down', 1]].forEach(function (p) {
            const b = head.appendChild(u.el('button', 'icon-btn'));
            b.type = 'button';
            b.appendChild(icon(p[0]));
            b.disabled = (i === 0 && p[1] < 0) || (i === a.steps.length - 1 && p[1] > 0);
            b.addEventListener('click', function (e) {
              e.preventDefault();
              const j = i + p[1];
              const tmp = a.steps[i];
              a.steps[i] = a.steps[j];
              a.steps[j] = tmp;
              render();
            });
          });
          const del = head.appendChild(u.el('button', 'icon-btn'));
          del.type = 'button';
          del.appendChild(icon('trash'));
          del.disabled = a.steps.length === 1;
          del.addEventListener('click', function (e) {
            e.preventDefault();
            a.steps.splice(i, 1);
            render();
          });
          card.appendChild(actionForm(step, ctx));
        });
      }
      render();
      wrap.appendChild(chips([
        ['+ Paso', function () { a.steps.push(defaults('keys')); render(); }],
        ['+ Espera', function () { a.steps.push(defaults('wait')); render(); }]
      ]));
      wrap.appendChild(checkbox('Detener la macro si un paso falla', a.stop_on_error !== false, function (v) {
        if (v) delete a.stop_on_error; else a.stop_on_error = false;
      }));
      return wrap;
    }
  };

  /** Formulario genérico (plugins externos): JSON de la acción. */
  function jsonForm(a) {
    const area = textarea(JSON.stringify(a, null, 2), null, 6);
    const error = u.el('span', 'field-hint error-text', '');
    area.addEventListener('input', function () {
      try {
        const parsed = JSON.parse(area.value);
        if (!parsed || typeof parsed !== 'object' || parsed.type !== a.type) {
          throw new Error('Debe ser un objeto con "type": "' + a.type + '"');
        }
        replaceContents(a, parsed);
        error.textContent = '';
      } catch (e) {
        error.textContent = e.message;
      }
    });
    const wrap = field('Parámetros (JSON)', area, 'Plugin externo: consulta su documentación.');
    wrap.appendChild(error);
    return wrap;
  }

  /** Devuelve el formulario adecuado para la acción (modifica `action` en el sitio). */
  function actionForm(action, ctx) {
    const builder = FORMS[action.type];
    return builder ? builder(action, ctx) : jsonForm(action);
  }

  /** Lista [tipo, nombre] con los tipos que el servidor tiene registrados. */
  function actionTypes(plugins) {
    const available = {};
    (plugins || []).forEach(function (p) { available[p.type] = p.title; });
    const list = BUILTIN_TYPES.filter(function (t) { return !plugins || available[t[0]]; });
    Object.keys(available).forEach(function (type) {
      if (!BUILTIN_TYPES.some(function (t) { return t[0] === type; })) {
        list.push([type, available[type] + ' (plugin)']);
      }
    });
    return list;
  }

  PD.form = {
    modal: modal,
    confirm: confirmDialog,
    field: field,
    input: input,
    select: select,
    checkbox: checkbox,
    textarea: textarea,
    chips: chips,
    stepper: stepper,
    iconPicker: iconPicker,
    colorPicker: colorPicker,
    actionForm: actionForm,
    actionTypes: actionTypes,
    defaults: defaults,
    comboFromEvent: comboFromEvent
  };
})(window);
