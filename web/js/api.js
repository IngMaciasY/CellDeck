/*
 * PhoneDeck - cliente HTTP de la API.
 * Todas las peticiones llevan la cabecera X-PhoneDeck-Token (protección CSRF).
 */
(function (global) {
  'use strict';

  const TIMEOUT_MS = 8000;
  let token = null;
  let onUnauthorized = null;

  /** Error con el código HTTP y el detalle devuelto por el servidor. */
  function ApiError(status, detail) {
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
    this.message = typeof detail === 'string' ? detail
      : (detail && detail.message) ? detail.message
      : status === 0 ? 'Sin conexión con la PC' : 'Error ' + status;
  }
  ApiError.prototype = Object.create(Error.prototype);

  /** fetch con tiempo máximo (Chrome 60 no tiene AbortController). */
  function fetchWithTimeout(url, options, ms) {
    return new Promise(function (resolve, reject) {
      const timer = setTimeout(function () {
        reject(new ApiError(0, 'La PC no responde'));
      }, ms);
      fetch(url, options).then(function (res) {
        clearTimeout(timer);
        resolve(res);
      }, function () {
        clearTimeout(timer);
        reject(new ApiError(0, 'Sin conexión con la PC'));
      });
    });
  }

  async function request(method, path, body) {
    const headers = { 'Accept': 'application/json' };
    if (token) headers['X-PhoneDeck-Token'] = token;
    const options = { method: method, headers: headers, cache: 'no-store' };
    if (body !== undefined) {
      headers['Content-Type'] = 'application/json';
      options.body = JSON.stringify(body);
    }
    const res = await fetchWithTimeout(path, options, TIMEOUT_MS);
    const data = await res.json().catch(function () { return null; });
    if (!res.ok) {
      const detail = data && data.detail !== undefined ? data.detail : null;
      const err = new ApiError(res.status, detail);
      if (res.status === 401 && onUnauthorized && path !== '/api/session' && path !== '/api/pair') {
        onUnauthorized(err);
      }
      throw err;
    }
    return data;
  }

  global.PD = global.PD || {};
  global.PD.api = {
    ApiError: ApiError,
    setToken: function (value) { token = value; },
    getToken: function () { return token; },
    onUnauthorized: function (fn) { onUnauthorized = fn; },
    session: function () { return request('GET', '/api/session'); },
    pair: function (pin, device) { return request('POST', '/api/pair', { pin: pin, device: device }); },
    getConfig: function () { return request('GET', '/api/config'); },
    saveConfig: function (revision, config) {
      return request('PUT', '/api/config', { revision: revision, config: config });
    },
    run: function (page, item, confirmed) {
      return request('POST', '/api/run', { page: page, item: item, confirmed: !!confirmed });
    },
    plugins: function () { return request('GET', '/api/plugins'); }
  };
})(window);
