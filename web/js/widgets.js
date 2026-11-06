/*
 * PhoneDeck - widgets: reloj, CPU/RAM, ahora suena y volumen.
 * Mezclador, Pomodoro y OBS viven en su propio archivo y se añaden con register().
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
  let dateCache = { day: -1, text: '' };

  function pad(n) { return (n < 10 ? '0' : '') + n; }

  /** La fecha larga (toLocaleDateString es costoso) se calcula una vez al día. */
  function dateText(now) {
    if (dateCache.day !== now.getDate()) {
      let text;
      try {
        text = now.toLocaleDateString('es', { weekday: 'long', day: 'numeric', month: 'long' });
        text = text.charAt(0).toUpperCase() + text.slice(1);   // solo la primera letra
      } catch (e) {
        text = now.toDateString();
      }
      dateCache = { day: now.getDate(), text: text };
    }
    return dateCache.text;
  }

  function tickClocks() {
    const now = new Date();
    const date = dateText(now);
    let anySeconds = false;
    clocks.forEach(function (c) {
      let time = pad(now.getHours()) + ':' + pad(now.getMinutes());
      if (c.seconds) {
        time += ':' + pad(now.getSeconds());
        anySeconds = true;
      }
      u.setText(c.time, time);
      u.setText(c.date, date);
    });
    scheduleClocks(now, anySeconds);
  }

  /**
   * Despierta justo en el cambio de minuto (o de segundo si algún reloj muestra segundos)
   * en vez de cada segundo: menos trabajo y la hora cambia en el instante exacto.
   */
  function scheduleClocks(now, everySecond) {
    clearTimeout(clockTimer);
    if (!clocks.length) {
      clockTimer = null;
      return;
    }
    const ms = now.getMilliseconds();
    const delay = everySecond ? 1000 - ms : (60 - now.getSeconds()) * 1000 - ms;
    clockTimer = setTimeout(tickClocks, delay + 20);
  }

  function createClock(item) {
    const el = u.el('div', 'widget w-clock');
    const entry = {
      time: el.appendChild(u.el('div', 'time', '--:--')),
      date: el.appendChild(u.el('div', 'date', '')),
      seconds: !!(item.options && item.options.seconds)
    };
    clocks.push(entry);
    tickClocks();   // pinta ya y reprograma el temporizador compartido
    return {
      el: el,
      update: function () {},
      destroy: function () {
        clocks.splice(clocks.indexOf(entry), 1);
        if (!clocks.length) {
          clearTimeout(clockTimer);
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
    let last = -1;
    return {
      root: root,
      set: function (percent, text) {
        const p = u.clamp(Math.round(percent), 0, 100);
        u.setText(value, text || (p + '%'));
        if (p === last) return;
        last = p;
        // transform (no width): la animación la hace la GPU sin recalcular la disposición.
        fill.style.transform = 'scaleX(' + (p / 100) + ')';
        const cls = 'meter-fill' + (p >= 90 ? ' critical' : p >= 70 ? ' high' : '');
        if (fill.className !== cls) fill.className = cls;
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
    let lastJson = '';
    let receivedAt = 0;
    let lastArt = null;
    let lastPlayIcon = '';
    let lastScale = '';
    let timer = null;

    function renderProgress() {
      let scale = 0;
      if (state && state.duration) {
        let pos = state.position || 0;
        if (state.status === 'playing') pos += (Date.now() - receivedAt) / 1000;
        scale = u.clamp(pos / state.duration, 0, 1);
      }
      const value = 'scaleX(' + scale.toFixed(4) + ')';
      if (value !== lastScale) {
        lastScale = value;
        fill.style.transform = value;
      }
    }

    /** El temporizador del progreso solo corre mientras suena algo con duración conocida. */
    function syncTimer() {
      const needed = !!(state && state.status === 'playing' && state.duration);
      if (needed && !timer) timer = setInterval(renderProgress, 1000);
      if (!needed && timer) {
        clearInterval(timer);
        timer = null;
      }
    }

    function update(type, data) {
      if (type !== 'media') return;
      const json = JSON.stringify(data);
      if (json === lastJson) return;   // mensaje repetido (p. ej. snapshot al resuscribirse)
      lastJson = json;
      state = data;
      receivedAt = Date.now();
      syncTimer();
      if (!data || (!data.title && !data.artist)) {
        u.setText(title, 'Nada sonando');
        u.setText(artist, '');
        art.style.backgroundImage = '';
        art.classList.remove('has-art');
        lastArt = null;
        el.classList.add('paused');
        renderProgress();
        return;
      }
      u.setText(title, data.title || 'Sin título');
      // Artista · app de origen (Spotify, Brave...): útil si suenan varias cosas.
      u.setText(artist, [data.artist, data.app].filter(Boolean).join(' · '));
      el.classList.toggle('paused', data.status !== 'playing');
      const url = safeArtworkUrl(data.artwork);
      if (url !== lastArt) {
        lastArt = url;
        art.style.backgroundImage = url ? 'url("' + url.replace(/"/g, '%22') + '")' : '';
        art.classList.toggle('has-art', !!url);
      }
      const playIcon = data.status === 'playing' ? 'pause' : 'play';
      if (playBtn && playIcon !== lastPlayIcon) {
        lastPlayIcon = playIcon;
        playBtn.innerHTML = '';
        playBtn.appendChild(icon(playIcon));
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
      destroy: function () { if (timer) clearInterval(timer); }
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

    let lastIcon = 'volume-2';

    /** Redibuja el icono solo si cambia (al arrastrar llegan decenas de eventos/s). */
    function setIcon(level) {
      const name = muted || level === 0 ? 'volume-x' : level < 50 ? 'volume-1' : 'volume-2';
      if (name === lastIcon) return;
      lastIcon = name;
      muteBtn.innerHTML = '';
      muteBtn.appendChild(icon(name));
    }

    slider.addEventListener('input', function () {
      dragging = true;
      clearTimeout(releaseTimer);
      const level = parseInt(slider.value, 10);
      u.setText(value, level + '%');
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
          if (slider.value !== String(data.level)) slider.value = String(data.level);
          u.setText(value, data.level + '%');
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

  function register(name, factory) { FACTORIES[name] = factory; }

  global.PD.widgets = { create: create, register: register };
})(window);
