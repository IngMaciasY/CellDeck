/*
 * PhoneDeck - Spotify: playlists y control de la reproducción en la PC.
 * El celular nunca habla con Spotify: la PC hace de puente (ver src/phonedeck/spotify.py).
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
  const NEEDS_ACCOUNT = ['unconfigured', 'unlinked', 'expired'];
  const DASHBOARD = 'developer.spotify.com/dashboard';

  function newView() {
    return {
      playlists: null,
      next: null,
      loading: false,
      error: '',
      loadedAt: 0,
      selected: null,
      tracks: null,
      tracksNext: null,
      tracksLoading: false,
      tracksError: '',
      available: true,
      scrollTop: 0,
      listScroll: 0
    };
  }

  let view = newView();
  const painters = [];

  function repaint() {
    painters.forEach(function (paint) { paint(); });
  }

  function loadPlaylists(offset) {
    const current = view;
    if (current.loading) return;
    current.loading = true;
    current.error = '';
    repaint();
    api.spotifyPlaylists(offset).then(function (page) {
      current.playlists = (offset ? current.playlists : []).concat(page.items);
      current.next = page.next_offset;
      current.loadedAt = Date.now();
    }, function (err) {
      current.error = err.message;
    }).then(function () {
      current.loading = false;
      if (current === view) repaint();
    });
  }

  function loadTracks(offset) {
    const current = view;
    const playlist = current.selected;
    if (current.tracksLoading) return;
    current.tracksLoading = true;
    current.tracksError = '';
    repaint();
    api.spotifyTracks(playlist.id, offset).then(function (page) {
      if (current.selected !== playlist) return;
      current.available = page.available;
      current.tracks = (offset ? current.tracks : []).concat(page.items);
      current.tracksNext = page.next_offset;
    }, function (err) {
      if (current.selected === playlist) current.tracksError = err.message;
    }).then(function () {
      if (current.selected !== playlist) return;   // ya se abrió otra: su carga sigue en marcha
      current.tracksLoading = false;
      if (current === view) repaint();
    });
  }

  function select(playlist) {
    view.selected = playlist;
    view.tracks = null;
    view.tracksNext = null;
    view.tracksError = '';
    view.available = playlist.readable;
    view.tracksLoading = false;
    if (playlist.readable) loadTracks(0);
    else repaint();
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

  function playlistMeta(playlist) {
    const parts = [];
    if (playlist.total !== null) {
      parts.push(playlist.total + (playlist.total === 1 ? ' canción' : ' canciones'));
    }
    if (playlist.owner) parts.push(playlist.owner);
    if (playlist.collaborative) parts.push('Colaborativa');
    else if (playlist.public === true) parts.push('Pública');
    else if (playlist.public === false) parts.push('Privada');
    return parts.join(' · ');
  }

  function textBlock(title, meta) {
    const box = u.el('span', 'sp-text');
    box.appendChild(u.el('span', 'sp-name', title));
    if (meta) box.appendChild(u.el('span', 'sp-meta', meta));
    return box;
  }

  function loadingRow() {
    const box = u.el('div', 'sp-loading');
    box.appendChild(u.el('div', 'spinner'));
    return box;
  }

  function failure(message, retry) {
    const box = u.el('div', 'sp-message');
    box.appendChild(u.el('p', '', message));
    box.appendChild(button('btn', 'Reintentar', retry));
    return box;
  }

  function moreButton(onClick) {
    return button('btn sp-more', 'Cargar más', onClick);
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
    const notice = el.appendChild(u.el('p', 'sp-notice hidden'));
    notice.setAttribute('role', 'status');
    const body = el.appendChild(u.el('div', 'sp-body'));
    const content = body.appendChild(u.el('div'));
    const info = global.PD.app && global.PD.app.state.info;
    const local = !!(info && info.loopback);
    const account = local ? body.appendChild(createAccount()) : null;

    const player = el.appendChild(u.el('div', 'sp-player hidden'));
    const playerCover = player.appendChild(u.el('span', 'sp-player-cover'));
    const playerTitle = player.appendChild(u.el('span', 'sp-text'));
    const title = playerTitle.appendChild(u.el('span', 'sp-name'));
    const subtitle = playerTitle.appendChild(u.el('span', 'sp-meta'));
    const controls = player.appendChild(u.el('span', 'sp-controls'));

    let data = { status: 'connecting', message: 'Conectando con Spotify…', user: null, player: null };
    let coverKey;
    let accountOpened = false;
    let pendingScroll = view.scrollTop;

    function send(type, message) {
      u.vibrate(15);
      if (!ctx.send(type, message)) u.toast('Sin conexión con la PC', 'error');
    }

    function control(name, label) {
      const btn = u.el('button', 'icon-btn');
      btn.type = 'button';
      btn.setAttribute('aria-label', label);
      btn.appendChild(icon(name));
      return btn;
    }

    controls.appendChild(control('skip-back', 'Anterior')).addEventListener('click', function () {
      send('spotify.control', { action: 'previous' });
    });
    const toggle = controls.appendChild(control('play', 'Reproducir'));
    toggle.classList.add('main');
    toggle.addEventListener('click', function () {
      send('spotify.control', { action: data.player && data.player.playing ? 'pause' : 'play' });
    });
    controls.appendChild(control('skip-forward', 'Siguiente')).addEventListener('click', function () {
      send('spotify.control', { action: 'next' });
    });

    function renderPlayer() {
      const now = data.player;
      u.show(player, !!now);
      if (!now) return;
      u.setText(title, now.title);
      u.setText(subtitle, [now.artists, now.device].filter(Boolean).join(' · '));
      if (now.image !== coverKey) {
        coverKey = now.image;
        playerCover.innerHTML = '';
        playerCover.appendChild(cover(now.image, 'sp-cover-small'));
      }
      toggle.innerHTML = '';
      toggle.appendChild(icon(now.playing ? 'pause' : 'play'));
      toggle.setAttribute('aria-label', now.playing ? 'Pausar' : 'Reproducir');
    }

    function renderRow(playlist) {
      const row = u.el('button', 'sp-row');
      row.type = 'button';
      row.appendChild(cover(playlist.image, 'sp-cover-medium'));
      row.appendChild(textBlock(playlist.name, playlistMeta(playlist)));
      row.appendChild(icon('chevron-right'));
      row.addEventListener('click', function () {
        view.listScroll = body.scrollTop;
        body.scrollTop = 0;
        select(playlist);
      });
      return row;
    }

    function renderList() {
      if (view.playlists) {
        view.playlists.forEach(function (playlist) { content.appendChild(renderRow(playlist)); });
        if (!view.playlists.length && !view.loading) {
          content.appendChild(u.el('p', 'sp-message', 'Tu cuenta no tiene playlists.'));
        }
      }
      if (view.loading) content.appendChild(loadingRow());
      else if (view.error) {
        content.appendChild(failure(view.error, function () { loadPlaylists(view.next || 0); }));
      } else if (view.next !== null) {
        content.appendChild(moreButton(function () { loadPlaylists(view.next); }));
      }
    }

    function renderTrack(track, playlist) {
      const row = u.el('button', 'sp-row sp-track');
      row.type = 'button';
      row.disabled = !track.uri;
      row.appendChild(cover(track.image, 'sp-cover-small'));
      row.appendChild(textBlock(track.title, track.artists));
      row.addEventListener('click', function () {
        send('spotify.play', { context: playlist.uri, track: track.uri });
      });
      return row;
    }

    function renderDetail() {
      const playlist = view.selected;
      const back = content.appendChild(button('sp-back', '', function () {
        view.selected = null;
        repaint();
        body.scrollTop = view.listScroll;
      }));
      back.appendChild(icon('chevron-left'));
      back.appendChild(u.el('span', '', 'Playlists'));

      const top = content.appendChild(u.el('div', 'sp-detail'));
      top.appendChild(cover(playlist.image, 'sp-cover-large'));
      const text = top.appendChild(u.el('div', 'sp-detail-text'));
      text.appendChild(u.el('h3', 'sp-title', playlist.name));
      text.appendChild(u.el('p', 'sp-meta', playlistMeta(playlist)));
      if (playlist.description) text.appendChild(u.el('p', 'sp-meta', playlist.description));

      const actions = content.appendChild(u.el('div', 'sp-actions'));
      actions.appendChild(button('btn btn-primary', 'Reproducir en la PC', function () {
        send('spotify.play', { context: playlist.uri, track: null });
      }));
      actions.appendChild(button('btn', 'ABRIR SPOTIFY', function () {
        send('spotify.open', { uri: playlist.uri });
      }));

      if (!view.available) {
        content.appendChild(u.el('p', 'sp-message',
          'Spotify solo comparte las canciones de las playlists que creaste o en las que ' +
          'colaboras. Esta sí se puede reproducir o abrir en la PC.'));
        return;
      }
      (view.tracks || []).forEach(function (track) {
        content.appendChild(renderTrack(track, playlist));
      });
      if (view.tracks && !view.tracks.length && !view.tracksLoading) {
        content.appendChild(u.el('p', 'sp-message', 'Esta playlist no tiene canciones.'));
      }
      if (view.tracksLoading) content.appendChild(loadingRow());
      else if (view.tracksError) {
        content.appendChild(failure(view.tracksError, function () {
          loadTracks(view.tracksNext || 0);
        }));
      } else if (view.tracksNext !== null) {
        content.appendChild(moreButton(function () { loadTracks(view.tracksNext); }));
      }
    }

    function renderAccountHint() {
      content.appendChild(u.el('p', 'sp-message', local
        ? 'Vincula tu cuenta para ver tus playlists.'
        : 'Abre PhoneDeck en la PC (icono de la bandeja → Abrir panel) para vincular tu cuenta.'));
      if (local && !accountOpened) {
        accountOpened = true;
        account.open = true;
      }
    }

    function paint() {
      const top = body.scrollTop;
      content.innerHTML = '';
      const needsAccount = NEEDS_ACCOUNT.indexOf(data.status) >= 0;
      const online = data.status === 'online';
      u.setText(user, data.user || '');
      // "Sin vincular" ya lo explica el formulario; caducada merece el aviso.
      const silent = online || (needsAccount && data.status !== 'expired');
      u.setText(notice, silent ? '' : data.message);
      u.show(notice, !silent && !!data.message);
      if (needsAccount) renderAccountHint();
      else if (view.selected) renderDetail();
      else if (view.playlists || online) renderList();
      else if (data.status === 'connecting') content.appendChild(loadingRow());
      body.scrollTop = top;
    }

    function maybeLoad() {
      if (data.status === 'online' && !view.playlists && !view.loading && !view.error) {
        loadPlaylists(0);
      }
    }

    function update(type, message) {
      if (type !== 'spotify' || !message) return;
      const before = data;
      data = message;
      if (NEEDS_ACCOUNT.indexOf(data.status) >= 0 && view.loadedAt) view = newView();
      renderPlayer();
      const changed = ['status', 'user', 'message'].some(function (key) {
        return before[key] !== data[key];
      });
      if (changed) {
        paint();
        maybeLoad();
      }
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

    if (view.loadedAt && Date.now() - view.loadedAt > STALE_MS) view = newView();
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
        view.scrollTop = body.scrollTop;
        painters.splice(painters.indexOf(paint), 1);
      }
    };
  }

  global.PD.widgets.register('spotify', createSpotify);
})(window);
