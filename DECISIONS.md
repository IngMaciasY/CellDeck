# Decisiones de diseño

Registro de lo que se eligió, lo que se descartó y por qué. Lo más reciente va primero.

## Cambio de nombre: PhoneDeck → CellDeck (2026-11-09)

- **Por qué:** en GitHub ya había 17 repositorios llamados PhoneDeck. "CellDeck" solo aparecía en
  1 sin relación y estaba libre en PyPI. **Descartados:** TapDeck, PocketDeck y Botonera (muy
  usados), y CelDeck, MandoPC, CtrlCel y PanelCel (libres, pero el dueño eligió CellDeck).
- **Elegido: cambio completo** (paquete `celldeck`, `CellDeck.exe`, `%APPDATA%\CellDeck`,
  variables `CELLDECK_*`, cabecera `X-CellDeck-Token`). **Descartado:** cambiar solo lo visible.
  Dejaría `phonedeck` por dentro y confundiría a quien contribuya.
- **Migración de quien ya lo usaba:**
  - La carpeta de datos se **copia**, no se mueve, la primera vez y solo si la nueva no existe.
    Así la antigua queda de respaldo y nunca se pisan datos.
  - La entrada "PhoneDeck" de la clave Run se sustituye por la de CellDeck, para que no se
    abran los dos.
  - En el celular, las claves `phonedeck.*` de `localStorage` pasan a `celldeck.*`. Como el
    secreto también se copia, el token sigue valiendo y no hay que volver a emparejar.
- **El historial conserva "PhoneDeck"** en los commits anteriores al cambio. Es el nombre que
  tenía entonces, así que no se reescribe.

## Repositorio público y Releases (2026-11-09)

### Datos personales

- **Comprobado:** el código y los 44 commits no contienen credenciales. El Client ID y el token
  de Spotify, la contraseña de OBS, el PIN y el secreto viven en
  `%APPDATA%\CellDeck\settings.json`, fuera del repositorio.
- **Elegido:** quitar de la config de fábrica los botones de las apps del autor (Steam, Epic,
  Visual Studio, Brave) y poner acciones que existen en cualquier Windows (Calculadora y
  Configuración). El catálogo de apps sigue en el código y se ofrece desde el editor.
  **Descartado:** dejarlos como ejemplo. En una PC sin esas apps se ven botones que no hacen
  nada.
- **Elegido:** mantener Spotify y OBS como integraciones opcionales que no se conectan hasta
  que el usuario las configura. **Descartado:** quitarlas. No contienen datos del autor y son
  funciones generales.
- **Descartado:** un Client ID de Spotify dentro del .exe público. El modo de desarrollo admite
  5 usuarios por app y obligaría al autor a aprobar a cada uno.
- **Descartado:** `.env.example`. CellDeck no lee secretos de variables de entorno; cada
  instalación genera los suyos. En su lugar, [docs/configuracion.md](docs/configuracion.md)
  documenta `settings.json`.
- **Historial:** se reescribe el autor de todos los commits con `git filter-repo`, conservando
  las fechas, para usar el correo noreply de otra cuenta de GitHub. Se hace antes del primer
  push, cuando reescribir no afecta a nadie. **Descartado:** aplastar todo en un commit, que
  perdería el historial de decisiones.

### Ramas y contribución

- **Elegido:** GitHub Flow (`main` estable + ramas `feat/`, `fix/`… + PR con CI obligatoria).
  **Descartado:** Git Flow con `develop`, que es demasiado proceso para un proyecto de este
  tamaño y sin versiones paralelas que mantener.

### Ejecutables

- **Elegido:** publicar `CellDeck.exe` (un solo archivo) y `CellDeck-win64.zip` (carpeta). El
  primero es lo más fácil de usar; el segundo arranca más rápido y dispara menos falsos
  positivos del antivirus. **Descartado por ahora:** un instalador con Inno Setup. Añade otra
  herramienta a la compilación y la app no necesita registrarse en el sistema.
- **Nombres fijos** (`CellDeck.exe`, sin la versión): así
  `releases/latest/download/CellDeck.exe` siempre funciona. La versión está en el título de la
  Release y en las propiedades del .exe.
- **Sin firma de código:** cuesta dinero o requiere verificar una identidad. Se compensa con el
  SHA-256 y una atestación de compilación de GitHub (Sigstore), y el README explica el aviso de
  SmartScreen.
- **La Release se crea como borrador:** el dueño prueba el .exe en una PC real antes de
  publicarlo. Las versiones `0.x` y las que llevan guion se marcan como preliminares.
- **Versión en un solo sitio:** `src/celldeck/__init__.py`. `pyproject.toml` la lee como
  `dynamic`, el spec la pone en las propiedades del .exe y el flujo de Release falla si la
  etiqueta no coincide.

### GitHub Actions

- **Acciones fijadas por SHA de commit** y permisos mínimos por trabajo (`contents: read`;
  `write` solo en el trabajo de Release). Una etiqueta se puede mover y un SHA no. Dependabot
  propone las actualizaciones de las acciones.
- **`gh release create`** (preinstalado en el runner) en lugar de una acción de terceros para
  crear la Release: una dependencia externa menos.
- **El .exe se compila en el runner con el mismo `build.bat`** y las mismas dependencias por
  hash que en local, y pasa `pip-audit`. **Descartado:** compilar en la PC del autor y subirlo a
  mano como única vía. No deja prueba de origen y podría colar archivos locales. Sigue
  documentado como alternativa.

## Spotify: biblioteca, búsqueda y Reproduciendo (2026-11-07)

- **Elegido:** pestañas Inicio · Playlists · Me gusta · Álbumes · Buscar, más una vista
  Reproduciendo. Son las fuentes que Spotify sigue dando en modo de desarrollo.
  **Descartado:** una pantalla de inicio con filas horizontales al estilo Android Auto. Pide más
  desplazamiento en un celular vertical.
- **Buscar es la forma de elegir cualquier canción**, incluidas las de playlists ajenas, cuya
  lista Spotify no entrega. Esas playlists se marcan con "Solo reproducir".
- **Al tocar una canción** sigue con su playlist o álbum. En Me gusta no hay contexto que Spotify
  documente para reproducir, así que el celular manda las 50 canciones siguientes.
  **Descartado:** el contexto `spotify:user:…:collection`, que no está documentado para
  reproducir. Son 50 y no más porque un mensaje del WebSocket admite 4096 bytes.
- **Mantener pulsado añade a la cola** (clic derecho en la PC). **Descartado:** un menú en cada
  toque, que añade un paso a la acción más común.
- **Barra de progreso:** la PC manda la posición cada 5 s y el celular la cuenta entre medias.
  **Descartado:** consultar a Spotify cada segundo, que gastaría la cuota.
- **Permisos nuevos:** `user-read-recently-played` y `user-library-read`. Spotify informa de los
  permisos concedidos al renovar el token, y con eso se avisa de que hay que volver a vincular.
  Si no los informa, no se avisa; la sección explica el error al abrirla.
- **Búsqueda:** por HTTP con el botón o Enter, no mientras se escribe, para no gastar cuota.
  Spotify limita a 10 resultados por tipo desde febrero de 2026.

## Spotify y menú de engranaje (2026-11-07)

### Cómo mostrar Spotify

- **Elegido:** interfaz propia sobre la Web API, con la PC de puente, igual que OBS. Es lo único
  que mantiene el estilo del Deck y permite controlar la música de la PC.
- **Descartado:** Web Player en un iframe. Comprobado el 2026-11-07: `open.spotify.com` envía
  `frame-ancestors` y el navegador lo rechaza.
- **Descartado:** Spotify Embed. Tiene el aspecto de Spotify, carga una playlist por iframe y
  obliga a abrir la CSP. Sonaría en el celular, y por WiFi (HTTP) probablemente solo clips de
  menos de 30 s, porque el audio cifrado pide un contexto seguro. Esto último no se probó.
- **Descartado:** Web Playback SDK. Convertiría el celular en reproductor, y CellDeck controla
  la PC.

### Autenticación

- **Elegido:** OAuth 2.0 con PKCE. Sin `client_secret`, que en un proyecto abierto no se podría
  guardar en ningún sitio.
- **Elegido:** un Client ID por usuario. El modo de desarrollo admite 5 usuarios por app, y salir
  de él exige ser una organización con al menos 250 000 usuarios activos al mes.
- **Descartado:** un Client ID común en el repositorio. Dejaría de servir con la sexta persona y
  obligaría a autorizar a cada usuario a mano.
- **Solo PC o USB:** Spotify solo admite `http` en la dirección de retorno si es `127.0.0.1`.
  **Descartado:** servir CellDeck por HTTPS, que exigiría certificados en cada celular.
- **Tokens:** el de acceso vive en memoria; el de renovación, en `settings.json` sin cifrar, igual
  que la contraseña de OBS y por la misma razón.
- **Renovación con cerrojo:** con PKCE el token puede rotar y el anterior deja de valer. Dos
  renovaciones simultáneas expulsarían al usuario.
- **Sesión rechazada:** si Spotify responde `invalid_grant` se borra el token y se pide volver a
  vincular. Los fallos de red no lo borran.
- **`state` de un solo uso:** impide que otra web vincule en esta PC una cuenta ajena. La ruta de
  retorno no lleva token de CellDeck porque quien llega es el navegador, desde Spotify.
- **Registro:** el filtro de los logs oculta también `code` y `state` del retorno.

### Permisos y privacidad

- **Elegido:** cuatro permisos, dos de lectura de playlists y dos de reproducción. El brief pedía
  solo lectura, pero el usuario eligió controlar la música de la PC.
- **Consecuencia aceptada:** cualquier celular emparejado ve las playlists privadas, como con OBS.
  **Descartado:** limitarlas a PC o USB. Se retira el acceso quitando el widget.
- **Sin widget, sin datos:** las rutas y comandos exigen el widget, igual que el resto de controles.

### Datos

- **Playlists que solo se siguen:** Spotify solo entrega canciones de playlists propias o
  colaborativas. Se muestran con un aviso y se pueden reproducir o abrir.
  **Descartado:** ocultarlas, porque desaparecerían listas que el usuario reconoce como suyas.
- **Por HTTP, no por WebSocket:** playlists y canciones son consultas paginadas. Por WebSocket
  solo va el estado, que sí cambia solo.
- **Estado bajo demanda:** el reproductor se consulta cada 5 s solo si alguien mira la sección.
- **Campos viejos y nuevos:** se lee `items` y, si falta, `tracks`, por el cambio de febrero de 2026.

### Portadas

- **Elegido:** pasan por la PC con una clave opaca, como los iconos del mezclador. El celular nunca
  envía una URL, la CSP no cambia y funciona con un celular por USB sin Internet.
- **Descartado:** añadir `i.scdn.co` a la CSP. Las portadas llegan de varios dominios y el celular
  necesitaría Internet propio.
- **Límites del proxy:** solo HTTPS a dominios de Spotify, sin seguir redirecciones, solo formatos
  de mapa de bits, 2 MB por imagen, 16 MB de caché y 6 descargas a la vez.

### Reproducción

- **Órdenes en segundo plano:** Spotify puede tardar segundos. Si se esperaran, el volumen y demás
  controles de ese celular quedarían bloqueados.
- **Sin dispositivo activo:** se reintenta indicando uno, con preferencia por la PC. Esta respuesta
  (404) no figura en la documentación de Spotify y no se ha probado contra el servicio real.
- **Abrir en la PC:** primero con la app; sin ella, en el navegador. Respeta los esquemas permitidos.

### Marca

- **Logo:** archivos oficiales sin alterar, blanco en temas oscuros y negro en el claro.
  **Descartado:** el verde, que Spotify reserva para fondos negros o blancos puros, y nuestros
  fondos no lo son. Mismo motivo por el que el botón verde de Multimedia no lleva el logo.
- **Pestaña:** usa solo el icono por falta de espacio, a 22 px. Dentro de la sección va el logo
  completo como atribución.

### Instalaciones existentes

- **Elegido:** cada sección guarda la versión en la que apareció y solo se añaden las de versiones
  nuevas. **Descartado:** subir `SECTIONS_VERSION` sin más, que devolvería Mixer, Pomodoro u OBS a
  quien los borró.

### Sección a pantalla completa

- **Elegido:** sola en su página, la sección mide justo el alto visible. Las filas del grid son
  para botones: en horizontal dejaban el reproductor fuera de la pantalla.

### Engranaje

- **Elegido:** los tres botones pasan a un menú que conserva sus ID, así su lógica no cambia.
- **Opciones que no aplican:** se ocultan. Si solo queda Ajustes, el engranaje lo abre directamente.
  **Descartado:** mostrarlas desactivadas, que ocupa sitio con opciones que nunca se podrán usar.
- **Tocar fuera solo cierra:** el toque no llega a lo que hay debajo. Debajo hay botones como
  Apagar; cerrar un menú no debe pulsarlos. Cuesta un toque más para cambiar de pestaña.

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
- **Consecuencia aceptada:** tras actualizar, los celulares emparejados ganan los controles del
  mezclador y de OBS sin que nadie los active. Se quitan borrando esas páginas.
- **Volumen general:** la migración no lo añade si el usuario ya lo había quitado, porque quitar
  un widget retira ese control al celular.
- **Si la escritura falla:** CellDeck arranca igual y reintenta en el siguiente inicio.

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
- **Sin widget, se detiene:** si se borra el widget con un periodo en marcha, el temporizador se
  para al terminar ese periodo, porque nadie podría pararlo desde el celular.
- **Avisos:** vibración, sonido y aviso en pantalla en el celular, más notificación de Windows.
- **Descartado:** notificación del sistema en el celular. Por WiFi (HTTP) el navegador la bloquea.

### OBS

- **Elegido:** la PC hace de puente hacia OBS. La contraseña se queda en `settings.json`, OBS no
  se expone a la red y funciona igual por USB y por WiFi.
- **Descartado:** conexión directa desde el celular. `crypto.subtle` no existe en HTTP, `adb
  reverse` solo reenvía el puerto de CellDeck y la contraseña acabaría en el teléfono.
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
