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

  /** Número de columnas según orientación y configuración. */
  function columnsFor(appearance) {
    const a = appearance || {};
    return isPortrait() ? (a.columns_portrait || 3) : (a.columns_landscape || 6);
  }

  /** Ajusta el tamaño de celda para que los botones sean cuadrados. */
  function layout(gridEl, appearance) {
    const cols = columnsFor(appearance);
    const style = global.getComputedStyle(gridEl);
    const gap = parseFloat(style.getPropertyValue('--gap')) || 10;
    // Si aún no está en pantalla (ancho 0) se estima con la ventana.
    const width = gridEl.clientWidth || (global.innerWidth - 2 * gap);
    let cell = Math.floor((width - gap * (cols - 1)) / cols);
    // En horizontal se limita para que quepan al menos 3 filas sin desplazarse.
    if (!isPortrait()) {
      const page = gridEl.parentNode;
      const maxCell = Math.floor((page.clientHeight - gap * 4) / 3);
      if (maxCell > 60) cell = Math.min(cell, maxCell);
    }
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

  global.PD.grid = { render: render, layout: layout, dispatch: dispatch, columnsFor: columnsFor };
})(window);
