/*
 * PhoneDeck - Pomodoro. El temporizador vive en la PC; aquí solo se muestra.
 *
 * La pantalla se repinta una vez por segundo, justo en el cambio de segundo, y solo si el
 * periodo está en marcha y la página es visible. Sin requestAnimationFrame ni bucles.
 */
(function (global) {
  'use strict';

  const u = global.PD.util;
  const icon = global.PD.icons.icon;
  const MAX_MINUTES = 180;
  const PHASES = {
    work: 'Trabajo',
    short_break: 'Descanso corto',
    long_break: 'Descanso largo'
  };
  const FIELDS = [
    ['work', 'Trabajo'],
    ['short_break', 'Descanso corto'],
    ['long_break', 'Descanso largo']
  ];

  // ---------------------------------------------------------------- avisos
  let audio = null;

  /** Los navegadores solo dejan sonar audio creado tras un toque del usuario. */
  function unlockSound() {
    const Context = global.AudioContext || global.webkitAudioContext;
    if (audio || !Context) return;
    try {
      audio = new Context();
      audio.suspend();   // en reposo no consume nada; beep() lo reactiva
    } catch (e) {
      audio = null;
    }
  }

  function beep() {
    if (!audio) return;
    audio.resume();
    const start = audio.currentTime + 0.05;
    [0, 0.3, 0.6].forEach(function (offset) {
      const tone = audio.createOscillator();
      const gain = audio.createGain();
      tone.frequency.value = 880;
      gain.gain.value = 0.25;
      tone.connect(gain);
      gain.connect(audio.destination);
      tone.start(start + offset);
      tone.stop(start + offset + 0.18);
    });
    setTimeout(function () { audio.suspend(); }, 1200);
  }

  function alertUser(data) {
    u.toast(data && data.message, 'ok', 6000);
    u.vibrate([300, 150, 300]);
    beep();
  }

  // ---------------------------------------------------------------- widget
  function iconButton(className, iconName, label) {
    const btn = u.el('button', 'btn ' + className);
    btn.type = 'button';
    btn.appendChild(icon(iconName));
    btn.appendChild(u.el('span', '', label));
    return btn;
  }

  function createSettings(ctx) {
    const box = u.el('details', 'pomo-settings');
    box.appendChild(u.el('summary', '', 'Ajustar tiempos'));
    const form = box.appendChild(u.el('div', 'pomo-form'));
    const inputs = {};
    FIELDS.forEach(function (field) {
      const label = form.appendChild(u.el('label', 'pomo-field'));
      label.appendChild(u.el('span', '', field[1]));
      const input = label.appendChild(document.createElement('input'));
      input.type = 'number';
      input.min = '1';
      input.max = String(MAX_MINUTES);
      input.setAttribute('inputmode', 'numeric');
      label.appendChild(u.el('span', 'muted', 'min'));
      inputs[field[0]] = input;
    });
    const save = form.appendChild(u.el('button', 'btn', 'Guardar'));
    save.type = 'button';

    let running = false;
    let edited = false;

    form.addEventListener('input', function () { edited = true; });
    box.addEventListener('toggle', function () {
      if (!box.open) edited = false;
    });

    save.addEventListener('click', function () {
      const message = {};
      const valid = FIELDS.every(function (field) {
        const value = Number(inputs[field[0]].value);
        message[field[0]] = value;
        return Number.isInteger(value) && value >= 1 && value <= MAX_MINUTES;
      });
      if (!valid) {
        u.toast('Usa minutos enteros entre 1 y ' + MAX_MINUTES, 'error');
        return;
      }
      if (!ctx.send('pomodoro.config', message)) {
        u.toast('Sin conexión con la PC', 'error');
        return;
      }
      u.toast(running ? 'Guardado: se aplica desde el siguiente periodo' : 'Guardado', 'ok');
      box.open = false;
    });

    return {
      el: box,
      update: function (data) {
        running = data.status !== 'idle';
        if (edited) return;   // no pisar lo que se está escribiendo
        FIELDS.forEach(function (field) {
          inputs[field[0]].value = String(data.durations[field[0]]);
        });
      }
    };
  }

  function createPomodoro(item, ctx) {
    const el = u.el('div', 'widget w-pomodoro');
    const phase = el.appendChild(u.el('div', 'pomo-phase', '—'));
    const time = el.appendChild(u.el('div', 'pomo-time', '--:--'));
    const bar = el.appendChild(u.el('div', 'meter-bar'));
    const fill = bar.appendChild(u.el('div', 'meter-fill'));
    const cycle = el.appendChild(u.el('div', 'pomo-cycle', ''));
    const actions = el.appendChild(u.el('div', 'pomo-actions'));
    const main = actions.appendChild(u.el('button', 'btn btn-primary'));
    main.type = 'button';
    const reset = actions.appendChild(iconButton('', 'refresh', 'Reiniciar'));
    const settings = createSettings(ctx);
    el.appendChild(settings.el);

    let state = null;
    let timer = null;
    let mainKey = '';

    function remainingMs() {
      if (state.status !== 'running') return state.remaining_ms;
      return Math.max(0, state.remaining_ms - (Date.now() - state.received_at));
    }

    function paint() {
      const ms = remainingMs();
      u.setText(time, u.formatTime(Math.ceil(ms / 1000)));
      const done = state.period_ms ? 1 - ms / state.period_ms : 0;
      fill.style.transform = 'scaleX(' + u.clamp(done, 0, 1) + ')';
    }

    function tick() {
      clearTimeout(timer);
      timer = null;
      if (!state) return;
      paint();
      if (state.status !== 'running' || document.hidden) return;
      const ms = remainingMs();
      if (ms > 0) timer = setTimeout(tick, (ms % 1000 || 1000) + 15);
    }

    function setMain(key, iconName, label) {
      if (key === mainKey) return;
      mainKey = key;
      main.innerHTML = '';
      main.appendChild(icon(iconName));
      main.appendChild(u.el('span', '', label));
    }

    function render(data) {
      state = data;
      el.setAttribute('data-phase', data.phase);
      u.setText(phase, PHASES[data.phase] || data.phase);
      u.setText(cycle, data.completed + ' de ' + data.cycle_length + ' completados');
      if (data.status === 'running') setMain('pause', 'pause', 'Pausar');
      else if (data.status === 'paused') setMain('resume', 'play', 'Reanudar');
      else setMain('start', 'play', 'Iniciar');
      settings.update(data);
      tick();
    }

    function send(action) {
      u.vibrate(15);
      unlockSound();
      if (!ctx.send('pomodoro.control', { action: action })) {
        u.toast('Sin conexión con la PC', 'error');
      }
    }

    main.addEventListener('click', function () { send(mainKey); });
    reset.addEventListener('click', function () { send('reset'); });
    document.addEventListener('visibilitychange', tick);

    return {
      el: el,
      update: function (type, data) {
        if (type === 'pomodoro' && data) render(data);
      },
      destroy: function () {
        clearTimeout(timer);
        document.removeEventListener('visibilitychange', tick);
      }
    };
  }

  global.PD.widgets.register('pomodoro', createPomodoro);
  global.PD.pomodoro = { alert: alertUser, unlockSound: unlockSound };
})(window);
