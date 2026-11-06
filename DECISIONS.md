# Decisiones de diseño

Registro de lo que se eligió, lo que se descartó y por qué. Lo más reciente va primero.

## Volume Mixer, Pomodoro y OBS (2026-11-06)

### Arquitectura general

- **Elegido:** tres widgets nuevos (`mixer`, `pomodoro`, `obs`) que usan el WebSocket
  existente. La PC es la fuente de verdad y el celular solo muestra y envía comandos acotados.
- **Descartado:** pestañas fijas fuera de la configuración. No se podrían mover ni quitar, y
  perderían el permiso por widget (si quitas el widget, el celular pierde ese control).
- **Descartado:** un segundo servicio o puerto. Duplicaría autenticación y reconexión.

### Las secciones en instalaciones existentes

- **Elegido:** migración de una sola vez que añade las tres páginas a `config.json`, con copia
  de seguridad, y lo marca en `settings.json` para no repetirla.
- **Descartado:** que cada usuario las agregue con el editor. Por WiFi la edición está
  desactivada por defecto, así que muchos nunca las verían.

### Volume Mixer

- **Elegido:** sondeo cada segundo, solo mientras alguien mira la página, sobre el dispositivo
  de salida predeterminado. Una fila por ejecutable; un cambio se aplica a todas sus sesiones.
- **Descartado:** eventos COM (`IAudioSessionEvents`). Son instantáneos, pero exigen un hilo con
  bucle de mensajes y objetos de retorno por sesión; demasiado para ahorrar menos de un segundo.
- **Descartado:** todos los dispositivos de salida (el usuario eligió el predeterminado).
- **Iconos:** se piden con una clave opaca que el servidor resuelve contra las sesiones vivas.
  Nunca viaja una ruta desde el celular, igual que en `/api/icon`.

### Pomodoro

- **Elegido:** el temporizador vive en la PC y solo despierta en el instante en que termina un
  periodo. El celular recibe los milisegundos restantes y pinta una vez por segundo si está
  visible.
- **Descartado:** temporizador en el celular. Android lo frena en segundo plano y una recarga
  lo perdería.
- **Duraciones:** se guardan en `pomodoro.json`, no en `config.json`. Por WiFi `config.json` no
  se puede editar por defecto y el usuario quiere configurarlas desde el celular.
- **Tiempo restante, no hora de fin:** los relojes de PC y celular pueden diferir.
- **Estado fresco:** el hub pide el estado al temporizador en cada alta en vez de reenviar una
  copia guardada, que tendría un tiempo restante viejo.
- **Reiniciar:** con el periodo en marcha o en pausa, vuelve al inicio de ese periodo. Si ya
  estaba al inicio, reinicia el ciclo completo. Así no hace falta otro botón.
- **Avisos:** vibración, sonido y aviso en pantalla en el celular, más notificación de Windows.
- **Descartado:** notificación del sistema en el celular. Por WiFi (HTTP) el navegador la bloquea.

### OBS

- **Elegido:** la PC hace de puente hacia OBS. La contraseña se queda en `settings.json`, OBS no
  se expone a la red y funciona igual por USB y por WiFi.
- **Descartado:** conexión directa desde el celular. `crypto.subtle` no existe en HTTP, `adb
  reverse` solo reenvía el puerto de PhoneDeck y la contraseña acabaría en el teléfono.
- **Contraseña:** se cambia en un formulario solo disponible por `loopback` (la PC o el celular
  por USB). Es de solo escritura: el servidor nunca la devuelve.
- **Comandos:** el puente solo acepta cambiar a una escena de la lista actual; no reenvía
  peticiones libres a OBS.
- **Escenas por nombre, no por UUID:** `sceneUuid` no existe en las primeras versiones de
  obs-websocket 5 y el nombre funciona en todas.
- **Conexión bajo demanda:** solo se conecta si alguien mira la página, y cierra tras un minuto
  sin nadie. Sin OBS abierto, reintenta con espera creciente de hasta 30 s.
- **Temas bajo demanda:** un cliente recién conectado solo recibe `media`, `volume` y `stats`.
  Si recibiera todos, abrir cualquier página contaría un instante como mirar OBS.
- **Contraseña sin cifrar en `settings.json`:** es el mismo trato que el PIN y el secreto de los
  tokens. **Descartado:** el almacén de credenciales de Windows, que añade dependencias y no
  protege frente a un programa que ya corre con tu usuario.
