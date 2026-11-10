/*
 * CellDeck - renderizado de una página: grid de botones y widgets.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const icon = global.PD.icons.icon;

  let widgets = [];

  function isPortrait() {
    return global.innerHeight >= global.innerWidth;
  }

  /**
   * Modo de distribución efectivo. Cada celular puede elegir en su menú un tamaño de
   * botón propio (se guarda solo en ese dispositivo); si no, manda la config de la PC.
   * @returns {{mode: string, size: number}}
   */
  function effectiveLayout(appearance) {
    const a = appearance || {};
    const local = parseInt(u.store.get('btnsize', ''), 10);
    if (local > 0) return { mode: 'auto', size: local };
    return { mode: a.layout === 'fixed' ? 'fixed' : 'auto', size: a.button_size || 104 };
  }

  /** Mide el espacio disponible (si aún no está en pantalla, estima con la ventana). */
  function metrics(gridEl) {
    const style = global.getComputedStyle(gridEl);
    const gap = parseFloat(style.getPropertyValue('--gap')) || 10;
    const width = gridEl.clientWidth || (global.innerWidth - 2 * gap);
    const page = gridEl.parentNode;
    const height = (page && page.clientHeight) || global.innerHeight;
    // En horizontal: que quepan al menos 3 filas sin desplazarse.
    const maxCell = isPortrait() ? 0 : Math.floor((height - gap * 4) / 3);
    return { gap: gap, width: width, maxCell: maxCell > 60 ? maxCell : 0 };
  }

  /**
   * Columnas para la pantalla actual.
   * - auto: tantas como quepan del tamaño ideal → 3 en un celular vertical, 6-7 en
   *   horizontal, 7-10 en una tablet. Sirve igual para un teléfono viejo o uno nuevo.
   * - fixed: las de la config según la orientación.
   */
  function columnsFor(appearance, gridEl) {
    const a = appearance || {};
    const lay = effectiveLayout(a);
    if (lay.mode === 'fixed') {
      return isPortrait() ? (a.columns_portrait || 3) : (a.columns_landscape || 6);
    }
    const m = metrics(gridEl || document.getElementById('grid'));
    const size = m.maxCell ? Math.min(lay.size, m.maxCell) : lay.size;
    return u.clamp(Math.floor((m.width + m.gap) / (size + m.gap)), 2, 12);
  }

  /** Ajusta columnas y tamaño de celda (botones cuadrados). Devuelve las columnas. */
  function layout(gridEl, appearance) {
    const cols = columnsFor(appearance, gridEl);
    const m = metrics(gridEl);
    let cell = Math.floor((m.width - m.gap * (cols - 1)) / cols);
    if (m.maxCell) cell = Math.min(cell, m.maxCell);
    cell = Math.max(56, cell);
    gridEl.style.setProperty('--cols', String(cols));
    gridEl.style.setProperty('--cell', cell + 'px');
    resizeWidgets();
    return cols;
  }

  function resizeWidgets() {
    widgets.forEach(function (w) { if (w.resize) w.resize(); });
  }

  // Icono genérico si no se puede mostrar el logotipo de la app (no instalada, sin red...).
  const APP_FALLBACK = { steam: 'gamepad', epic: 'gamepad', visualstudio: 'code', vscode: 'code', brave: 'globe' };

  function fallbackIcon(item) {
    const action = item.action || {};
    if (action.type === 'app') return APP_FALLBACK[action.app] || 'square';
    if (action.type === 'url') return 'globe';
    if (action.type === 'launch') return 'folder';
    return 'square';
  }

  /**
   * Logotipo oficial de la app (extraído por la PC del .exe instalado). La URL lleva la
   * revisión de la config para que el navegador la cachee; si falla, icono genérico.
   */
  function appIcon(item, ctx) {
    const img = document.createElement('img');
    img.className = 'key-img';
    img.alt = '';
    img.setAttribute('draggable', 'false');
    img.onerror = function () {
      if (img.parentNode) img.parentNode.replaceChild(icon(fallbackIcon(item)), img);
    };
    img.src = '/api/icon/' + encodeURIComponent(ctx.pageId) + '/' + encodeURIComponent(item.id) +
      '?v=' + encodeURIComponent(ctx.revision || '') +
      '&token=' + encodeURIComponent(global.PD.api.getToken() || '');
    return img;
  }

  function createButton(item, onPress, ctx) {
    const btn = u.el('button', 'key');
    btn.type = 'button';
    btn.setAttribute('data-id', item.id);
    if (item.color) {
      btn.style.background = item.color;
      if (u.isLightColor(item.color)) btn.classList.add('dark-text');
    }
    btn.appendChild(item.icon === 'app' ? appIcon(item, ctx) : icon(item.icon || 'square'));
    const label = u.el('span', 'key-label', item.label || '');
    btn.appendChild(label);
    if (item.label) btn.setAttribute('aria-label', item.label);

    // Feedback visual inmediato al tocar (antes del click).
    btn.addEventListener('touchstart', function () { btn.classList.add('pressed'); }, { passive: true });
    btn.addEventListener('mousedown', function () { btn.classList.add('pressed'); });
    ['touchend', 'touchcancel', 'mouseup', 'mouseleave'].forEach(function (evt) {
      btn.addEventListener(evt, function () { btn.classList.remove('pressed'); }, { passive: true });
    });
    btn.addEventListener('click', function () { onPress(item, btn); });
    return btn;
  }

  function destroyWidgets() {
    widgets.forEach(function (w) { w.destroy(); });
    widgets = [];
  }

  /**
   * Pinta una página.
   * @param {HTMLElement} gridEl
   * @param {object} page  página de la config
   * @param {object} appearance
   * @param {{onPress: function, widgetCtx: object,
   *          edit?: {onSelect: function(object), onAdd: function()}}} handlers
   *   Con `edit` se pinta el modo edición: tocar abre el editor (no ejecuta nada),
   *   cada elemento tiene un asa para arrastrarlo y al final hay un "+ Añadir".
   */
  function render(gridEl, page, appearance, handlers) {
    destroyWidgets();
    gridEl.innerHTML = '';
    gridEl.classList.toggle('no-labels', appearance && appearance.show_labels === false);
    const cols = layout(gridEl, appearance);
    const edit = handlers.edit || null;

    if ((!page || !page.items || !page.items.length) && !edit) {
      gridEl.appendChild(u.el('div', 'empty', 'Esta página está vacía. Toca el engranaje y luego Editar para añadir botones.'));
      return;
    }

    (page ? page.items : []).forEach(function (item) {
      let node;
      if (item.kind === 'widget') {
        const widget = global.PD.widgets.create(item, handlers.widgetCtx);
        widgets.push(widget);
        node = widget.el;
      } else {
        node = createButton(item, edit ? function () { edit.onSelect(item); } : handlers.onPress,
          { pageId: page.id, revision: handlers.revision });
      }
      const w = Math.min(item.w || 1, cols);
      const h = item.h || 1;
      if (w > 1) node.style.gridColumn = 'span ' + w;
      if (h > 1) node.style.gridRow = 'span ' + h;
      if (edit) decorateForEdit(node, item, edit);
      gridEl.appendChild(node);
    });

    if (edit) {
      const add = u.el('button', 'key add-tile');
      add.type = 'button';
      add.appendChild(icon('plus'));
      add.appendChild(u.el('span', 'key-label', 'Añadir'));
      add.addEventListener('click', edit.onAdd);
      gridEl.appendChild(add);
    }
    resizeWidgets();   // ya están en el DOM: se pueden medir
  }

  /** Modo edición: capa que intercepta toques + asa de arrastre. */
  function decorateForEdit(node, item, edit) {
    node.classList.add('edit-item');
    if (item.kind === 'widget') {
      // Los widgets tienen controles propios: la capa evita usarlos al editar.
      const overlay = node.appendChild(u.el('div', 'edit-overlay'));
      overlay.addEventListener('click', function () { edit.onSelect(item); });
    }
    const handle = node.appendChild(u.el('span', 'drag-handle'));
    handle.setAttribute('aria-label', 'Arrastrar para mover');
    handle.appendChild(icon('grip'));
    handle.addEventListener('click', function (e) { e.stopPropagation(); });
  }

  /** Reenvía un mensaje en vivo a los widgets visibles. */
  function dispatch(type, data) {
    widgets.forEach(function (w) { w.update(type, data); });
  }

  global.PD.grid = {
    render: render,
    layout: layout,
    dispatch: dispatch,
    columnsFor: columnsFor,
    effectiveLayout: effectiveLayout
  };
})(window);
