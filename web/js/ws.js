/*
 * CellDeck - conexión WebSocket con reconexión exponencial.
 * El servidor envía {type, data}: hello, config y los temas en vivo.
 */
(function (global) {
  'use strict';

  const MIN_DELAY = 1000;
  const MAX_DELAY = 10000;
  const PING_MS = 25000;

  /**
   * @param {function(string, *)} onMessage  mensaje recibido (tipo, datos)
   * @param {function(string)} onState  'connecting' | 'online' | 'offline' | 'unauthorized'
   */
  function Connection(onMessage, onState) {
    this.onMessage = onMessage;
    this.onState = onState;
    this.socket = null;
    this.token = null;
    this.delay = MIN_DELAY;
    this.retryTimer = null;
    this.pingTimer = null;
    this.stopped = true;
  }

  Connection.prototype.start = function (token) {
    this.token = token;
    this.stopped = false;
    this.delay = MIN_DELAY;
    this._open();
  };

  Connection.prototype.stop = function () {
    this.stopped = true;
    clearTimeout(this.retryTimer);
    clearInterval(this.pingTimer);
    if (this.socket) {
      this.socket.onclose = null;
      this.socket.close();
      this.socket = null;
    }
  };

  /** Reintento inmediato (botón "Reintentar" o al volver la pestaña a primer plano). */
  Connection.prototype.retryNow = function () {
    if (this.stopped || this.isOpen()) return;
    clearTimeout(this.retryTimer);
    this.delay = MIN_DELAY;
    this._open();
  };

  Connection.prototype.isOpen = function () {
    return !!this.socket && this.socket.readyState === WebSocket.OPEN;
  };

  Connection.prototype.send = function (type, data) {
    if (!this.isOpen()) return false;
    const msg = { type: type };
    if (data) {
      Object.keys(data).forEach(function (k) { msg[k] = data[k]; });
    }
    this.socket.send(JSON.stringify(msg));
    return true;
  };

  Connection.prototype._open = function () {
    const self = this;
    if (self.socket) {
      self.socket.onclose = null;
      try { self.socket.close(); } catch (e) { /* ya cerrado */ }
    }
    self.onState('connecting');
    const proto = global.location.protocol === 'https:' ? 'wss://' : 'ws://';
    const url = proto + global.location.host + '/ws?token=' + encodeURIComponent(self.token || '');
    let socket;
    try {
      socket = new WebSocket(url);
    } catch (e) {
      self._scheduleRetry();
      return;
    }
    self.socket = socket;

    socket.onopen = function () {
      self.delay = MIN_DELAY;
      self.onState('online');
      clearInterval(self.pingTimer);
      self.pingTimer = setInterval(function () { self.send('ping'); }, PING_MS);
    };
    socket.onmessage = function (event) {
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch (e) {
        return;
      }
      if (msg && typeof msg.type === 'string') self.onMessage(msg.type, msg.data);
    };
    socket.onclose = function (event) {
      clearInterval(self.pingTimer);
      self.socket = null;
      if (self.stopped) return;
      if (event.code === 4401) {
        self.stopped = true;
        self.onState('unauthorized');
        return;
      }
      self.onState('offline');
      self._scheduleRetry();
    };
  };

  Connection.prototype._scheduleRetry = function () {
    const self = this;
    clearTimeout(self.retryTimer);
    // Pequeña aleatoriedad para no sincronizar reintentos de varios clientes.
    const wait = self.delay + Math.floor(Math.random() * 300);
    self.retryTimer = setTimeout(function () { self._open(); }, wait);
    self.delay = Math.min(MAX_DELAY, self.delay * 2);
  };

  global.PD = global.PD || {};
  global.PD.Connection = Connection;
})(window);
