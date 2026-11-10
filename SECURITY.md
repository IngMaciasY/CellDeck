# Seguridad

CellDeck controla tu PC (teclado, programas, apagado), así que la seguridad importa.

## Versiones con soporte

Solo la última versión publicada en [Releases](../../releases) recibe correcciones de seguridad.

## Cómo reportar una vulnerabilidad

**No abras un issue público.** Usa el reporte privado de GitHub: pestaña **Security** →
**Report a vulnerability**. Incluye:

- La versión de CellDeck y de Windows.
- Los pasos para reproducirla y su impacto. Por ejemplo: "otro equipo de la red WiFi puede
  ejecutar acciones sin PIN".

Responderemos en cuanto podamos. Es un proyecto voluntario y no hay plazos garantizados.

## Cómo protege CellDeck tu PC (resumen)

- **USB por defecto.** El modo WiFi hay que activarlo a mano desde el icono de la bandeja.
- **PIN de 6 dígitos y token firmado** para cada dispositivo. **Desconectar todos los dispositivos**,
  en la bandeja, invalida todos los tokens.
- **Comprobación de la cabecera `Host`**, contra ataques de *DNS rebinding*.
- **La edición remota (por WiFi) está desactivada** por defecto.
- **Lista de esquemas de URL permitidos** para los botones de tipo enlace.
- **Los secretos se guardan solo en tu PC**, en `%APPDATA%\CellDeck\settings.json`: PIN,
  secreto de los tokens, contraseña de OBS y token de Spotify. Nunca se incluyen en el
  repositorio ni en el ejecutable.

Usa el modo WiFi solo en redes de confianza (tu casa), no en redes públicas.
