/*
 * PhoneDeck - iconos SVG (24x24, trazo). Locales: la app funciona sin Internet.
 * Estilo inspirado en Lucide (https://lucide.dev, licencia ISC); ver web/icons/LICENSE.txt.
 * El nombre del icono solo se usa como clave del diccionario: nunca se inyecta en el HTML.
 */
(function (global) {
  'use strict';

  const SPEAKER = '<polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>';
  const MONITOR = '<rect x="2" y="3" width="20" height="14" rx="2"/><path d="M8 21h8M12 17v4"/>';
  const MIC = '<rect x="9" y="2" width="6" height="12" rx="3"/><path d="M5 10v1a7 7 0 0 0 14 0v-1M12 18v4"/>';

  const ICONS = {
    'activity': '<polyline points="22 12 18 12 15 21 9 3 6 12 2 12"/>',
    'bell': '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.7 21a2 2 0 0 1-3.4 0"/>',
    'calendar': '<rect x="3" y="4" width="18" height="18" rx="2"/><path d="M16 2v4M8 2v4M3 10h18"/>',
    'camera': '<path d="M3 8a2 2 0 0 1 2-2h2l2-3h6l2 3h2a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/><circle cx="12" cy="13" r="4"/>',
    'check': '<polyline points="20 6 9 17 4 12"/>',
    'chevron-down': '<polyline points="6 9 12 15 18 9"/>',
    'chevron-left': '<polyline points="15 18 9 12 15 6"/>',
    'chevron-right': '<polyline points="9 18 15 12 9 6"/>',
    'chevron-up': '<polyline points="18 15 12 9 6 15"/>',
    'clock': '<circle cx="12" cy="12" r="10"/><polyline points="12 6 12 12 16 14"/>',
    'code': '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    'coffee': '<path d="M17 8h1a4 4 0 0 1 0 8h-1"/><path d="M3 8h14v9a4 4 0 0 1-4 4H7a4 4 0 0 1-4-4z"/><path d="M6 2v3M10 2v3M14 2v3"/>',
    'copy': '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
    'cpu': '<rect x="5" y="5" width="14" height="14" rx="2"/><rect x="9" y="9" width="6" height="6"/><path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3"/>',
    'download': '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="7 10 12 15 17 10"/><path d="M12 15V3"/>',
    'file-text': '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><polyline points="14 2 14 8 20 8"/><path d="M8 13h8M8 17h6"/>',
    'folder': '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
    'gamepad': '<rect x="2" y="7" width="20" height="10" rx="5"/><path d="M6 12h4M8 10v4"/><path d="M15 11h.01M18 13h.01"/>',
    'globe': '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20a15 15 0 0 1 0-20z"/>',
    'grip': '<path d="M9 5h.01M15 5h.01M9 12h.01M15 12h.01M9 19h.01M15 19h.01" stroke-width="3.2"/>',
    'headphones': '<path d="M3 18v-6a9 9 0 0 1 18 0v6"/><path d="M21 19a2 2 0 0 1-2 2h-1v-6h3zM3 19a2 2 0 0 0 2 2h1v-6H3z"/>',
    'heart': '<path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21.2l8.8-8.8a5.5 5.5 0 0 0 0-7.8z"/>',
    'home': '<path d="M3 10l9-7 9 7v10a1 1 0 0 1-1 1h-5v-6H9v6H4a1 1 0 0 1-1-1z"/>',
    'image': '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><polyline points="21 15 16 10 5 21"/>',
    'keyboard': '<rect x="2" y="6" width="20" height="12" rx="2"/><path d="M6 10h.01M10 10h.01M14 10h.01M18 10h.01M7 14h10"/>',
    'layout': '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 9h18M9 21V9"/>',
    'link': '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
    'lock': '<rect x="4" y="11" width="16" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/>',
    'log-out': '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><polyline points="16 17 21 12 16 7"/><path d="M21 12H9"/>',
    'mail': '<rect x="2" y="4" width="20" height="16" rx="2"/><polyline points="22 6 12 13 2 6"/>',
    'maximize': '<path d="M8 3H5a2 2 0 0 0-2 2v3M21 8V5a2 2 0 0 0-2-2h-3M3 16v3a2 2 0 0 0 2 2h3M16 21h3a2 2 0 0 0 2-2v-3"/>',
    'menu': '<path d="M3 6h18M3 12h18M3 18h18"/>',
    'message': '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
    'mic': MIC,
    'mic-off': MIC + '<path d="M2 2l20 20"/>',
    'minimize': '<path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3"/>',
    'monitor': MONITOR,
    'monitor-off': MONITOR + '<path d="M2 2l20 20"/>',
    'moon': '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
    'music': '<path d="M9 18V5l12-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="18" cy="16" r="3"/>',
    'pause': '<rect x="6" y="4" width="4" height="16" rx="1"/><rect x="14" y="4" width="4" height="16" rx="1"/>',
    'pencil': '<path d="M17 3l4 4L8 20H4v-4z"/>',
    'play': '<polygon points="6 3 20 12 6 21 6 3"/>',
    'play-pause': '<polygon points="3 5 11 12 3 19 3 5"/><path d="M15 5v14M20 5v14"/>',
    'plus': '<path d="M12 5v14M5 12h14"/>',
    'power': '<path d="M18.4 6.6a9 9 0 1 1-12.8 0"/><path d="M12 2v10"/>',
    'record': '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="4"/>',
    'refresh': '<polyline points="23 4 23 10 17 10"/><path d="M20.5 15a9 9 0 1 1-2.1-9.4L23 10"/>',
    'search': '<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.4-4.4"/>',
    'skip-back': '<polygon points="19 20 9 12 19 4 19 20"/><path d="M5 19V5"/>',
    'skip-forward': '<polygon points="5 4 15 12 5 20 5 4"/><path d="M19 5v14"/>',
    'sliders': '<path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6"/>',
    'square': '<rect x="4" y="4" width="16" height="16" rx="3"/>',
    'star': '<polygon points="12 2 15.1 8.3 22 9.3 17 14.1 18.2 21 12 17.8 5.8 21 7 14.1 2 9.3 8.9 8.3 12 2"/>',
    'stop': '<rect x="5" y="5" width="14" height="14" rx="2"/>',
    'sun': '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    'terminal': '<polyline points="4 17 10 11 4 5"/><path d="M12 19h8"/>',
    'trash': '<path d="M3 6h18M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6M10 11v6M14 11v6M9 6V4h6v2"/>',
    'usb': '<circle cx="12" cy="20" r="2"/><path d="M12 18V3M9 6l3-3 3 3M12 14l-4-2V9M12 12l4-2V8"/>',
    'timer': '<circle cx="12" cy="14" r="8"/><path d="M12 10v4l2 2M9 2h6"/>',
    'video': '<rect x="2" y="6" width="14" height="12" rx="2"/><polygon points="22 8 16 12 22 16 22 8"/>',
    'volume-1': SPEAKER + '<path d="M15.5 8.5a5 5 0 0 1 0 7"/>',
    'volume-2': SPEAKER + '<path d="M15.5 8.5a5 5 0 0 1 0 7M19 5a10 10 0 0 1 0 14"/>',
    'volume-x': SPEAKER + '<path d="M22 9l-6 6M16 9l6 6"/>',
    'wifi': '<path d="M5 12.5a10 10 0 0 1 14 0M8.5 16a5 5 0 0 1 7 0M2 9a15 15 0 0 1 20 0M12 20h.01"/>',
    'x': '<path d="M18 6L6 18M6 6l12 12"/>',
    'zap': '<polygon points="13 2 3 14 12 14 11 22 21 10 12 10 13 2"/>'
  };

  /** Devuelve un <svg class="icon"> listo para insertar. Icono desconocido → cuadrado. */
  function icon(name, extraClass) {
    const body = Object.prototype.hasOwnProperty.call(ICONS, name) ? ICONS[name] : ICONS.square;
    const wrap = document.createElement('div');
    wrap.innerHTML = '<svg class="icon' + (extraClass ? ' ' + extraClass : '') +
      '" viewBox="0 0 24 24" aria-hidden="true">' + body + '</svg>';
    return wrap.firstChild;
  }

  global.PD = global.PD || {};
  global.PD.icons = {
    icon: icon,
    names: Object.keys(ICONS).sort()
  };
})(window);
