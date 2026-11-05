/*
 * PhoneDeck - widgets: reloj, CPU/RAM, ahora suena y volumen.
 *
 * Cada widget: { el, update(type, data), destroy() }.
 * Los datos en vivo llegan por WebSocket (mensajes "media", "volume", "stats").
 * Los controles de los widgets solo envían comandos acotados (volumen 0-100,
 * teclas multimedia): nunca acciones arbitrarias.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const icon = global.PD.icons.icon;

  // ----------------------------------------------------------------- reloj
  const clocks = [];
  let clockTimer = null;

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  function tickClocks() {
    const now = new Date();
    let date;
    try {
      date = now.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
      date = date.charAt(0).toUpperCase() + date.slice(1);   // solo la primera letra
    } catch (e) {
      date = now.toDateString();
    }
    clocks.forEach(function (c) {
      let time = pad(now.getHours()) + ':' + pad(now.getMinutes());
      if (c.seconds) time += ':' + pad(now.getSeconds());
      c.time.textContent = time;
      c.date.textContent = date;
    });
  }

  function createClock(item) {
    const el = u.el('div', 'widget w-clock');
    const entry = {
      time: el.appendChild(u.el('div', 'time', '--:--')),
      date: el.appendChild(u.el('div', 'date', '')),
      seconds: !!(item.options && item.options.seconds)
    };
    clocks.push(entry);
    if (!clockTimer) clockTimer = setInterval(tickClocks, 1000);
    tickClocks();
    return {
      el: el,
      update: function () {},
      destroy: function () {
        clocks.splice(clocks.indexOf(entry), 1);
        if (!clocks.length) {
          clearInterval(clockTimer);
          clockTimer = null;
        }
      }
    };
  }

  // ----------------------------------------------------------------- stats
  function meter(label) {
    const root = u.el('div', 'meter');
    const head = root.appendChild(u.el('div', 'meter-head'));
    head.appendChild(u.el('span', '', label));
    const value = head.appendChild(u.el('span', 'muted', '—'));
    const bar = root.appendChild(u.el('div', 'meter-bar'));
    const fill = bar.appendChild(u.el('div', 'meter-fill'));
    return {
      root: root,
      set: function (percent, text) {
        const p = u.clamp(Math.round(percent), 0, 100);
        fill.style.width = p + '%';
        fill.className = 'meter-fill' + (p >= 90 ? ' critical' : p >= 70 ? ' high' : '');
        value.textContent = text || (p + '%');
      }
    };
  }

  function createStats() {
    const el = u.el('div', 'widget w-stats');
    const cpu = meter('CPU');
    const ram = meter('RAM');
    el.appendChild(cpu.root);
    el.appendChild(ram.root);
    return {
      el: el,
      update: function (type, data) {
        if (type !== 'stats' || !data) return;
        cpu.set(data.cpu);
        const ramText = data.ram_total
          ? Math.round(data.ram) + '% · ' + data.ram_used.toFixed(1) + '/' + data.ram_total.toFixed(1) + ' GB'
          : null;
        ram.set(data.ram, ramText);
      },
      destroy: function () {}
    };
  }

  // ----------------------------------------------------------- ahora suena
  function safeArtworkUrl(url) {
    // Solo se aceptan URLs de nuestra propia API.
    if (typeof url !== 'string' || url.indexOf('/api/media/artwork') !== 0) return null;
    const token = global.PD.api.getToken();
    return url + (url.indexOf('?') >= 0 ? '&' : '?') + 'token=' + encodeURIComponent(token || '');
  }

  function createNowPlaying(item, ctx) {
    const el = u.el('div', 'widget w-media');
    const art = el.appendChild(u.el('div', 'art'));
    art.appendChild(icon('music'));
    const info = el.appendChild(u.el('div', 'info'));
    const title = info.appendChild(u.el('div', 'title', 'Nada sonando'));
    const artist = info.appendChild(u.el('div', 'artist', ''));
    const progress = info.appendChild(u.el('div', 'progress'));
    const fill = progress.appendChild(u.el('div', 'progress-fill'));
    const showControls = item.h >= 2 && !(item.options && item.options.controls === false);
    let playBtn = null;

    if (showControls) {
      const controls = info.appendChild(u.el('div', 'controls'));
      [['prev', 'skip-back'], ['play_pause', 'play'], ['next', 'skip-forward']].forEach(function (pair) {
        const btn = u.el('button', 'icon-btn' + (pair[0] === 'play_pause' ? ' main' : ''));
        btn.type = 'button';
        btn.setAttribute('aria-label', pair[0]);
        btn.appendChild(icon(pair[1]));
        btn.addEventListener('click', function () {
          u.vibrate(15);
          if (!ctx.send('media', { command: pair[0] })) u.toast('Sin conexión con la PC', 'error');
        });
        controls.appendChild(btn);
        if (pair[0] === 'play_pause') playBtn = btn;
      });
    }

    let state = null;
    let receivedAt = 0;
    let lastArt = null;
    const timer = setInterval(renderProgress, 1000);

    function renderProgress() {
      if (!state || !state.duration) {
        fill.style.width = '0';
        return;
      }
      let pos = state.position || 0;
      if (state.status === 'playing') pos += (Date.now() - receivedAt) / 1000;
      fill.style.width = u.clamp(pos / state.duration * 100, 0, 100) + '%';
    }

    function update(type, data) {
      if (type !== 'media') return;
      state = data;
      receivedAt = Date.now();
      if (!data || (!data.title && !data.artist)) {
        title.textContent = 'Nada sonando';
        artist.textContent = '';
        art.style.backgroundImage = '';
        art.classList.remove('has-art');
        lastArt = null;
        el.classList.add('paused');
        renderProgress();
        return;
      }
      title.textContent = data.title || 'Sin título';
      // Artista · app de origen (Spotify, Brave...): útil si suenan varias cosas.
      artist.textContent = [data.artist, data.app].filter(Boolean).join(' · ');
      el.classList.toggle('paused', data.status !== 'playing');
      const url = safeArtworkUrl(data.artwork);
      if (url !== lastArt) {
        lastArt = url;
        art.style.backgroundImage = url ? 'url("' + url.replace(/"/g, '%22') + '")' : '';
        art.classList.toggle('has-art', !!url);
      }
      if (playBtn) {
        playBtn.innerHTML = '';
        playBtn.appendChild(icon(data.status === 'playing' ? 'pause' : 'play'));
      }
      renderProgress();
    }

    /** Portada cuadrada (sin aspect-ratio en Chrome 60): se calcula con el tamaño real. */
    function resize() {
      const size = Math.floor(Math.min(el.clientHeight - 20, el.clientWidth * 0.42));
      if (size > 0) {
        art.style.width = size + 'px';
        art.style.height = size + 'px';
      }
    }

    return {
      el: el,
      update: update,
      resize: resize,
      destroy: function () { clearInterval(timer); }
    };
  }

  // ---------------------------------------------------------------- volumen
  function createVolume(item, ctx) {
    const el = u.el('div', 'widget w-volume');
    const muteBtn = el.appendChild(u.el('button', 'icon-btn'));
    muteBtn.type = 'button';
    muteBtn.setAttribute('aria-label', 'Silenciar');
    muteBtn.appendChild(icon('volume-2'));
    const slider = el.appendChild(document.createElement('input'));
    slider.type = 'range';
    slider.min = '0';
    slider.max = '100';
    slider.step = '1';
    slider.value = '0';
    slider.setAttribute('aria-label', 'Volumen');
    const value = el.appendChild(u.el('span', 'value', '—'));

    let muted = false;
    let dragging = false;
    let releaseTimer = null;

    const sendLevel = u.throttle(function (level) {
      ctx.send('volume.set', { value: level });
    }, 80);

    function setIcon(level) {
      muteBtn.innerHTML = '';
      muteBtn.appendChild(icon(muted || level === 0 ? 'volume-x' : level < 50 ? 'volume-1' : 'volume-2'));
    }

    slider.addEventListener('input', function () {
      dragging = true;
      clearTimeout(releaseTimer);
      const level = parseInt(slider.value, 10);
      value.textContent = level + '%';
      setIcon(level);
      sendLevel(level);
    });
    slider.addEventListener('change', function () {
      // Tras soltar, se ignoran un momento los ecos del servidor para que no "salte".
      releaseTimer = setTimeout(function () { dragging = false; }, 700);
    });
    muteBtn.addEventListener('click', function () {
      u.vibrate(15);
      if (!ctx.send('volume.mute', { muted: !muted })) u.toast('Sin conexión con la PC', 'error');
    });

    return {
      el: el,
      update: function (type, data) {
        if (type !== 'volume' || !data) return;
        muted = !!data.muted;
        el.classList.toggle('muted', muted);
        if (!dragging) {
          slider.value = String(data.level);
          value.textContent = data.level + '%';
        }
        setIcon(parseInt(slider.value, 10));
      },
      destroy: function () { clearTimeout(releaseTimer); }
    };
  }

  const FACTORIES = {
    clock: createClock,
    stats: createStats,
    now_playing: createNowPlaying,
    volume: createVolume
  };

  /**
   * Crea un widget. ctx = { send(type, data) -> bool, snapshot: {tipo: datos} }.
   */
  function create(item, ctx) {
    const factory = FACTORIES[item.widget];
    if (!factory) {
      const el = u.el('div', 'widget', 'Widget desconocido: ' + item.widget);
      return { el: el, update: function () {}, destroy: function () {} };
    }
    const widget = factory(item, ctx);
    if (item.color) widget.el.style.background = item.color;
    // Pinta el último estado conocido sin esperar al siguiente mensaje.
    Object.keys(ctx.snapshot || {}).forEach(function (type) {
      widget.update(type, ctx.snapshot[type]);
    });
    return widget;
  }

  global.PD.widgets = { create: create, types: Object.keys(FACTORIES) };
})(window);
