# Conexión por cable USB

Hay dos formas de usar CellDeck por cable. **Recomendada: `adb reverse`.**

| | `adb reverse` | Anclaje USB (tethering) |
|---|---|---|
| Necesita adb en la PC | Sí | No |
| Modo de CellDeck | USB (solo `127.0.0.1`, el más seguro) | WiFi (escucha en la red, pide PIN) |
| URL en el celular | `http://localhost:8765` | `http://IP-de-la-PC:8765` |
| "Añadir a inicio" a pantalla completa | Sí (localhost es contexto seguro) | Acceso directo normal |
| Riesgo | Ninguno | La PC puede usar los datos móviles del celular |

---

## Opción A: `adb reverse` (recomendada)

### 1. Activar la depuración USB (Xiaomi Redmi 5 Plus / MIUI)

1. **Ajustes → Mi teléfono / Acerca del teléfono** → toca 7 veces **Versión de MIUI**
   hasta ver "Ya eres desarrollador".
2. **Ajustes → Ajustes adicionales → Opciones de desarrollador**:
   - Activa **Depuración USB**.
   - (Recomendado) Activa **Pantalla activa / Mantener activo**: la pantalla no se apaga
     mientras el celular carga, y por cable siempre está cargando.

### 2. Instalar adb en la PC

Descarga **SDK Platform-Tools** desde la web oficial de Android
(<https://developer.android.com/tools/releases/platform-tools>), descomprímelo (por ejemplo
en `C:\platform-tools`) y añade esa carpeta al `PATH`. Comprueba con `adb version`.

### 3. Conectar

1. Conecta el cable. En el celular acepta **"¿Permitir depuración USB?"** (marca
   "Permitir siempre desde este ordenador").
2. Con CellDeck en marcha, ejecuta `scripts\connect_usb.bat` (o, desde el hito (e),
   **Conectar USB** en el icono de la bandeja).
3. En el celular abre Chrome y entra en **`http://localhost:8765`**.
4. Menú de Chrome → **Añadir a pantalla de inicio**. Se abrirá a pantalla completa.

> El túnel de `adb reverse` se pierde al desconectar el cable o reiniciar el celular:
> vuelve a ejecutar `connect_usb.bat`.

---

## Opción B: Anclaje USB (sin adb)

1. Arranca CellDeck en **modo WiFi** (`scripts\dev.bat --mode wifi`; desde el hito (e),
   en la bandeja). El PIN aparece en el log y, más adelante, en la bandeja.
2. En el celular: **Ajustes → Conexión y compartir → Anclaje USB**.
3. En la PC, `ipconfig` muestra un adaptador nuevo ("Remote NDIS"). Anota su IPv4
   (normalmente `192.168.42.x`).
4. En el celular abre `http://192.168.42.x:8765` e introduce el PIN.

> ⚠️ Windows puede empezar a usar el celular como conexión a Internet y gastar datos
> móviles. Desactiva los datos móviles del celular mientras usas el anclaje.

---

## Problemas frecuentes

| Síntoma | Solución |
|---|---|
| `adb devices` no muestra nada | Cambia de cable (algunos solo cargan), usa otro puerto USB, revisa que la depuración USB esté activa. |
| Aparece `unauthorized` | Desbloquea el celular y acepta el diálogo. Si no aparece: Opciones de desarrollador → *Revocar autorizaciones de depuración USB* y reconecta. |
| `http://localhost:8765` no carga | Comprueba que CellDeck esté en marcha en la PC y repite `connect_usb.bat`. |
| Error de conexión segura / SSL, o el log dice `Invalid HTTP request received` | Chrome está entrando por `https://`. Escribe la dirección **completa con `http://`** (`http://localhost:8765`) o deja que `connect_usb.bat` la abra solo. Después añádela a la pantalla de inicio. |
| La pantalla se apaga | Activa **Pantalla activa** en Opciones de desarrollador, o deja activo "Mantener pantalla encendida" en el menú de CellDeck. |
