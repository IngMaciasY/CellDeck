/*
 * PhoneDeck - aplicación principal del celular.
 *
 * Flujo: sesión (token) → config → render → WebSocket en vivo.
 * Si la sesión exige PIN (modo WiFi) se muestra el teclado de emparejamiento.
 */
(function (global) {
  'use strict';

  const PD = global.PD;
  const u = PD.util;
  const api = PD.api;
  const $ = u.$;

  const CONFIRM_MS = 3000;
  const FEEDBACK_MS = 700;
  const DANGEROUS_SYSTEM = ['shutdown', 'restart', 'logoff', 'hibernate'];

  const state = {
    info: null,          // respuesta de /api/session
    config: null,
    revision: null,
    pageId: u.store.get('page', null),
    snapshot: {},        // último mensaje en vivo por tipo (media, volume, stats)
    connection: null,
    started: false
  };

  // ------------------------------------------------------------ utilidades
  function setOverlay(visible, text, hint, showRetry) {
    u.show($('overlay'), visible);
    if (text) $('overlay-text').textContent = text;
    $('overlay-hint').textContent = hint || '';
    u.show($('overlay-retry'), !!showRetry);
  }

  function setConn(status) {
    const node = $('conn');
    node.className = 'conn conn-' + status;
    const labels = { online: 'Conectado', offline: 'Sin conexión', connecting: 'Conectando' };
    node.setAttribute('aria-label', labels[status] || status);
  }

  function applyTheme() {
    const local = u.store.get('theme', '');
    const fromConfig = state.config && state.config.appearance ? state.config.appearance.theme : 'dark';
    const theme = local || fromConfig || 'dark';
    document.documentElement.setAttribute('data-theme', theme);
    const accent = state.config && state.config.appearance && state.config.appearance.accent;
    if (accent) document.documentElement.style.setProperty('--accent', accent);
    const meta = document.querySelector('meta[name="theme-color"]');
    if (meta) meta.setAttribute('content', theme === 'light' ? '#ffffff' : theme === 'oled' ? '#000000' : '#1a1d24');
  }

  function currentPage() {
    const pages = state.config ? state.config.pages : [];
    for (let i = 0; i < pages.length; i++) {
      if (pages[i].id === state.pageId) return pages[i];
    }
    return pages[0] || null;
  }

  // ---------------------------------------------------------------- render
  function renderTabs() {
    const tabs = $('tabs');
    tabs.innerHTML = '';
    const page = currentPage();
    state.config.pages.forEach(function (p) {
      const tab = u.el('button', 'tab' + (page && p.id === page.id ? ' active' : ''));
      tab.type = 'button';
      tab.setAttribute('role', 'tab');
      tab.setAttribute('aria-selected', page && p.id === page.id ? 'true' : 'false');
      if (p.icon) tab.appendChild(PD.icons.icon(p.icon));
      tab.appendChild(u.el('span', '', p.name));
      tab.addEventListener('click', function () { goToPage(p.id); });
      tabs.appendChild(tab);
    });
    const active = tabs.querySelector('.tab.active');
    if (active && active.scrollIntoView) active.scrollIntoView({ block: 'nearest', inline: 'nearest' });
  }

  function renderPage() {
    const page = currentPage();
    if (page) state.pageId = page.id;
    const editing = !!PD.editor && PD.editor.isActive();
    PD.grid.render($('grid'), page, state.config.appearance, {
      onPress: onButtonPress,
      widgetCtx: { send: sendLive, snapshot: state.snapshot },
      edit: editing ? PD.editor.gridHandlers() : null
    });
  }

  function renderAll() {
    if (!state.config) return;
    applyTheme();
    renderTabs();
    renderPage();
  }

  function goToPage(pageId) {
    if (pageId === state.pageId) return;
    state.pageId = pageId;
    u.store.set('page', pageId);
    renderTabs();
    renderPage();
    $('page').scrollTop = 0;
  }

  function stepPage(delta) {
    const pages = state.config ? state.config.pages : [];
    if (pages.length < 2) return;
    const page = currentPage();
    const index = pages.indexOf(page);
    const next = pages[(index + delta + pages.length) % pages.length];
    goToPage(next.id);
  }

  function showConfigError(message) {
    const banner = $('banner');
    banner.textContent = message ? 'La config de la PC tiene errores; se usa la última válida. ' + message : '';
    u.show(banner, !!message);
  }

  function applyConfigPayload(payload) {
    state.config = payload.config;
    state.revision = payload.revision;
    showConfigError(payload.error);
    renderAll();
  }

  /** Config nueva desde la PC (WebSocket o al reconectar). */
  function receiveConfig(payload) {
    if (!payload || payload.revision === state.revision) return;
    if (PD.editor && PD.editor.isActive()) {
      // Mientras se edita no se pisa el borrador: se guarda la versión de la PC aparte.
      state.saved = payload.config;
      state.revision = payload.revision;
      showConfigError(payload.error);
      PD.editor.onRemoteConfig(payload);
      return;
    }
    applyConfigPayload(payload);
  }

  /** El editor muestra su borrador (draft) o vuelve a la config guardada (null). */
  function useConfig(draft) {
    if (draft) {
      if (!state.saved) state.saved = state.config;
      state.config = draft;
    } else if (state.saved) {
      state.config = state.saved;
      state.saved = null;
    }
    renderAll();
  }

  /** Tras guardar desde el editor. */
  function applySaved(payload) {
    state.saved = null;
    applyConfigPayload(payload);
  }

  function updateEditButton() {
    u.show($('btn-edit'), !!(state.info && state.info.can_edit));
  }

  // ------------------------------------------------------------- acciones
  function needsConfirmation(action) {
    if (!action) return false;
    if (action.type === 'system') return DANGEROUS_SYSTEM.indexOf(action.command) >= 0;
    if (action.type === 'macro') return (action.steps || []).some(needsConfirmation);
    return false;
  }

  function flash(btn, cls) {
    btn.classList.add(cls);
    setTimeout(function () { btn.classList.remove(cls); }, FEEDBACK_MS);
  }

  function enterConfirm(btn) {
    btn.classList.add('confirming');
    const label = btn.querySelector('.key-label');
    const original = label ? label.textContent : '';
    if (label) label.textContent = '¿Seguro?';
    btn._confirmTimer = setTimeout(function () {
      btn.classList.remove('confirming');
      if (label) label.textContent = original;
      btn._confirmTimer = null;
    }, CONFIRM_MS);
    btn._restoreLabel = function () {
      btn.classList.remove('confirming');
      if (label) label.textContent = original;
    };
  }

  async function onButtonPress(item, btn) {
    onUserGesture();
    u.vibrate(20);
    const page = currentPage();
    if (!page || btn.classList.contains('busy')) return;

    let confirmed = false;
    if (btn._confirmTimer) {
      clearTimeout(btn._confirmTimer);
      btn._confirmTimer = null;
      btn._restoreLabel();
      confirmed = true;
    } else if (item.confirm || needsConfirmation(item.action)) {
      enterConfirm(btn);
      return;
    }

    btn.classList.add('busy');
    try {
      const res = await api.run(page.id, item.id, confirmed);
      btn.classList.remove('busy');
      if (res.ok) {
        flash(btn, 'ok');
        if (res.message) u.toast(res.message, 'ok');
      } else {
        flash(btn, 'fail');
        u.toast(res.message || 'La acción falló', 'error');
      }
    } catch (err) {
      btn.classList.remove('busy');
      if (err.status === 428) {
        enterConfirm(btn);   // el servidor exige confirmación
        return;
      }
      flash(btn, 'fail');
      if (err.status !== 401) u.toast(err.message, 'error');
    }
  }

  /** Comandos en vivo de los widgets (volumen, multimedia) por WebSocket. */
  function sendLive(type, data) {
    return !!state.connection && state.connection.send(type, data);
  }

  // ------------------------------------------------------------ WebSocket
  function onLiveMessage(type, data) {
    if (type === 'config') {
      receiveConfig(data);
      return;
    }
    if (type === 'error') {
      u.toast((data && data.message) || 'Error en la PC', 'error');
      return;
    }
    if (type === 'hello') {
      if (data && state.info) state.info.can_edit = data.can_edit;
      updateEditButton();
      return;
    }
    if (type === 'media' || type === 'volume' || type === 'stats') {
      state.snapshot[type] = data;
      PD.grid.dispatch(type, data);
    }
  }

  function onConnState(status) {
    if (status === 'unauthorized') {
      handleUnauthorized();
      return;
    }
    setConn(status);
    if (status === 'online') {
      setOverlay(false);
      // Puede haber cambiado la config mientras estábamos desconectados.
      api.getConfig().then(receiveConfig, function () { /* se reintentará al reconectar */ });
    } else if (status === 'offline' && state.config) {
      setOverlay(true, 'Se perdió la conexión con la PC', reconnectHint(), true);
    }
  }

  function reconnectHint() {
    if (state.info && state.info.loopback) {
      return '¿Sigue conectado el cable? Ejecuta connect_usb.bat (o "Conectar USB" en la bandeja).';
    }
    return '¿Está PhoneDeck abierto en la PC y el celular en la misma red WiFi?';
  }

  // -------------------------------------------------------- emparejamiento
  let pin = '';

  function renderPinDots() {
    const dots = $('pin-dots');
    dots.innerHTML = '';
    for (let i = 0; i < 6; i++) dots.appendChild(u.el('span', 'pin-dot' + (i < pin.length ? ' filled' : '')));
  }

  function buildKeypad() {
    const pad = $('keypad');
    if (pad.children.length) return;
    ['1', '2', '3', '4', '5', '6', '7', '8', '9', '⌫', '0', 'OK'].forEach(function (k) {
      const b = u.el('button', k === 'OK' ? 'ok' : '', k);
      b.type = 'button';
      b.addEventListener('click', function () { onPinKey(k); });
      pad.appendChild(b);
    });
  }

  function onPinKey(key) {
    u.vibrate(10);
    $('pair-error').textContent = '';
    if (key === '⌫') pin = pin.slice(0, -1);
    else if (key === 'OK') submitPin();
    else if (pin.length < 6) pin += key;
    renderPinDots();
    if (pin.length === 6 && key !== 'OK') submitPin();
  }

  async function submitPin() {
    if (pin.length !== 6) return;
    const attempt = pin;
    try {
      const res = await api.pair(attempt, deviceName());
      u.store.set('token', res.token);
      api.setToken(res.token);
      pin = '';
      u.show($('pair'), false);
      start();
    } catch (err) {
      pin = '';
      renderPinDots();
      const dots = $('pin-dots');
      dots.classList.remove('error');
      void dots.offsetWidth;   // reinicia la animación
      dots.classList.add('error');
      $('pair-error').textContent = err.status === 403 ? 'PIN incorrecto' : err.message;
    }
  }

  function deviceName() {
    const m = /\(([^)]+)\)/.exec(navigator.userAgent);
    const parts = m ? m[1].split(';') : [];
    return (parts.length ? parts[parts.length - 1] : 'celular').replace(/Build.*/, '').trim().slice(0, 60) || 'celular';
  }

  function showPairing() {
    setOverlay(false);
    u.show($('app'), false);
    buildKeypad();
    pin = '';
    renderPinDots();
    u.show($('pair'), true);
  }

  function handleUnauthorized() {
    if (state.connection) state.connection.stop();
    u.store.remove('token');
    api.setToken(null);
    if (state.info && state.info.loopback) {
      start();   // en local basta con pedir otro token
    } else {
      showPairing();
    }
  }

  /** Emparejamiento automático con el PIN incluido en el QR (#pin=123456). */
  async function pairFromHash() {
    const m = /[#&]pin=(\d{6})/.exec(global.location.hash);
    if (!m) return;
    if (global.history && global.history.replaceState) {
      global.history.replaceState(null, '', global.location.pathname + global.location.search);
    }
    try {
      const res = await api.pair(m[1], deviceName());
      u.store.set('token', res.token);
    } catch (e) {
      u.toast('El PIN del QR no es válido: introdúcelo a mano', 'error');
    }
  }

  // --------------------------------------------- pantalla completa / sueño
  function fullscreenElement() {
    // Chrome 60 solo tiene la versión con prefijo; la estándar se usa si existe.
    // eslint-disable-next-line compat/compat
    return document.fullscreenElement || document.webkitFullscreenElement || null;
  }

  function toggleFullscreen() {
    const root = document.documentElement;
    if (fullscreenElement()) {
      if (document.exitFullscreen) document.exitFullscreen();
      else if (document.webkitExitFullscreen) document.webkitExitFullscreen();
      return;
    }
    const req = root.requestFullscreen || root.webkitRequestFullscreen;
    if (req) {
      try {
        const r = req.call(root);
        if (r && r.catch) r.catch(function () { /* el navegador lo rechazó */ });
      } catch (e) { /* no soportado */ }
    }
  }

  /** ¿Abierta como app instalada (pantalla de inicio)? Entonces sobra el botón. */
  function isStandalone() {
    const mm = global.matchMedia;
    return !!(navigator.standalone ||
      (mm && (mm('(display-mode: fullscreen)').matches || mm('(display-mode: standalone)').matches)));
  }

  /** iPhone no tiene API de pantalla completa: se oculta el botón donde no sirve. */
  function fullscreenSupported() {
    const root = document.documentElement;
    return !!(root.requestFullscreen || root.webkitRequestFullscreen) && !isStandalone();
  }

  function updateFullscreenIcon() {
    const btn = $('btn-fullscreen');
    u.show(btn, fullscreenSupported() || !!fullscreenElement());
    btn.innerHTML = '';
    btn.appendChild(PD.icons.icon(fullscreenElement() ? 'minimize' : 'maximize'));
  }

  let gestureHandled = false;

  /** El primer toque habilita lo que requiere gesto: NoSleep y pantalla completa. */
  function onUserGesture() {
    if (gestureHandled) return;
    gestureHandled = true;
    if (u.store.get('nosleep', true)) PD.nosleep.enable();
    if (u.store.get('autofs', false) && !fullscreenElement()) toggleFullscreen();
  }

  // ----------------------------------------------------------------- menú
  function openSheet() {
    const info = state.info || {};
    const box = $('sheet-info');
    box.innerHTML = '';
    const lines = [
      ['PhoneDeck', 'v' + (info.version || '?')],
      ['Conexión', info.loopback ? 'USB / local' : 'WiFi'],
      ['Servidor', global.location.host],
      ['Edición', info.can_edit ? 'permitida' : 'desactivada (se activa en la PC)']
    ];
    lines.forEach(function (l) {
      const row = u.el('div');
      row.appendChild(document.createTextNode(l[0] + ': '));
      row.appendChild(u.el('b', '', l[1]));
      box.appendChild(row);
    });
    $('opt-haptics').checked = u.store.get('haptics', true);
    $('opt-nosleep').checked = u.store.get('nosleep', true);
    $('opt-autofs').checked = u.store.get('autofs', false);
    $('opt-theme').value = u.store.get('theme', '');
    $('opt-size').value = String(u.store.get('btnsize', ''));
    updateColsInfo();
    u.show($('btn-forget'), !info.loopback);
    updateNoSleepHint();
    u.show($('sheet-backdrop'), true);
    u.show($('sheet'), true);
  }

  function closeSheet() {
    u.show($('sheet-backdrop'), false);
    u.show($('sheet'), false);
  }

  function updateColsInfo() {
    if (!state.config) return;
    const lay = PD.grid.effectiveLayout(state.config.appearance);
    const cols = PD.grid.columnsFor(state.config.appearance);
    $('cols-info').textContent = cols + ' columnas · ' + (lay.mode === 'fixed' ? 'fijas' : 'automáticas');
  }

  function updateNoSleepHint() {
    const hint = $('nosleep-hint');
    if (!u.store.get('nosleep', true)) {
      hint.textContent = '';
      return;
    }
    const method = PD.nosleep.method();
    hint.textContent = method === 'wakelock' ? 'Pantalla encendida (Wake Lock).'
      : method === 'video' ? 'Pantalla encendida (modo compatible). Si aun así se apaga, activa ' +
        '"Pantalla activa" en Opciones de desarrollador mientras carga.'
      : 'Toca cualquier botón para activar el modo pantalla encendida.';
  }

  function bindMenu() {
    $('btn-menu').appendChild(PD.icons.icon('menu'));
    $('btn-menu').addEventListener('click', function () { onUserGesture(); openSheet(); });
    $('sheet-backdrop').addEventListener('click', closeSheet);
    $('opt-haptics').addEventListener('change', function (e) { u.store.set('haptics', e.target.checked); });
    $('opt-nosleep').addEventListener('change', function (e) {
      u.store.set('nosleep', e.target.checked);
      if (e.target.checked) PD.nosleep.enable(); else PD.nosleep.disable();
      setTimeout(updateNoSleepHint, 300);
    });
    $('opt-autofs').addEventListener('change', function (e) { u.store.set('autofs', e.target.checked); });
    $('opt-theme').addEventListener('change', function (e) {
      u.store.set('theme', e.target.value);
      applyTheme();
    });
    $('opt-size').addEventListener('change', function (e) {
      // Preferencia solo de este celular: no cambia la config de la PC ni otros dispositivos.
      if (e.target.value) u.store.set('btnsize', e.target.value);
      else u.store.remove('btnsize');
      state.lastCols = PD.grid.columnsFor(state.config.appearance);
      renderPage();
      updateColsInfo();
    });
    $('btn-reload').addEventListener('click', function () { global.location.reload(); });
    $('btn-forget').addEventListener('click', function () {
      u.store.remove('token');
      global.location.reload();
    });
  }

  // ---------------------------------------------------------------- gestos
  function bindSwipe() {
    const page = $('page');
    let x0 = 0;
    let y0 = 0;
    let t0 = 0;
    let tracking = false;
    page.addEventListener('touchstart', function (e) {
      if (e.touches.length !== 1) { tracking = false; return; }
      // No interferir con sliders, asas de arrastre del editor ni ventanas modales.
      const t = e.target;
      tracking = !(t && (t.tagName === 'INPUT' || (t.closest && t.closest('.drag-handle, .modal'))));
      x0 = e.touches[0].clientX;
      y0 = e.touches[0].clientY;
      t0 = Date.now();
    }, { passive: true });
    page.addEventListener('touchend', function (e) {
      if (!tracking || (PD.editor && PD.editor.isDragging())) return;
      tracking = false;
      const t = e.changedTouches[0];
      const dx = t.clientX - x0;
      const dy = t.clientY - y0;
      if (Date.now() - t0 < 600 && Math.abs(dx) > 70 && Math.abs(dy) < 50) stepPage(dx < 0 ? 1 : -1);
    }, { passive: true });
  }

  // ---------------------------------------------------------------- arranque
  async function loadSession() {
    const saved = u.store.get('token', null);
    if (saved) api.setToken(saved);
    try {
      const info = await api.session();
      if (info.token) {
        api.setToken(info.token);   // local: token nuevo en cada carga
      }
      state.info = info;
      return 'ok';
    } catch (err) {
      if (err.status === 401) return 'pair';
      throw err;
    }
  }

  async function start() {
    setOverlay(true, 'Conectando con la PC…', '', false);
    let status;
    try {
      status = await loadSession();
    } catch (err) {
      setOverlay(true, 'No se pudo conectar con la PC', err.message + '. ' + reconnectHint(), true);
      return;
    }
    if (status === 'pair') {
      showPairing();
      return;
    }
    let payload;
    try {
      payload = await api.getConfig();
    } catch (err) {
      if (err.status === 401) return;   // onUnauthorized ya actúa
      setOverlay(true, 'No se pudo cargar la configuración', err.message, true);
      return;
    }
    // Primero se muestra (para que el grid tenga ancho) y luego se pinta.
    u.show($('app'), true);
    applyConfigPayload(payload);
    updateEditButton();
    state.lastCols = PD.grid.columnsFor(state.config.appearance);
    setOverlay(false);
    if (state.connection) state.connection.stop();
    state.connection = new PD.Connection(onLiveMessage, onConnState);
    state.connection.start(api.getToken());
  }

  function registerServiceWorker() {
    // Solo en contexto seguro (http://localhost por USB): permite "Añadir a pantalla de inicio".
    if (!('serviceWorker' in navigator) || !global.isSecureContext) return;
    navigator.serviceWorker.register('sw.js').catch(function () { /* opcional */ });
  }

  function init() {
    api.onUnauthorized(handleUnauthorized);
    PD.editor.init();
    bindMenu();
    bindSwipe();
    updateFullscreenIcon();
    $('btn-fullscreen').addEventListener('click', function () { onUserGesture(); toggleFullscreen(); });
    document.addEventListener('fullscreenchange', updateFullscreenIcon);
    document.addEventListener('webkitfullscreenchange', updateFullscreenIcon);
    document.addEventListener('click', onUserGesture, true);
    $('overlay-retry').addEventListener('click', function () {
      if (state.connection && state.config) state.connection.retryNow();
      else start();
    });

    const relayout = u.throttle(function () {
      if (!state.config) return;
      const cols = PD.grid.columnsFor(state.config.appearance);
      if (cols !== state.lastCols) {
        state.lastCols = cols;
        renderPage();   // cambian las columnas: se vuelve a pintar
      } else {
        PD.grid.layout($('grid'), state.config.appearance);
      }
    }, 150);
    global.addEventListener('resize', relayout);
    global.addEventListener('orientationchange', function () { setTimeout(relayout, 250); });

    document.addEventListener('visibilitychange', function () {
      if (document.visibilityState === 'visible' && state.connection) state.connection.retryNow();
    });

    registerServiceWorker();
    pairFromHash().then(start, start);
  }

  // API mínima para el editor visual (hito d) y para depurar desde la consola.
  PD.app = {
    state: state,
    renderAll: renderAll,
    goToPage: goToPage,
    showPairing: showPairing,
    reload: start,
    useConfig: useConfig,
    applySaved: applySaved
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})(window);
