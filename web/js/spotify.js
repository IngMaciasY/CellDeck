/*
 * PhoneDeck - Spotify: biblioteca, búsqueda y control de la música de la PC.
 * El celular nunca habla con Spotify: la PC hace de puente (ver src/phonedeck/spotify.py).
 *
 * Pestañas: Inicio (recientes), Playlists, Me gusta, Álbumes y Buscar. Tocar la barra de
 * reproducción abre "Reproduciendo", con la barra para moverse dentro de la canción.
 * Tocar una canción la reproduce; mantenerla pulsada la añade a la cola.
 *
 * Lo cargado vive fuera del widget porque girar el celular repinta la página y lo recrea.
 * Los textos que vienen de Spotify siempre se insertan como texto.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const api = global.PD.api;
  const icon = global.PD.icons.icon;

  const STALE_MS = 5 * 60 * 1000;
  const RECENT_STALE_MS = 60 * 1000;
  const HOLD_MS = 550;
  const MAX_PLAY_URIS = 50;   // límite del puente: cabe en un mensaje del WebSocket
  const NEEDS_ACCOUNT = ['unconfigured', 'unlinked', 'expired'];
  const DASHBOARD = 'developer.spotify.com/dashboard';
  const TABS = [['home', 'Inicio'], ['playlists', 'Playlists'], ['liked', 'Me gusta'],
    ['albums', 'Álbumes'], ['search', 'Buscar']];

  /** Origen de cada lista: función(offset) → promesa de página. */
  const SOURCES = {
    recent: function () { return api.spotifyRecent(); },
    queue: function () { return api.spotifyQueue(); },
    playlists: function (offset) { return api.spotifyPlaylists(offset); },
    liked: function (offset) { return api.spotifyLiked(offset); },
    albums: function (offset) { return api.spotifyAlbums(offset); }
  };

  function newView() {
    return {
      tab: 'home',
      lists: {},
      detail: null,      // { kind: 'playlist' | 'album', item }
      nowPlaying: false,
      query: '',
      draft: '',
      results: null,
      searching: false,
      searchError: '',
      scroll: {},
      createdAt: Date.now()
    };
  }

  let view = newView();
  const painters = [];
  let painting = false;   // una carga que empieza al pintar no vuelve a pintar todo

  function repaint() {
    if (painting) return;
    painters.forEach(function (paint) { paint(); });
  }

  function list(key) {
    if (!view.lists[key]) {
      view.lists[key] = { items: null, next: null, loading: false, error: '', available: true,
        loadedAt: 0 };
    }
    return view.lists[key];
  }

  function detailKey(detail) {
    return detail.kind + ':' + detail.item.id;
  }

  function sourceFor(key) {
    if (SOURCES[key]) return SOURCES[key];
    const parts = key.split(':');
    return parts[0] === 'album'
      ? function (offset) { return api.spotifyAlbumTracks(parts[1], offset); }
      : function (offset) { return api.spotifyTracks(parts[1], offset); };
  }

  /** Carga una página de una lista. Una respuesta de una vista ya descartada no se pinta. */
  function load(key, offset) {
    const current = view;
    const target = list(key);
    if (target.loading) return;
    target.loading = true;
    target.error = '';
    repaint();
    sourceFor(key)(offset).then(function (page) {
      if (page.available === false) target.available = false;
      target.items = (offset ? target.items : []).concat(page.items);
      target.next = page.next_offset;
      target.loadedAt = Date.now();
    }, function (err) {
      target.error = err.message;
    }).then(function () {
      target.loading = false;
      if (current !== view) return;
      if (target.again) {
        target.again = false;
        load(key, 0);
        return;
      }
      repaint();
    });
  }

  /** Vuelve a pedir una lista ya; si está cargando, al terminar (su dato ya es viejo). */
  function refresh(key) {
    const target = list(key);
    if (target.loading) target.again = true;
    else load(key, 0);
  }

  function ensure(key, maxAge) {
    const target = list(key);
    const old = maxAge && target.loadedAt && Date.now() - target.loadedAt > maxAge;
    if ((!target.items || old) && !target.loading && !target.error) load(key, 0);
  }

  function search(text) {
    const current = view;
    view.query = text;
    view.searching = true;
    view.searchError = '';
    repaint();
    api.spotifySearch(text).then(function (found) {
      if (current === view && current.query === text) current.results = found;
    }, function (err) {
      if (current === view && current.query === text) current.searchError = err.message;
    }).then(function () {
      if (current !== view || current.query !== text) return;
      current.searching = false;
      repaint();
    });
  }

  // --------------------------------------------------------------- piezas
  function cover(key, className) {
    const box = u.el('span', 'sp-cover ' + className);
    box.appendChild(icon('music'));
    if (key) {
      const img = document.createElement('img');
      img.alt = '';
      img.setAttribute('loading', 'lazy');
      img.addEventListener('error', function () { img.remove(); });
      img.src = api.spotifyImage(key);
      box.appendChild(img);
    }
    return box;
  }

  function button(className, text, onClick) {
    const btn = u.el('button', className, text);
    btn.type = 'button';
    btn.addEventListener('click', onClick);
    return btn;
  }

  function textBlock(title, meta) {
    const box = u.el('span', 'sp-text');
    box.appendChild(u.el('span', 'sp-name', title));
    if (meta) box.appendChild(u.el('span', 'sp-meta', meta));
    return box;
  }

  function countText(total) {
    if (total === null || total === undefined) return '';
    return total + (total === 1 ? ' canción' : ' canciones');
  }

  function playlistMeta(playlist) {
    const parts = [];
    const count = countText(playlist.total);
    if (count) parts.push(count);
    if (playlist.owner) parts.push(playlist.owner);
    if (playlist.collaborative) parts.push('Colaborativa');
    else if (playlist.public === true) parts.push('Pública');
    else if (playlist.public === false) parts.push('Privada');
    return parts.join(' · ');
  }

  function albumMeta(album) {
    return [album.artists, countText(album.total)].filter(Boolean).join(' · ');
  }

  function loadingRow() {
    const box = u.el('div', 'sp-loading');
    box.appendChild(u.el('div', 'spinner'));
    return box;
  }

  function message(text) {
    return u.el('p', 'sp-message', text);
  }

  function failure(text, retry) {
    const box = u.el('div', 'sp-message');
    box.appendChild(u.el('p', '', text));
    box.appendChild(button('btn', 'Reintentar', retry));
    return box;
  }

  function sectionTitle(text) {
    return u.el('h3', 'sp-section', text);
  }

  function formatTime(ms) {
    const total = Math.max(0, Math.floor(ms / 1000));
    const seconds = total % 60;
    return Math.floor(total / 60) + ':' + (seconds < 10 ? '0' : '') + seconds;
  }

  /**
   * Toque normal y pulsación larga. En Android una pulsación larga también dispara
   * "contextmenu" y a veces un click: la marca de tiempo evita hacer dos cosas.
   */
  function pressable(row, onTap, onHold) {
    let timer = null;
    let touching = false;
    let held = false;   // tras una pulsación larga se ignora el click que la siga
    function cancel() {
      clearTimeout(timer);
      timer = null;
    }
    function hold() {
      if (held) return;
      held = true;
      u.vibrate(30);
      onHold();
    }
    // Solo un toque nuevo reinicia: tras soltar, Android puede emitir mousedown y click
    // sintéticos, y esos no deben reproducir lo que se acaba de añadir a la cola.
    row.addEventListener('touchstart', function () {
      cancel();
      held = false;
      touching = true;
      timer = setTimeout(function () { timer = null; hold(); }, HOLD_MS);
    }, { passive: true });
    row.addEventListener('touchmove', cancel, { passive: true });
    row.addEventListener('touchend', function () {
      cancel();
      touching = false;
    });
    row.addEventListener('touchcancel', function () {
      cancel();
      touching = false;
    });
    row.addEventListener('contextmenu', function (e) {
      e.preventDefault();
      if (touching) {   // Android: la misma pulsación larga
        cancel();
        hold();
      } else {          // clic derecho con ratón: no hay click detrás que ignorar
        u.vibrate(30);
        onHold();
      }
    });
    row.addEventListener('click', function () {
      if (held) {
        held = false;
        return;
      }
      onTap();
    });
  }

  // ------------------------------------------------------ cuenta (solo local)
  function field(form, label, input) {
    const row = form.appendChild(u.el('label', 'sp-field'));
    row.appendChild(u.el('span', '', label));
    row.appendChild(input);
    return input;
  }

  function createAccount() {
    const box = u.el('details', 'sp-account');
    box.appendChild(u.el('summary', '', 'Cuenta de Spotify'));
    const form = box.appendChild(u.el('div', 'sp-form'));

    const steps = form.appendChild(u.el('ol', 'sp-steps'));
    steps.appendChild(u.el('li', '', 'Entra a ' + DASHBOARD + ' con una cuenta Premium y crea una app.'));
    steps.appendChild(u.el('li', '', 'En "Redirect URIs" pega esta dirección y marca "Web API":'));
    const redirect = document.createElement('input');
    redirect.className = 'sp-copy';
    redirect.readOnly = true;
    redirect.setAttribute('aria-label', 'Dirección para Spotify');
    redirect.addEventListener('click', function () { redirect.select(); });
    steps.lastChild.appendChild(redirect);
    steps.appendChild(u.el('li', '', 'Guarda, copia el Client ID de la app y pégalo aquí.'));

    const clientId = document.createElement('input');
    clientId.type = 'text';
    clientId.maxLength = 32;
    clientId.autocomplete = 'off';
    clientId.spellcheck = false;
    field(form, 'Client ID', clientId);

    const actions = form.appendChild(u.el('div', 'sp-actions'));
    const link = actions.appendChild(button('btn btn-primary', 'Vincular cuenta', onLink));
    const unlink = actions.appendChild(button('btn', 'Desvincular', onUnlink));

    function fill(data) {
      redirect.value = data.redirect_uri;
      clientId.value = data.client_id;
      link.textContent = data.linked ? 'Volver a vincular' : 'Vincular cuenta';
      u.show(unlink, data.linked);
    }

    function failed(err) {
      link.disabled = false;
      u.toast(err.status === 422 ? 'Revisa el Client ID: son 32 caracteres' : err.message, 'error');
    }

    /** Guarda el Client ID y abre Spotify: al aceptar, Spotify devuelve a esta misma app. */
    function onLink() {
      link.disabled = true;
      api.saveSpotifySettings({ client_id: clientId.value.trim() })
        .then(function () { return api.spotifyLogin(); })
        .then(function (res) { global.location.href = res.url; }, failed);
    }

    function onUnlink() {
      api.spotifyUnlink().then(function (data) {
        fill(data);
        u.toast('Cuenta desvinculada', 'ok');
      }, failed);
    }

    box.addEventListener('toggle', function () {
      if (box.open) api.spotifySettings().then(fill, failed);
    });

    return box;
  }

  // --------------------------------------------------------------- widget
  function createSpotify(item, ctx) {
    const el = u.el('div', 'widget w-spotify');
    const head = el.appendChild(u.el('div', 'sp-head'));
    ['white', 'black'].forEach(function (color) {
      const logo = document.createElement('img');
      logo.className = 'sp-logo sp-logo-' + color;
      logo.alt = 'Spotify';
      logo.src = 'icons/spotify-logo-' + color + '.svg';
      head.appendChild(logo);
    });
    const user = head.appendChild(u.el('span', 'sp-user'));
    const tabs = el.appendChild(u.el('div', 'sp-tabs'));
    tabs.setAttribute('role', 'tablist');
    const notice = el.appendChild(u.el('p', 'sp-notice hidden'));
    notice.setAttribute('role', 'status');
    const body = el.appendChild(u.el('div', 'sp-body'));
    const content = body.appendChild(u.el('div'));
    const info = global.PD.app && global.PD.app.state.info;
    const local = !!(info && info.loopback);
    const account = local ? body.appendChild(createAccount()) : null;

    const player = el.appendChild(u.el('div', 'sp-player hidden'));
    const opener = player.appendChild(u.el('button', 'sp-player-open'));
    opener.type = 'button';
    opener.setAttribute('aria-label', 'Abrir Reproduciendo');
    const playerCover = opener.appendChild(u.el('span', 'sp-player-cover'));
    const playerTitle = opener.appendChild(u.el('span', 'sp-text'));
    const title = playerTitle.appendChild(u.el('span', 'sp-name'));
    const subtitle = playerTitle.appendChild(u.el('span', 'sp-meta'));
    const controls = player.appendChild(u.el('span', 'sp-controls'));

    let data = { status: 'connecting', message: 'Conectando con Spotify…', user: null, player: null,
      relink: false };
    let progressAt = Date.now();
    let coverKey;
    let accountOpened = false;
    let seekBar = null;   // la barra de "Reproduciendo", mientras está a la vista
    let clock = null;

    function send(type, payload) {
      u.vibrate(15);
      if (!ctx.send(type, payload)) {
        u.toast('Sin conexión con la PC', 'error');
        return false;
      }
      return true;
    }

    function queueSong(track) {
      if (track.uri && send('spotify.queue', { uri: track.uri })) u.toast('Añadida a la cola', 'ok');
    }

    function controlButton(name, label, action, main) {
      const btn = u.el('button', 'icon-btn' + (main ? ' main' : ''));
      btn.type = 'button';
      btn.setAttribute('aria-label', label);
      btn.appendChild(icon(name));
      btn.addEventListener('click', function () {
        const playing = data.player && data.player.playing;
        const command = action === 'toggle' ? (playing ? 'pause' : 'play') : action;
        send('spotify.control', { action: command });
      });
      return btn;
    }

    function toggleIcon(btn) {
      const playing = !!(data.player && data.player.playing);
      btn.innerHTML = '';
      btn.appendChild(icon(playing ? 'pause' : 'play'));
      btn.setAttribute('aria-label', playing ? 'Pausar' : 'Reproducir');
    }

    controls.appendChild(controlButton('skip-back', 'Anterior', 'previous'));
    const toggle = controls.appendChild(controlButton('play', 'Reproducir', 'toggle', true));
    controls.appendChild(controlButton('skip-forward', 'Siguiente', 'next'));
    opener.addEventListener('click', function () {
      view.nowPlaying = true;
      view.queueWanted = true;
      paint();
      body.scrollTop = 0;
    });

    // ------------------------------------------------ progreso de la canción
    /** Posición estimada: la PC la manda cada 5 s y entre medias se cuenta aquí. */
    function position() {
      const now = data.player;
      if (!now) return 0;
      const extra = now.playing ? Date.now() - progressAt : 0;
      return Math.min(now.duration_ms || 0, (now.progress_ms || 0) + extra);
    }

    function tick() {
      if (!seekBar || seekBar.dragging || !data.player) return;
      const pos = position();
      seekBar.input.value = String(pos);
      u.setText(seekBar.elapsed, formatTime(pos));
      u.setText(seekBar.total, formatTime(data.player.duration_ms || 0));
    }

    function stopClock() {
      clearInterval(clock);
      clock = null;
    }

    function renderPlayer() {
      const now = data.player;
      u.show(player, !!now && !view.nowPlaying);
      if (!now) return;
      u.setText(title, now.title);
      u.setText(subtitle, [now.artists, now.device].filter(Boolean).join(' · '));
      if (now.image !== coverKey) {
        coverKey = now.image;
        playerCover.innerHTML = '';
        playerCover.appendChild(cover(now.image, 'sp-cover-small'));
      }
      toggleIcon(toggle);
    }

    /** Marca la canción que suena en las listas visibles, sin repintarlas. */
    function markPlaying() {
      const uri = data.player && data.player.uri;
      const rows = content.querySelectorAll('[data-uri]');
      for (let i = 0; i < rows.length; i++) {
        rows[i].classList.toggle('playing', !!uri && rows[i].getAttribute('data-uri') === uri);
      }
    }

    // --------------------------------------------------------------- filas
    /** Fila de canción. ``play`` es lo que se manda al tocarla. */
    function trackRow(track, play, number) {
      const row = u.el('button', 'sp-row sp-track');
      row.type = 'button';
      row.disabled = !track.uri;
      if (track.uri) row.setAttribute('data-uri', track.uri);
      if (number) row.appendChild(u.el('span', 'sp-num', String(number)));
      else row.appendChild(cover(track.image, 'sp-cover-small'));
      row.appendChild(textBlock(track.title, track.artists));
      pressable(row, function () {
        if (!track.uri) return;
        if (play) send('spotify.play', play);
        else send('spotify.skip', { count: Number(row.getAttribute('data-skip')) });
      }, function () { queueSong(track); });
      return row;
    }

    function trackList(tracks, playFor, numbered) {
      tracks.forEach(function (track, index) {
        content.appendChild(trackRow(track, playFor(track, index), numbered ? index + 1 : 0));
      });
    }

    /** Las canciones desde la tocada en adelante: así sigue sonando el resto (Me gusta). */
    function followingFrom(tracks, index) {
      const uris = [];
      for (let i = index; i < tracks.length && uris.length < MAX_PLAY_URIS; i++) {
        if (tracks[i].uri) uris.push(tracks[i].uri);
      }
      return uris;
    }

    function openDetail(kind, entry) {
      view.scroll[view.tab] = body.scrollTop;
      view.detail = { kind: kind, item: entry };
      repaint();
      body.scrollTop = 0;
    }

    function collectionRow(kind, entry) {
      const row = u.el('button', 'sp-row');
      row.type = 'button';
      row.appendChild(cover(entry.image, 'sp-cover-medium'));
      const meta = kind === 'album' ? albumMeta(entry) : playlistMeta(entry);
      const text = row.appendChild(textBlock(entry.name, meta));
      if (kind === 'playlist' && !entry.readable) {
        text.appendChild(u.el('span', 'sp-tag', 'Solo reproducir'));
      }
      row.appendChild(icon('chevron-right'));
      row.addEventListener('click', function () { openDetail(kind, entry); });
      return row;
    }

    /** Pie de una lista paginada: cargando, error con reintento o "Cargar más". */
    function listFooter(key, target) {
      if (target.loading) content.appendChild(loadingRow());
      else if (target.error) {
        content.appendChild(failure(target.error, function () { load(key, target.next || 0); }));
      } else if (target.next !== null) {
        content.appendChild(button('btn sp-more', 'Cargar más', function () { load(key, target.next); }));
      }
    }

    // -------------------------------------------------------------- vistas
    function renderHome() {
      const recent = list('recent');
      content.appendChild(sectionTitle('Escuchado recientemente'));
      if (recent.items) {
        trackList(recent.items, function (track) {
          return track.context ? { context: track.context, track: track.uri } : { track: track.uri };
        });
        if (!recent.items.length && !recent.loading) {
          content.appendChild(message('Aún no hay nada reciente.'));
        }
      }
      listFooter('recent', recent);
    }

    function renderCollections(key, kind, emptyText) {
      const target = list(key);
      (target.items || []).forEach(function (entry) {
        content.appendChild(collectionRow(kind, entry));
      });
      if (target.items && !target.items.length && !target.loading) {
        content.appendChild(message(emptyText));
      }
      listFooter(key, target);
    }

    function renderLiked() {
      const target = list('liked');
      if (target.items) {
        trackList(target.items, function (track, index) {
          return { uris: followingFrom(target.items, index) };
        });
        if (!target.items.length && !target.loading) {
          content.appendChild(message('Aún no guardaste canciones.'));
        }
      }
      listFooter('liked', target);
    }

    function renderSearch() {
      const form = content.appendChild(u.el('form', 'sp-search'));
      const input = form.appendChild(document.createElement('input'));
      input.type = 'search';
      input.className = 'sp-query';
      input.placeholder = 'Canciones, álbumes o playlists';
      input.maxLength = 100;
      input.value = view.draft;
      input.addEventListener('input', function () { view.draft = input.value; });
      input.setAttribute('aria-label', 'Buscar en Spotify');
      input.setAttribute('enterkeyhint', 'search');
      const go = form.appendChild(u.el('button', 'icon-btn'));
      go.type = 'submit';
      go.setAttribute('aria-label', 'Buscar');
      go.appendChild(icon('search'));
      form.addEventListener('submit', function (e) {
        e.preventDefault();
        const text = input.value.trim();
        if (!text) return;
        input.blur();
        search(text);
      });

      if (view.searching) {
        content.appendChild(loadingRow());
        return;
      }
      if (view.searchError) {
        content.appendChild(failure(view.searchError, function () { search(view.query); }));
        return;
      }
      const found = view.results;
      if (!found) {
        content.appendChild(message('Busca cualquier canción para reproducirla en la PC.'));
        return;
      }
      if (!found.tracks.length && !found.albums.length && !found.playlists.length) {
        content.appendChild(message('Sin resultados para "' + view.query + '".'));
        return;
      }
      if (found.tracks.length) {
        content.appendChild(sectionTitle('Canciones'));
        trackList(found.tracks, function (track) {
          return track.album_uri ? { context: track.album_uri, track: track.uri } : { track: track.uri };
        });
      }
      if (found.albums.length) {
        content.appendChild(sectionTitle('Álbumes'));
        found.albums.forEach(function (album) { content.appendChild(collectionRow('album', album)); });
      }
      if (found.playlists.length) {
        content.appendChild(sectionTitle('Playlists'));
        found.playlists.forEach(function (pl) { content.appendChild(collectionRow('playlist', pl)); });
      }
    }

    function renderDetail() {
      const detail = view.detail;
      const entry = detail.item;
      const back = content.appendChild(button('sp-back', '', function () {
        view.detail = null;
        repaint();
        body.scrollTop = view.scroll[view.tab] || 0;
      }));
      back.appendChild(icon('chevron-left'));
      back.appendChild(u.el('span', '', 'Atrás'));

      const top = content.appendChild(u.el('div', 'sp-detail'));
      top.appendChild(cover(entry.image, 'sp-cover-large'));
      const text = top.appendChild(u.el('div', 'sp-detail-text'));
      text.appendChild(u.el('h3', 'sp-title', entry.name));
      const meta = detail.kind === 'album' ? albumMeta(entry) : playlistMeta(entry);
      text.appendChild(u.el('p', 'sp-meta', meta));
      if (entry.description) text.appendChild(u.el('p', 'sp-meta', entry.description));

      const actions = content.appendChild(u.el('div', 'sp-actions'));
      actions.appendChild(button('btn btn-primary', 'Reproducir en la PC', function () {
        send('spotify.play', { context: entry.uri });
      }));
      actions.appendChild(button('btn', 'ABRIR SPOTIFY', function () {
        send('spotify.open', { uri: entry.uri });
      }));

      if (detail.kind === 'playlist' && !entry.readable) {
        content.appendChild(message('Spotify solo comparte las canciones de las playlists que ' +
          'creaste o en las que colaboras. Esta se puede reproducir o abrir en la PC; para ' +
          'elegir una canción concreta, búscala en la pestaña Buscar.'));
        return;
      }
      const key = detailKey(detail);
      const target = list(key);
      if (!target.available) {
        content.appendChild(message('Spotify no entregó sus canciones.'));
        return;
      }
      if (target.items) {
        trackList(target.items, function (track) {
          return { context: entry.uri, track: track.uri };
        }, detail.kind === 'album');
        if (!target.items.length && !target.loading) content.appendChild(message('No tiene canciones.'));
      }
      listFooter(key, target);
    }

    function renderNowPlaying() {
      const now = data.player;
      const box = content.appendChild(u.el('div', 'sp-now'));
      const close = box.appendChild(button('sp-back', '', function () {
        view.nowPlaying = false;
        paint();
      }));
      close.appendChild(icon('chevron-down'));
      close.appendChild(u.el('span', '', 'Reproduciendo'));
      if (!now) {
        box.appendChild(message('No suena nada. Elige una canción o abre Spotify en la PC.'));
        return;
      }
      // En horizontal, portada a la izquierda y controles a la derecha (ver CSS).
      const main = box.appendChild(u.el('div', 'sp-now-main'));
      main.appendChild(cover(now.image, 'sp-cover-xl'));
      const side = main.appendChild(u.el('div', 'sp-now-side'));
      side.appendChild(u.el('h3', 'sp-title sp-now-title', now.title));
      side.appendChild(u.el('p', 'sp-meta sp-now-meta', now.artists));
      if (now.device) side.appendChild(u.el('p', 'sp-meta sp-now-meta', 'En ' + now.device));

      const seek = side.appendChild(u.el('div', 'sp-seek'));
      const input = seek.appendChild(document.createElement('input'));
      input.type = 'range';
      input.min = '0';
      input.max = String(now.duration_ms || 0);
      input.step = '1000';
      input.disabled = !now.duration_ms;
      input.setAttribute('aria-label', 'Posición en la canción');
      const times = seek.appendChild(u.el('div', 'sp-times'));
      seekBar = {
        input: input,
        elapsed: times.appendChild(u.el('span', '', '0:00')),
        total: times.appendChild(u.el('span', '', formatTime(now.duration_ms || 0))),
        dragging: false,
        toggle: null
      };
      input.addEventListener('input', function () {
        seekBar.dragging = true;
        u.setText(seekBar.elapsed, formatTime(Number(input.value)));
      });
      input.addEventListener('change', function () {
        const target = Math.round(Number(input.value));
        seekBar.dragging = false;
        if (send('spotify.seek', { position_ms: target }) && data.player) {
          data.player.progress_ms = target;   // sin esperar a que la PC lo confirme
          data.player.progress_age_ms = 0;
          progressAt = Date.now();
        }
      });

      const big = side.appendChild(u.el('div', 'sp-now-controls'));
      big.appendChild(controlButton('skip-back', 'Anterior', 'previous'));
      seekBar.toggle = big.appendChild(controlButton('play', 'Reproducir', 'toggle', true));
      toggleIcon(seekBar.toggle);
      big.appendChild(controlButton('skip-forward', 'Siguiente', 'next'));

      const queue = list('queue');
      content.appendChild(sectionTitle('A continuación'));
      if (queue.items) {
        // Saltar con "siguiente" conserva el resto de la cola; reproducirla la borraría.
        queue.items.forEach(function (track, index) {
          const row = content.appendChild(trackRow(track, null, 0));
          row.setAttribute('data-skip', String(index + 1));
        });
        if (!queue.items.length && !queue.loading) content.appendChild(message('La cola está vacía.'));
      }
      listFooter('queue', queue);
      tick();
      clock = setInterval(tick, 1000);
    }

    function renderTabs(visible) {
      tabs.innerHTML = '';
      u.show(tabs, visible);
      if (!visible) return;
      TABS.forEach(function (tab) {
        const active = view.tab === tab[0];
        const chip = u.el('button', 'sp-chip' + (active ? ' active' : ''), tab[1]);
        chip.type = 'button';
        chip.setAttribute('role', 'tab');
        chip.setAttribute('aria-selected', active ? 'true' : 'false');
        chip.addEventListener('click', function () {
          if (active && !view.detail) return;
          if (!view.detail) view.scroll[view.tab] = body.scrollTop;
          view.tab = tab[0];
          view.detail = null;
          paint();
          body.scrollTop = view.scroll[view.tab] || 0;
        });
        tabs.appendChild(chip);
      });
    }

    function renderAccountHint() {
      content.appendChild(message(local
        ? 'Vincula tu cuenta para ver tu música.'
        : 'Abre PhoneDeck en la PC (icono de la bandeja → Abrir panel) para vincular tu cuenta.'));
      if (local && !accountOpened) {
        accountOpened = true;
        account.open = true;
      }
    }

    /** Pide lo que la vista va a mostrar. Se llama antes de pintarla. */
    function loadVisible() {
      if (data.status !== 'online') return;
      if (view.nowPlaying) {
        if (view.queueWanted) {
          view.queueWanted = false;   // al abrir, la cola siempre se pide de nuevo
          refresh('queue');
        }
      } else if (view.detail) {
        if (view.detail.kind === 'album' || view.detail.item.readable) ensure(detailKey(view.detail));
      } else if (view.tab === 'home') ensure('recent', RECENT_STALE_MS);
      else if (SOURCES[view.tab]) ensure(view.tab);
    }

    function noticeText(needsAccount, online) {
      if (data.status === 'expired') return data.message;
      if (needsAccount) return '';
      if (!online) return data.message;
      if (data.relink) {
        return local
          ? 'Vuelve a vincular la cuenta (abajo, en Cuenta de Spotify) para usar Inicio, Me gusta y Álbumes.'
          : 'Vuelve a vincular la cuenta desde la PC para usar Inicio, Me gusta y Álbumes.';
      }
      return '';
    }

    function paint() {
      painting = true;
      try {
        loadVisible();
        draw();
      } finally {
        painting = false;
      }
    }

    function draw() {
      const top = body.scrollTop;
      const searching = document.activeElement && document.activeElement.className === 'sp-query';
      content.innerHTML = '';
      seekBar = null;
      stopClock();
      const needsAccount = NEEDS_ACCOUNT.indexOf(data.status) >= 0;
      const online = data.status === 'online';
      const text = noticeText(needsAccount, online);
      u.setText(user, data.user || '');
      u.setText(notice, text);
      u.show(notice, !!text);
      renderTabs(!needsAccount && !view.nowPlaying);
      renderPlayer();
      if (needsAccount) renderAccountHint();
      else if (view.nowPlaying) renderNowPlaying();
      else if (view.detail) renderDetail();
      else if (!online && !Object.keys(view.lists).length) {
        if (data.status === 'connecting') content.appendChild(loadingRow());
      } else if (view.tab === 'home') renderHome();
      else if (view.tab === 'playlists') {
        renderCollections('playlists', 'playlist', 'Tu cuenta no tiene playlists.');
      } else if (view.tab === 'liked') renderLiked();
      else if (view.tab === 'albums') renderCollections('albums', 'album', 'Aún no guardaste álbumes.');
      else renderSearch();
      // La cuenta se gestiona al final de Playlists (o cuando hace falta vincular).
      const showAccount = needsAccount || data.relink || (view.tab === 'playlists' && !view.detail);
      u.show(account, showAccount && !view.nowPlaying);
      body.scrollTop = top;
      markPlaying();
      // Repintar mientras se escribe no debe cerrar el teclado.
      const query = searching && content.querySelector('.sp-query');
      if (query) {
        query.focus();
        query.setSelectionRange(query.value.length, query.value.length);
      }
    }

    function update(type, incoming) {
      if (type !== 'spotify' || !incoming) return;
      const before = data;
      data = incoming;
      // La posición se leyó hace progress_age_ms (al suscribirse puede tener segundos).
      progressAt = Date.now() - ((data.player && data.player.progress_age_ms) || 0);
      if (NEEDS_ACCOUNT.indexOf(data.status) >= 0 && Object.keys(view.lists).length) view = newView();
      const changed = ['status', 'user', 'message', 'relink'].some(function (key) {
        return before[key] !== data[key];
      });
      const beforeUri = before.player && before.player.uri;
      const nowUri = data.player && data.player.uri;
      if (changed) {
        paint();
        return;
      }
      if (view.nowPlaying && (beforeUri !== nowUri || !before.player !== !data.player)) {
        // Cambió la canción: la vista y la cola, que ya avanzó, se vuelven a pedir.
        refresh('queue');
        paint();
        return;
      }
      renderPlayer();
      if (seekBar && data.player) {
        if (!seekBar.dragging) seekBar.input.max = String(data.player.duration_ms || 0);
        toggleIcon(seekBar.toggle);
        tick();
      }
      if (beforeUri !== nowUri) markPlaying();
    }

    /**
     * Sola en su página, la sección mide justo el alto visible: la lista se desplaza por
     * dentro y el reproductor queda siempre a la vista. Las filas del grid son para botones.
     */
    function fitPage() {
      const grid = el.parentNode;
      if (!grid || grid.children.length !== 1) {
        el.style.height = '';
        return;
      }
      const page = grid.parentNode;
      const bottom = parseFloat(global.getComputedStyle(page).paddingBottom) || 0;
      const top = grid.getBoundingClientRect().top - page.getBoundingClientRect().top;
      el.style.gridRow = 'auto';
      el.style.height = (page.clientHeight - top - bottom) + 'px';
    }

    if (Date.now() - view.createdAt > STALE_MS && !view.nowPlaying) view = newView();
    let pendingScroll = view.scroll.current || 0;
    painters.push(paint);
    paint();

    return {
      el: el,
      update: update,
      resize: function () {
        fitPage();
        if (!pendingScroll) return;
        body.scrollTop = pendingScroll;
        pendingScroll = 0;
      },
      destroy: function () {
        view.scroll.current = body.scrollTop;
        stopClock();
        painters.splice(painters.indexOf(paint), 1);
      }
    };
  }

  global.PD.widgets.register('spotify', createSpotify);
})(window);
