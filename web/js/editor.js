/*
 * PhoneDeck - editor visual (celular o PC).
 *
 * Se edita una copia (borrador) de la config. Nada se aplica en la PC hasta pulsar
 * "Guardar"; entonces se envía completa con su revisión (si otro dispositivo guardó
 * antes, el servidor responde 409 y se ofrece descartar o sobrescribir).
 *
 * Mover: arrastrar el asa ⠿ de cada elemento (pointer events) o usar "Mover" en su
 * ventana de edición (alternativa para navegadores sin pointer events).
 */
(function (global) {
  'use strict';

  const PD = global.PD;
  const u = PD.util;
  const api = PD.api;
  const F = PD.form;
  const icon = PD.icons.icon;
  const $ = u.$;

  const WIDGET_TYPES = [['now_playing', 'Ahora suena'], ['volume', 'Volumen'], ['clock', 'Reloj'],
    ['stats', 'CPU / RAM']];

  const E = {
    active: false,
    draft: null,
    revision: null,
    dirty: false,
    remoteChanged: false,
    plugins: null,
    apps: null
  };

  /** Vista previa del icono: "Logo de la app" o el SVG correspondiente. */
  function iconPreview(name) {
    return name === 'app' ? u.el('span', 'icon-preview-app', 'Logo de la app') : icon(name || 'square');
  }

  function clone(obj) {
    return JSON.parse(JSON.stringify(obj));
  }

  function app() {
    return PD.app;
  }

  function currentPage() {
    const st = app().state;
    const pages = E.draft.pages;
    for (let i = 0; i < pages.length; i++) {
      if (pages[i].id === st.pageId) return pages[i];
    }
    return pages[0];
  }

  /** ID corto y único: "spotify-k3f9". */
  function newId(base, taken) {
    const slug = String(base || 'item').toLowerCase()
      .normalize('NFD').replace(/[̀-ͯ]/g, '')
      .replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 24) || 'item';
    let id;
    do {
      id = slug + '-' + Math.random().toString(36).slice(2, 6);
    } while (taken.indexOf(id) >= 0);
    return id;
  }

  function itemIds(page) {
    return page.items.map(function (i) { return i.id; });
  }

  // -------------------------------------------------------------- estado
  function setDirty() {
    E.dirty = true;
    $('ed-save').disabled = false;
    $('ed-status').textContent = 'Cambios sin guardar';
    app().renderAll();
  }

  function updateBar() {
    $('ed-save').disabled = !E.dirty;
    $('ed-status').textContent = E.remoteChanged
      ? 'Cambió en otro dispositivo'
      : E.dirty ? 'Cambios sin guardar' : 'Modo edición';
  }

  async function enter() {
    const st = app().state;
    if (!st.info || !st.info.can_edit) {
      u.toast('La edición desde este dispositivo está desactivada en la PC', 'error');
      return;
    }
    if (!E.plugins) {
      try {
        const results = await Promise.all([api.plugins(), api.apps()]);
        E.plugins = results[0].plugins;
        E.apps = results[1].apps;
      } catch (err) {
        u.toast('No se pudieron cargar los tipos de acción: ' + err.message, 'error');
        return;
      }
    }
    E.draft = clone(st.config);
    E.revision = st.revision;
    E.dirty = false;
    E.remoteChanged = false;
    E.active = true;
    document.body.classList.add('editing');
    u.show($('edit-bar'), true);
    updateBar();
    app().useConfig(E.draft);
  }

  function leave() {
    E.active = false;
    E.draft = null;
    document.body.classList.remove('editing');
    u.show($('edit-bar'), false);
    app().useConfig(null);   // vuelve a la config guardada
  }

  async function cancel() {
    if (E.dirty) {
      const ok = await F.confirm('Descartar cambios', '¿Salir del editor sin guardar los cambios?',
        'Descartar', true);
      if (!ok) return;
    }
    leave();
  }

  async function save(force) {
    const btn = $('ed-save');
    btn.disabled = true;
    try {
      const payload = await api.saveConfig(force ? null : E.revision, E.draft);
      app().applySaved(payload);
      leave();
      u.toast('Configuración guardada', 'ok');
    } catch (err) {
      btn.disabled = false;
      if (err.status === 409) {
        conflictDialog();
      } else if (err.status === 422) {
        showErrors(err.detail);
      } else {
        u.toast(err.message, 'error');
      }
    }
  }

  function conflictDialog() {
    F.modal({
      title: 'La configuración cambió',
      body: u.el('p', '', 'Mientras editabas, se guardó otra versión (desde la PC u otro dispositivo).'),
      actions: [
        { label: 'Descartar mis cambios', onClick: function () { leave(); app().reload(); } },
        { label: 'Sobrescribir', cls: 'btn-danger', onClick: function () { save(true); } }
      ]
    });
  }

  function showErrors(detail) {
    const body = u.el('div');
    body.appendChild(u.el('p', '', 'La PC rechazó la configuración:'));
    const list = body.appendChild(u.el('ul', 'error-list'));
    const errors = (detail && detail.errors) || [];
    (errors.length ? errors : [{ loc: '', msg: (detail && detail.message) || 'Error desconocido' }])
      .slice(0, 8).forEach(function (e) {
        list.appendChild(u.el('li', '', describeLoc(e.loc) + e.msg));
      });
    F.modal({ title: 'No se pudo guardar', body: body, actions: [{ label: 'Entendido', cls: 'btn-primary' }] });
  }

  /** "pages.0.items.3.action" → "Multimedia › Spotify: " */
  function describeLoc(loc) {
    const m = /^pages\.(\d+)(?:\.items\.(\d+))?/.exec(loc || '');
    if (!m || !E.draft) return '';
    const page = E.draft.pages[+m[1]];
    if (!page) return '';
    let text = page.name;
    if (m[2] !== undefined && page.items[+m[2]]) {
      const item = page.items[+m[2]];
      text += ' › ' + (item.label || item.widget || item.id);
    }
    return text + ': ';
  }

  /** Cambios guardados en otro sitio mientras se editaba. */
  function onRemoteConfig(payload) {
    if (!E.dirty) {
      E.draft = clone(payload.config);
      E.revision = payload.revision;
      app().useConfig(E.draft);
      return;
    }
    E.remoteChanged = true;
    updateBar();
  }

  // ------------------------------------------------------ edición de items
  function itemEditor(page, index, isNew) {
    const original = page.items[index];
    const item = clone(original);
    const body = u.el('div', 'item-editor');
    const errorBox = u.el('p', 'error-text');

    if (item.kind === 'button') {
      const labelInput = F.input(item.label, function (v) { item.label = v; },
        { maxLength: 40, placeholder: 'Nombre del botón' });
      body.appendChild(F.field('Etiqueta', labelInput));
      const actionBox = u.el('div', 'action-box');
      const types = F.actionTypes(E.plugins).filter(function (t) { return t[0] !== 'wait'; });
      const knownNames = (E.apps || []).map(function (a) { return a.name; });
      const ctx = {
        types: F.actionTypes(E.plugins),
        apps: E.apps,
        // Al elegir una app: su nombre como etiqueta (si no se escribió otro) y su logotipo.
        onAppChosen: function (app) {
          if (!item.label || item.label === 'Nuevo' || knownNames.indexOf(item.label) >= 0) {
            item.label = app.name;
            labelInput.value = app.name;
          }
          setIcon('app');
        }
      };
      function renderAction() {
        actionBox.innerHTML = '';
        actionBox.appendChild(F.actionForm(item.action, ctx));
      }
      body.appendChild(F.field('Qué hace', F.select(types, item.action.type, function (v) {
        item.action = F.defaults(v);
        renderAction();
        if (v === 'app') {
          const first = (E.apps || []).filter(function (a) { return a.id === item.action.app; })[0];
          if (first) ctx.onAppChosen(first);
        }
      })));
      body.appendChild(actionBox);
      renderAction();
      body.appendChild(F.checkbox('Pedir confirmación (doble toque)', item.confirm, function (v) {
        if (v) item.confirm = true; else delete item.confirm;
      }));
    } else {
      const optsBox = u.el('div');
      function renderOptions() {
        optsBox.innerHTML = '';
        item.options = item.options || {};
        if (item.widget === 'clock') {
          optsBox.appendChild(F.checkbox('Mostrar segundos', item.options.seconds, function (v) {
            if (v) item.options.seconds = true; else delete item.options.seconds;
          }));
        } else if (item.widget === 'now_playing') {
          optsBox.appendChild(F.checkbox('Mostrar controles (si mide 2 filas o más)',
            item.options.controls !== false, function (v) {
              if (v) delete item.options.controls; else item.options.controls = false;
            }));
        } else if (item.widget === 'volume') {
          optsBox.appendChild(u.el('p', 'field-hint',
            'Mientras exista este widget, el celular puede mover el volumen con el slider.'));
        }
      }
      body.appendChild(F.field('Widget', F.select(WIDGET_TYPES, item.widget, function (v) {
        item.widget = v;
        item.options = {};
        renderOptions();
      })));
      body.appendChild(optsBox);
      renderOptions();
    }

    // Apariencia del elemento
    let setIcon = function () {};
    if (item.kind === 'button') {
      const iconField = u.el('details', 'collapsible');
      const summary = iconField.appendChild(u.el('summary', '', 'Icono'));
      summary.appendChild(iconPreview(item.icon));
      let picker = F.iconPicker(item.icon || 'square', function (name) {
        item.icon = name;
        summary.replaceChild(iconPreview(name), summary.lastChild);
      });
      iconField.appendChild(picker);
      setIcon = function (name) {
        item.icon = name;
        summary.replaceChild(iconPreview(name), summary.lastChild);
        const fresh = F.iconPicker(name, function (n) {
          item.icon = n;
          summary.replaceChild(iconPreview(n), summary.lastChild);
        });
        iconField.replaceChild(fresh, picker);
        picker = fresh;
      };
      body.appendChild(iconField);
    }
    body.appendChild(F.field('Color', F.colorPicker(item.color, function (c) {
      if (c) item.color = c; else delete item.color;
    }, true)));
    const size = u.el('div', 'size-row');
    size.appendChild(F.field('Ancho', F.stepper(item.w || 1, 1, item.kind === 'widget' ? 6 : 4,
      function (v) { item.w = v; })));
    size.appendChild(F.field('Alto', F.stepper(item.h || 1, 1, 4, function (v) { item.h = v; })));
    body.appendChild(size);

    // Mover / duplicar / borrar
    const tools = body.appendChild(u.el('div', 'item-tools'));
    function tool(label, iconName, fn, cls) {
      const b = tools.appendChild(u.el('button', 'btn btn-small' + (cls ? ' ' + cls : '')));
      b.type = 'button';
      b.appendChild(icon(iconName));
      b.appendChild(document.createTextNode(' ' + label));
      b.addEventListener('click', fn);
      return b;
    }
    let dialog = null;
    tool('Mover antes', 'chevron-left', function () { moveItem(page, index, index - 1); dialog.close(); });
    tool('Mover después', 'chevron-right', function () { moveItem(page, index, index + 1); dialog.close(); });
    if (!isNew) {
      tool('Duplicar', 'copy', function () {
        const copy = clone(original);
        copy.id = newId(copy.label || copy.widget, itemIds(page));
        page.items.splice(index + 1, 0, copy);
        dialog.close();
        setDirty();
      });
    }
    tool('Eliminar', 'trash', async function () {
      const ok = await F.confirm('Eliminar', '¿Eliminar "' + (original.label || original.widget) + '"?',
        'Eliminar', true);
      if (!ok) return;
      page.items.splice(index, 1);
      dialog.close();
      setDirty();
    }, 'btn-danger');

    body.appendChild(errorBox);

    dialog = F.modal({
      title: isNew ? 'Nuevo elemento' : 'Editar ' + (item.kind === 'button' ? 'botón' : 'widget'),
      body: body,
      actions: [
        { label: 'Cancelar', onClick: function () { if (isNew) { page.items.splice(index, 1); app().renderAll(); } } },
        { label: 'Listo', cls: 'btn-primary', onClick: function () { return commitItem(page, index, item, errorBox); } }
      ]
    });
  }

  /** Valida en la PC el borrador con el elemento editado; si es válido lo aplica. */
  async function commitItem(page, index, item, errorBox) {
    const previous = page.items[index];
    page.items[index] = item;
    try {
      await api.validateConfig(E.draft);
    } catch (err) {
      if (err.status === 422) {
        page.items[index] = previous;
        const errors = (err.detail && err.detail.errors) || [];
        errorBox.textContent = errors.length ? errors.map(function (e) { return e.msg; }).join(' · ')
          : err.message;
        return false;   // la ventana sigue abierta para corregir
      }
      // Sin conexión: se acepta y el servidor validará al guardar.
    }
    setDirty();
    return true;
  }

  function moveItem(page, from, to) {
    if (to < 0 || to >= page.items.length || from === to) return;
    const item = page.items.splice(from, 1)[0];
    page.items.splice(to, 0, item);
    setDirty();
  }

  function addItem() {
    const page = currentPage();
    const body = u.el('div', 'add-choices');
    let dialog = null;
    function choice(label, iconName, make) {
      const b = body.appendChild(u.el('button', 'add-choice'));
      b.type = 'button';
      b.appendChild(icon(iconName));
      b.appendChild(u.el('span', '', label));
      b.addEventListener('click', function () {
        dialog.close();
        const item = make();
        page.items.push(item);
        app().renderAll();
        itemEditor(page, page.items.length - 1, true);
      });
    }
    choice('Botón', 'square', function () {
      return { kind: 'button', id: newId('boton', itemIds(page)), label: 'Nuevo', icon: 'star',
        action: F.defaults('media') };
    });
    WIDGET_TYPES.forEach(function (w) {
      const icons = { now_playing: 'music', volume: 'volume-2', clock: 'clock', stats: 'cpu' };
      choice('Widget: ' + w[1], icons[w[0]], function () {
        return { kind: 'widget', id: newId(w[0], itemIds(page)), widget: w[0],
          w: 3,
          h: w[0] === 'now_playing' ? 2 : 1 };
      });
    });
    dialog = F.modal({ title: 'Añadir', body: body, actions: [{ label: 'Cancelar' }] });
  }

  // ------------------------------------------------------------- páginas
  function pageEditor() {
    const page = currentPage();
    const pages = E.draft.pages;
    const data = { name: page.name, icon: page.icon || 'square' };
    const body = u.el('div');
    body.appendChild(F.field('Nombre', F.input(data.name, function (v) { data.name = v; }, { maxLength: 30 })));
    const iconBox = u.el('details', 'collapsible');
    iconBox.appendChild(u.el('summary', '', 'Icono'));
    iconBox.appendChild(F.iconPicker(data.icon, function (n) { data.icon = n; }));
    body.appendChild(iconBox);
    const tools = body.appendChild(u.el('div', 'item-tools'));
    let dialog = null;
    function tool(label, iconName, fn, cls) {
      const b = tools.appendChild(u.el('button', 'btn btn-small' + (cls ? ' ' + cls : '')));
      b.type = 'button';
      b.appendChild(icon(iconName));
      b.appendChild(document.createTextNode(' ' + label));
      b.addEventListener('click', fn);
    }
    const index = pages.indexOf(page);
    function movePage(delta) {
      const to = index + delta;
      if (to < 0 || to >= pages.length) return;
      pages.splice(index, 1);
      pages.splice(to, 0, page);
      dialog.close();
      setDirty();
    }
    tool('Mover a la izquierda', 'chevron-left', function () { movePage(-1); });
    tool('Mover a la derecha', 'chevron-right', function () { movePage(1); });
    tool('Eliminar página', 'trash', async function () {
      if (pages.length === 1) {
        u.toast('Debe quedar al menos una página', 'error');
        return;
      }
      const ok = await F.confirm('Eliminar página', '¿Eliminar "' + page.name + '" y sus ' +
        page.items.length + ' elementos?', 'Eliminar', true);
      if (!ok) return;
      pages.splice(index, 1);
      app().goToPage(pages[Math.max(0, index - 1)].id);
      dialog.close();
      setDirty();
    }, 'btn-danger');

    dialog = F.modal({
      title: 'Página',
      body: body,
      actions: [
        { label: 'Cancelar' },
        { label: 'Listo', cls: 'btn-primary', onClick: function () {
          if (!data.name.trim()) { u.toast('La página necesita un nombre', 'error'); return false; }
          page.name = data.name.trim().slice(0, 30);
          page.icon = data.icon;
          setDirty();
          return true;
        } }
      ]
    });
  }

  function addPage() {
    const pages = E.draft.pages;
    if (pages.length >= 30) {
      u.toast('Máximo 30 páginas', 'error');
      return;
    }
    const page = { id: newId('pagina', pages.map(function (p) { return p.id; })), name: 'Nueva página',
      icon: 'star', items: [] };
    pages.push(page);
    setDirty();
    app().goToPage(page.id);
    pageEditor();
  }

  // ----------------------------------------------------------- apariencia
  function appearanceEditor() {
    const a = clone(E.draft.appearance || {});
    const body = u.el('div');
    body.appendChild(F.field('Tema', F.select([['dark', 'Oscuro'], ['oled', 'OLED (negro puro)'],
      ['light', 'Claro']], a.theme || 'dark', function (v) { a.theme = v; })));
    body.appendChild(F.field('Color de acento', F.colorPicker(a.accent || '#4f8cff', function (c) {
      if (c) a.accent = c;
    }, false)));
    const fixedBox = u.el('div', 'size-row');
    const autoBox = u.el('div');
    function refresh() {
      fixedBox.style.display = a.layout === 'fixed' ? '' : 'none';
      autoBox.style.display = a.layout === 'fixed' ? 'none' : '';
    }
    body.appendChild(F.field('Distribución', F.select([['auto', 'Automática (se adapta a cada pantalla)'],
      ['fixed', 'Columnas fijas']], a.layout || 'auto', function (v) { a.layout = v; refresh(); })));
    const sizeOut = u.el('span', 'muted', (a.button_size || 104) + ' px');
    const range = document.createElement('input');
    range.type = 'range';
    range.min = '64';
    range.max = '220';
    range.step = '4';
    range.value = String(a.button_size || 104);
    range.addEventListener('input', function () {
      a.button_size = parseInt(range.value, 10);
      sizeOut.textContent = a.button_size + ' px';
    });
    autoBox.appendChild(F.field('Tamaño ideal de botón', range,
      'Cada celular calcula cuántas columnas caben. Cada dispositivo puede ajustarlo en su menú ☰.'));
    autoBox.appendChild(sizeOut);
    body.appendChild(autoBox);
    fixedBox.appendChild(F.field('Columnas (vertical)', F.stepper(a.columns_portrait || 3, 2, 8,
      function (v) { a.columns_portrait = v; })));
    fixedBox.appendChild(F.field('Columnas (horizontal)', F.stepper(a.columns_landscape || 6, 3, 12,
      function (v) { a.columns_landscape = v; })));
    body.appendChild(fixedBox);
    body.appendChild(F.checkbox('Mostrar etiquetas en los botones', a.show_labels !== false, function (v) {
      a.show_labels = v;
    }));
    refresh();
    F.modal({
      title: 'Apariencia',
      body: body,
      actions: [
        { label: 'Cancelar' },
        { label: 'Listo', cls: 'btn-primary', onClick: function () {
          E.draft.appearance = a;
          setDirty();
        } }
      ]
    });
  }

  // ----------------------------------------------------------- arrastrar
  let drag = null;

  function autoScroll(clientY) {
    const page = $('page');
    const rect = page.getBoundingClientRect();
    if (clientY < rect.top + 50) page.scrollTop -= 12;
    else if (clientY > rect.bottom - 50) page.scrollTop += 12;
  }

  function itemsIn(gridEl) {
    return Array.prototype.slice.call(gridEl.querySelectorAll('.edit-item'));
  }

  function bindDrag(gridEl) {
    if (gridEl._pdDrag) return;
    gridEl._pdDrag = true;

    gridEl.addEventListener('pointerdown', function (e) {
      if (!E.active) return;
      const handle = e.target.closest ? e.target.closest('.drag-handle') : null;
      if (!handle) return;
      const el = handle.closest('.edit-item');
      if (!el) return;
      e.preventDefault();
      drag = { el: el, from: itemsIn(gridEl).indexOf(el), id: e.pointerId };
      el.classList.add('dragging');
      gridEl.classList.add('drag-active');
      u.vibrate(15);
      // La captura va en el grid (que no se mueve), no en el elemento arrastrado.
      try { gridEl.setPointerCapture(e.pointerId); } catch (err) { /* opcional */ }
    });

    gridEl.addEventListener('pointermove', function (e) {
      if (!drag || e.pointerId !== drag.id) return;
      e.preventDefault();
      autoScroll(e.clientY);
      const under = document.elementFromPoint(e.clientX, e.clientY);
      const target = under && under.closest ? under.closest('.edit-item') : null;
      if (!target || target === drag.el) return;
      const items = itemsIn(gridEl);
      const ti = items.indexOf(target);
      const di = items.indexOf(drag.el);
      gridEl.insertBefore(drag.el, ti > di ? target.nextSibling : target);
    });

    function end(e) {
      if (!drag || e.pointerId !== drag.id) return;
      const to = itemsIn(gridEl).indexOf(drag.el);
      const from = drag.from;
      drag.el.classList.remove('dragging');
      gridEl.classList.remove('drag-active');
      drag = null;
      if (to !== from && to >= 0) moveItem(currentPage(), from, to);
    }
    gridEl.addEventListener('pointerup', end);
    gridEl.addEventListener('pointercancel', end);
  }

  /** Manejadores que grid.render usa en modo edición. */
  function gridHandlers() {
    bindDrag($('grid'));
    return {
      onSelect: function (item) {
        const page = currentPage();
        itemEditor(page, page.items.indexOf(item), false);
      },
      onAdd: addItem
    };
  }

  /** Se llama una vez, cuando app.js termina de cargar este archivo bajo demanda. */
  function init() {
    $('ed-save').addEventListener('click', function () { save(false); });
    $('ed-cancel').addEventListener('click', cancel);
    $('ed-page').addEventListener('click', pageEditor);
    $('ed-add-page').addEventListener('click', addPage);
    $('ed-appearance').addEventListener('click', appearanceEditor);
    global.addEventListener('beforeunload', function (e) {
      if (E.active && E.dirty) {
        e.preventDefault();
        e.returnValue = '';
      }
    });
  }

  PD.editor = {
    init: init,
    toggle: function () { if (E.active) cancel(); else enter(); },
    isActive: function () { return E.active; },
    isDragging: function () { return !!drag; },
    gridHandlers: gridHandlers,
    onRemoteConfig: onRemoteConfig,
    // Para tests/depuración
    _state: E
  };
})(window);
