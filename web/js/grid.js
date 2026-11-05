/*
 * PhoneDeck - renderizado de una página: grid de botones y widgets.
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

  function createButton(item, onPress) {
    const btn = u.el('button', 'key');
    btn.type = 'button';
    btn.setAttribute('data-id', item.id);
    if (item.color) {
      btn.style.background = item.color;
      if (u.isLightColor(item.color)) btn.classList.add('dark-text');
    }
    btn.appendChild(icon(item.icon || 'square'));
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
   * @param {{onPress: function, widgetCtx: object}} handlers
   */
  function render(gridEl, page, appearance, handlers) {
    destroyWidgets();
    gridEl.innerHTML = '';
    gridEl.classList.toggle('no-labels', appearance && appearance.show_labels === false);
    const cols = layout(gridEl, appearance);

    if (!page || !page.items || !page.items.length) {
      gridEl.appendChild(u.el('div', 'empty', 'Esta página está vacía.'));
      return;
    }

    page.items.forEach(function (item) {
      let node;
      if (item.kind === 'widget') {
        const widget = global.PD.widgets.create(item, handlers.widgetCtx);
        widgets.push(widget);
        node = widget.el;
      } else {
        node = createButton(item, handlers.onPress);
      }
      const w = Math.min(item.w || 1, cols);
      const h = item.h || 1;
      if (w > 1) node.style.gridColumn = 'span ' + w;
      if (h > 1) node.style.gridRow = 'span ' + h;
      gridEl.appendChild(node);
    });
    resizeWidgets();   // ya están en el DOM: se pueden medir
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
