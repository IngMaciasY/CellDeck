# Conectar Spotify

La página **Spotify** controla la música que suena en tu PC. Tiene cinco pestañas:

- **Inicio:** lo que escuchaste hace poco.
- **Playlists:** tus playlists y sus canciones.
- **Me gusta:** tus canciones guardadas.
- **Álbumes:** tus álbumes guardados, con todas sus canciones.
- **Buscar:** cualquier canción, álbum o playlist de Spotify.

Toca una canción para que suene en la PC; después sigue con el resto de su playlist o álbum.
**Mantenla pulsada** (o clic derecho en la PC) para añadirla a la cola. Toca la barra de abajo
para abrir **Reproduciendo**: ahí puedes arrastrar la barra para ir a cualquier parte de la
canción y ver qué viene en la cola.

Se configura una sola vez.

## Qué necesitas

- Una cuenta **Spotify Premium**. Spotify la exige al dueño de la app y para controlar la
  reproducción.
- Abrir PhoneDeck **desde la PC o con el celular por USB**. Spotify solo acepta volver a
  `127.0.0.1`, así que por WiFi no se puede vincular. Una vez vinculada, la cuenta funciona en
  todos los celulares emparejados, también por WiFi.

## Pasos

1. En PhoneDeck, abre la página **Spotify** y despliega **Cuenta de Spotify**. Deja a la vista
   la dirección que empieza por `http://127.0.0.1`.
2. Entra a [developer.spotify.com/dashboard](https://developer.spotify.com/dashboard) y crea
   una app. El nombre y la descripción pueden ser los que quieras.
3. En **Redirect URIs** pega la dirección del paso 1, tal cual.
4. En **Which API/SDKs are you planning to use?** marca **Web API** y guarda.
5. Copia el **Client ID** de la app y pégalo en PhoneDeck.
6. Toca **Vincular cuenta**, entra a Spotify y acepta los permisos. Volverás a PhoneDeck con
   tus playlists.

Si otra persona va a usar su cuenta con tu app, añádela en **User Management** dentro de la
app. Spotify admite hasta 5 cuentas por app en modo de desarrollo.

## Permisos que se piden

| Permiso | Para qué |
|---|---|
| `playlist-read-private` | Ver tus playlists privadas |
| `playlist-read-collaborative` | Ver las playlists colaborativas |
| `user-read-playback-state` | Mostrar qué suena y en qué dispositivo |
| `user-modify-playback-state` | Reproducir, pausar, cambiar de canción, moverte dentro de ella y añadir a la cola |
| `user-read-recently-played` | La pestaña Inicio |
| `user-library-read` | Las pestañas Me gusta y Álbumes |

Si vinculaste la cuenta antes de que existieran Inicio, Me gusta y Álbumes, PhoneDeck te pedirá
**volver a vincular** una vez para conceder los permisos nuevos.

## Qué debes saber

- **La música suena en la PC, no en el celular.** Spotify debe estar abierto en la PC o en otro
  dispositivo tuyo.
- **Las playlists que solo sigues no muestran sus canciones.** Spotify solo las entrega si
  creaste la playlist o colaboras en ella. Aparecen marcadas con **Solo reproducir**: se pueden
  reproducir o abrir, y para elegir una canción concreta, búscala en **Buscar**.
- **La búsqueda da hasta 10 resultados por tipo**, el máximo que permite Spotify.
- **Cualquier celular emparejado ve tus playlists**, incluidas las privadas, y también lo que
  escuchaste y tus canciones guardadas. Para impedirlo, quita el widget de Spotify con el editor.
- **El token se guarda sin cifrar** en `settings.json`, en tu PC, igual que la contraseña de
  OBS. Nunca llega al celular.

## Si algo falla

| Aviso | Qué hacer |
|---|---|
| `Spotify rechazó la cuenta` | Comprueba que el dueño de la app tenga Premium y que la cuenta esté en **User Management** |
| `La sesión de Spotify caducó` | Vuelve a vincular desde la PC. Pasa si retiraste el acceso en tu cuenta de Spotify |
| `Abre Spotify en la PC` | Spotify no está abierto en ningún dispositivo |
| `INVALID_CLIENT: Invalid redirect URI` en la página de Spotify | La dirección de **Redirect URIs** no coincide exactamente. Si cambiaste el puerto de PhoneDeck, actualízala |

## Desvincular

En **Cuenta de Spotify**, toca **Desvincular**. PhoneDeck borra el token de la PC. Para retirar
también el permiso en Spotify, entra a
[spotify.com/account/apps](https://www.spotify.com/account/apps/).
