"""Puente con Spotify por su Web API: playlists y control de la reproducción.

El celular nunca habla con Spotify: habla con PhoneDeck y este puente habla con Spotify. Así los
tokens no salen de la PC, las portadas no obligan a abrir la CSP y funciona igual por USB y por
WiFi. Spotify solo acepta ``http`` en la dirección de retorno si es ``127.0.0.1``, de modo que
la cuenta se vincula desde la PC o con el celular por USB; después sirve desde cualquier celular.

Autenticación: OAuth 2.0 con PKCE, sin ``client_secret``. PhoneDeck es código abierto y cada
usuario crea su propio Client ID (el modo de desarrollo de Spotify admite 5 usuarios por app).

Alcance: leer playlists y ordenar reproducir, pausar y saltar. No se reenvían peticiones libres.
El estado del reproductor solo se consulta mientras alguien mira la sección.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import html
import json
import logging
import re
import secrets
import time
import urllib.error
import urllib.request
from collections import OrderedDict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from email.message import Message
from enum import StrEnum
from http.client import HTTPException
from typing import Any, Literal
from urllib.parse import urlencode, urlsplit

from phonedeck.config.settings import SettingsStore
from phonedeck.platform.base import PlatformBackend, PlatformError
from phonedeck.ws import WebSocketHub

log = logging.getLogger(__name__)

TOPIC = "spotify"
ACCOUNTS_URL = "https://accounts.spotify.com"
API_URL = "https://api.spotify.com/v1"
CALLBACK_PATH = "/api/spotify/callback"
SCOPES = (
    "playlist-read-private",
    "playlist-read-collaborative",
    "user-read-playback-state",
    "user-modify-playback-state",
)

CLIENT_ID_PATTERN = r"^[0-9a-fA-F]{32}$"
PLAYLIST_ID_PATTERN = r"^[A-Za-z0-9]{1,62}$"
PLAYLIST_URI_PATTERN = r"^spotify:playlist:[A-Za-z0-9]{1,62}$"
ITEM_URI_PATTERN = r"^spotify:(track|episode):[A-Za-z0-9]{1,62}$"
IMAGE_KEY_PATTERN = r"^[0-9a-f]{32}$"

PAGE_SIZE = 50  # máximo que admite Spotify
PLAYLIST_IMAGE_WIDTH = 160
TRACK_IMAGE_WIDTH = 64
MAX_DESCRIPTION = 300

HTTP_TIMEOUT_S = 6.0
EXPIRY_MARGIN_S = 60  # el token de acceso se renueva antes de que caduque
LOGIN_TTL_S = 600.0
MAX_PENDING_LOGINS = 8
POLL_S = 5.0
MAX_RETRY_S = 60.0
MAX_BACKOFF_STEPS = 4
MAX_QUEUED_COMMANDS = 5
AFTER_COMMAND_S = 0.4  # Spotify tarda un instante en reflejar una orden
DEFAULT_RETRY_AFTER_S = 5.0
WAIT_IDLE_S = 30.0

MAX_JSON_BYTES = 4 * 1024 * 1024
MAX_IMAGE_BYTES = 2 * 1024 * 1024
MAX_IMAGE_CACHE_BYTES = 16 * 1024 * 1024
MAX_IMAGE_KEYS = 5000
MAX_IMAGE_DOWNLOADS = 6  # una lista pide decenas de portadas a la vez
IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp", "image/gif"})
IMAGE_DOMAINS = ("scdn.co", "spotifycdn.com")

NOT_CONFIGURED_MESSAGE = "Falta configurar Spotify desde la PC"
NOT_LINKED_MESSAGE = "Cuenta de Spotify sin vincular"
CONNECTING_MESSAGE = "Conectando con Spotify…"
OFFLINE_MESSAGE = "No se pudo conectar con Spotify"
EXPIRED_MESSAGE = "La sesión de Spotify caducó. Vuelve a vincular la cuenta desde la PC"
FORBIDDEN_MESSAGE = (
    "Spotify rechazó la cuenta. Revisa que el dueño de la app tenga Premium "
    "y que esta cuenta esté en la lista de usuarios de la app"
)
RATE_LIMIT_MESSAGE = "Spotify pidió esperar un momento antes de seguir"
NO_DEVICE_MESSAGE = "Abre Spotify en la PC y vuelve a intentarlo"
PREMIUM_MESSAGE = "Spotify solo permite controlar la reproducción con una cuenta Premium"
COMMAND_REFUSED_MESSAGE = "Spotify no permitió esa acción ahora mismo"
SCHEME_BLOCKED_MESSAGE = "Los ajustes de la PC no permiten abrir enlaces de Spotify"
BUSY_MESSAGE = "Spotify va lento: espera un momento"

MediaAction = Literal["play", "pause", "next", "previous"]
PLAYER_COMMANDS: dict[str, tuple[str, str]] = {
    "play": ("PUT", "/me/player/play"),
    "pause": ("PUT", "/me/player/pause"),
    "next": ("POST", "/me/player/next"),
    "previous": ("POST", "/me/player/previous"),
}


class SpotifyStatus(StrEnum):
    UNCONFIGURED = "unconfigured"
    UNLINKED = "unlinked"
    CONNECTING = "connecting"
    ONLINE = "online"
    OFFLINE = "offline"
    EXPIRED = "expired"
    FORBIDDEN = "forbidden"


STATUS_MESSAGES = {
    SpotifyStatus.UNCONFIGURED: NOT_CONFIGURED_MESSAGE,
    SpotifyStatus.UNLINKED: NOT_LINKED_MESSAGE,
    SpotifyStatus.CONNECTING: CONNECTING_MESSAGE,
    SpotifyStatus.ONLINE: "",
    SpotifyStatus.OFFLINE: OFFLINE_MESSAGE,
    SpotifyStatus.EXPIRED: EXPIRED_MESSAGE,
    SpotifyStatus.FORBIDDEN: FORBIDDEN_MESSAGE,
}


class SpotifyError(PlatformError):
    """Error apto para mostrar en el celular."""


class SpotifyAuthError(SpotifyError):
    """Spotify ya no acepta la sesión: reintentar no lo arregla, hay que volver a vincular."""


class SpotifyApiError(SpotifyError):
    """Respuesta de error de la Web API."""

    def __init__(self, status: int, reason: str = "", detail: str = "") -> None:
        super().__init__(FORBIDDEN_MESSAGE if status == 403 else OFFLINE_MESSAGE)
        self.status = status
        self.reason = reason
        self.detail = detail

    @property
    def no_device(self) -> bool:
        """Un 404 también puede ser una playlist borrada: no se confunden."""
        if self.status != 404:
            return False
        return self.reason == "NO_ACTIVE_DEVICE" or "device" in self.detail.lower()


@dataclass(frozen=True, slots=True)
class HttpResponse:
    status: int
    body: bytes
    headers: Message[str, str]  # sin distinguir mayúsculas


@dataclass(frozen=True, slots=True)
class PendingLogin:
    """Un inicio de sesión a medias, entre abrir Spotify y volver a PhoneDeck."""

    verifier: str
    redirect_uri: str
    origin: str
    expires_at: float


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """La API no redirige; seguir un 30x permitiría que una portada apuntara a otro equipo."""

    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


_OPENER = urllib.request.build_opener(_NoRedirect)


def http_request(
    method: str, url: str, headers: Mapping[str, str], data: bytes | None, limit: int
) -> HttpResponse:
    """Petición bloqueante: se ejecuta en un hilo. Lee como mucho ``limit + 1`` bytes."""
    request = urllib.request.Request(url, data=data, headers=dict(headers), method=method)  # noqa: S310
    try:
        with _OPENER.open(request, timeout=HTTP_TIMEOUT_S) as res:
            return HttpResponse(res.status, res.read(limit + 1), res.headers)
    except urllib.error.HTTPError as exc:
        with exc:
            return HttpResponse(exc.code, exc.read(limit + 1), exc.headers)


def code_challenge(verifier: str) -> str:
    """Reto PKCE (S256) del ``code_verifier``."""
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def redirect_uri(port: int) -> str:
    """Dirección de retorno. Spotify no admite ``localhost``: tiene que ser la IP."""
    return f"http://127.0.0.1:{port}{CALLBACK_PATH}"


def is_spotify_image(url: str) -> bool:
    """Solo se descargan portadas de los dominios de imágenes de Spotify, por HTTPS."""
    try:
        parts = urlsplit(url)
        port = parts.port
    except ValueError:
        return False
    host = parts.hostname or ""
    return (
        parts.scheme == "https"
        and port in (None, 443)
        and any(host == d or host.endswith(f".{d}") for d in IMAGE_DOMAINS)
    )


def pick_image(images: Any, min_width: int) -> str | None:
    """La imagen más pequeña que cubra ``min_width``: un celular viejo no necesita más."""
    if not isinstance(images, list):
        return None
    valid = [i for i in images if isinstance(i, dict) and isinstance(i.get("url"), str)]
    sized = sorted(
        (i for i in valid if isinstance(i.get("width"), int)), key=lambda i: int(i["width"])
    )
    for image in sized:
        if image["width"] >= min_width:
            return str(image["url"])
    if sized:
        return str(sized[-1]["url"])
    return str(valid[0]["url"]) if valid else None


def clean_text(value: Any) -> str:
    """Las descripciones llegan con entidades HTML y a veces con enlaces."""
    if not isinstance(value, str):
        return ""
    text = html.unescape(re.sub(r"<[^>]*>", "", value)).strip()
    return text[:MAX_DESCRIPTION]


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _entries(page: dict[str, Any]) -> list[dict[str, Any]]:
    """Elementos de una página de resultados. Spotify a veces incluye ``null``."""
    items = page.get("items")
    return [i for i in items if isinstance(i, dict)] if isinstance(items, list) else []


def _next_offset(page: dict[str, Any], offset: int) -> int | None:
    items = page.get("items")
    count = len(items) if isinstance(items, list) else 0
    return offset + count if page.get("next") and count else None


def _parse_json(res: HttpResponse) -> Any:
    if not res.body:
        return None
    try:
        return json.loads(res.body)
    except ValueError as exc:
        raise SpotifyError(OFFLINE_MESSAGE) from exc


def _api_error(res: HttpResponse) -> SpotifyApiError:
    try:
        error = _mapping(_mapping(json.loads(res.body)).get("error"))
    except ValueError:
        error = {}
    return SpotifyApiError(
        res.status, str(error.get("reason") or ""), str(error.get("message") or "")
    )


def _retry_after(res: HttpResponse) -> float:
    try:
        return max(1.0, float(res.headers.get("Retry-After", DEFAULT_RETRY_AFTER_S)))
    except ValueError:
        return DEFAULT_RETRY_AFTER_S


def pick_device(devices: list[dict[str, Any]]) -> str | None:
    """Dispositivo para reproducir si no hay uno activo: se prefiere la PC."""
    usable = [d for d in devices if isinstance(d.get("id"), str) and not d.get("is_restricted")]
    usable.sort(key=lambda d: str(d.get("type", "")).lower() != "computer")
    return str(usable[0]["id"]) if usable else None


class SpotifyBridge:
    def __init__(
        self,
        hub: WebSocketHub,
        store: SettingsStore,
        *,
        accounts_url: str = ACCOUNTS_URL,
        api_url: str = API_URL,
        allow_image: Callable[[str], bool] = is_spotify_image,
    ) -> None:
        self.hub = hub
        self._store = store
        self._accounts_url = accounts_url
        self._api_url = api_url
        self._allow_image = allow_image
        self._status = SpotifyStatus.CONNECTING
        self._message = CONNECTING_MESSAGE
        self._access: str | None = None
        self._expires_at = 0.0
        # Solo una renovación a la vez: Spotify puede rotar el refresh token en cada una.
        self._token_lock = asyncio.Lock()
        # Las órdenes se aplican en el orden en que se tocaron.
        self._command_lock = asyncio.Lock()
        self._queued_commands = 0
        # Cambia con cada sesión: una respuesta de la sesión anterior ya no se usa.
        self._session = 0
        self._user_id: str | None = None
        self._user: str | None = None
        self._player: dict[str, Any] | None = None
        self._logins: dict[str, PendingLogin] = {}
        self._retry_at = 0.0
        self._next_poll = 0.0
        self._failures = 0
        self._published: dict[str, Any] | None = None
        # El celular pide las portadas con una clave opaca: nunca envía una URL.
        self._image_urls: OrderedDict[str, str] = OrderedDict()
        self._images: OrderedDict[str, tuple[bytes, str]] = OrderedDict()
        self._image_bytes = 0
        self._downloads = asyncio.Semaphore(MAX_IMAGE_DOWNLOADS)

    # ---------------------------------------------------------------- publicar
    @property
    def status(self) -> SpotifyStatus:
        settings = self._store.settings
        if not settings.spotify_client_id:
            return SpotifyStatus.UNCONFIGURED
        if not settings.spotify_refresh_token:
            expired = self._status is SpotifyStatus.EXPIRED
            return SpotifyStatus.EXPIRED if expired else SpotifyStatus.UNLINKED
        return self._status

    def payload(self) -> dict[str, Any]:
        status = self.status
        linked = status is self._status and status not in (
            SpotifyStatus.UNCONFIGURED,
            SpotifyStatus.UNLINKED,
            SpotifyStatus.EXPIRED,
        )
        return {
            "status": status.value,
            "message": self._message if linked else STATUS_MESSAGES[status],
            "user": self._user if linked else None,
            "player": self._player if linked else None,
        }

    async def _publish(self) -> None:
        payload = self.payload()
        if payload != self._published:
            self._published = payload
            # Sin caché: cada suscripción pide el estado actual a ``payload``.
            await self.hub.broadcast(TOPIC, payload, cache=False)

    def _set_status(self, status: SpotifyStatus, message: str | None = None) -> None:
        self._status = status
        self._message = STATUS_MESSAGES[status] if message is None else message
        if status is not SpotifyStatus.ONLINE:
            self._player = None

    def poke(self, delay: float = 0.0) -> None:
        """Adelanta la siguiente consulta del reproductor."""
        self._next_poll = min(self._next_poll, time.monotonic() + delay)
        self.hub.wake()

    # ------------------------------------------------------------------ cuenta
    def _reset_session(self) -> None:
        self._session += 1
        self._access = None
        self._expires_at = 0.0
        self._user_id = None
        self._user = None
        self._player = None
        self._retry_at = 0.0
        self._failures = 0
        self._next_poll = 0.0

    def _save(self, **changes: Any) -> None:
        try:
            self._store.update(**changes)
        except OSError:
            log.exception("No se pudo guardar la sesión de Spotify")

    async def save_client_id(self, client_id: str) -> None:
        """Una sesión pertenece a un Client ID: si cambia, hay que volver a vincular."""
        settings = self._store.settings
        if client_id == settings.spotify_client_id:
            return
        async with self._token_lock:
            self._reset_session()
            self._logins.clear()
            self._set_status(SpotifyStatus.CONNECTING)
            self._store.update(spotify_client_id=client_id, spotify_refresh_token="")
        await self._publish()

    async def unlink(self) -> None:
        async with self._token_lock:
            self._reset_session()
            self._logins.clear()
            self._set_status(SpotifyStatus.CONNECTING)
            self._store.update(spotify_refresh_token="")
            self._images.clear()
            self._image_urls.clear()
            self._image_bytes = 0
        await self._publish()

    def start_login(self, callback: str, origin: str) -> str:
        """Prepara el login y devuelve la URL de Spotify que debe abrir el navegador."""
        client_id = self._store.settings.spotify_client_id
        if not client_id:
            raise SpotifyError(NOT_CONFIGURED_MESSAGE)
        now = time.monotonic()
        self._logins = {k: v for k, v in self._logins.items() if v.expires_at > now}
        while len(self._logins) >= MAX_PENDING_LOGINS:
            del self._logins[next(iter(self._logins))]
        login_state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        self._logins[login_state] = PendingLogin(verifier, callback, origin, now + LOGIN_TTL_S)
        query = urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": callback,
                "code_challenge_method": "S256",
                "code_challenge": code_challenge(verifier),
                "state": login_state,
                "scope": " ".join(SCOPES),
            }
        )
        return f"{self._accounts_url}/authorize?{query}"

    async def finish_login(self, login_state: str, code: str, error: str) -> tuple[str, str]:
        """Termina el login. Devuelve ``(resultado, origen)`` para volver a la app.

        ``state`` es de un solo uso y solo lo conoce quien inició el login: un enlace
        preparado por otra web no puede vincular aquí una cuenta ajena.
        """
        pending = self._logins.pop(login_state, None)
        if pending is None or pending.expires_at <= time.monotonic():
            return "error", "/"
        if error or not code:
            return ("denied" if error == "access_denied" else "error"), pending.origin
        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": pending.redirect_uri,
            "client_id": self._store.settings.spotify_client_id,
            "code_verifier": pending.verifier,
        }
        async with self._token_lock:
            try:
                body = await self._token_post(form)
            except SpotifyError:
                log.warning("Spotify no aceptó el código de autorización")
                return "error", pending.origin
            refresh_token = body.get("refresh_token")
            if not isinstance(refresh_token, str) or not refresh_token:
                return "error", pending.origin
            self._reset_session()
            self._keep_access(body)
            self._set_status(SpotifyStatus.CONNECTING)
            self._save(spotify_refresh_token=refresh_token)
        log.info("Cuenta de Spotify vinculada")
        await self._publish()
        self.poke()
        return "ok", pending.origin

    # ------------------------------------------------------------------ tokens
    async def _fetch(
        self,
        method: str,
        url: str,
        headers: Mapping[str, str] | None = None,
        data: bytes | None = None,
        limit: int = MAX_JSON_BYTES,
    ) -> HttpResponse:
        try:
            res = await asyncio.to_thread(http_request, method, url, headers or {}, data, limit)
        except (OSError, HTTPException) as exc:
            log.debug("Sin conexión con Spotify: %s", exc)
            raise SpotifyError(OFFLINE_MESSAGE) from exc
        if len(res.body) > limit:
            raise SpotifyError(OFFLINE_MESSAGE)
        return res

    async def _token_post(self, form: dict[str, str]) -> dict[str, Any]:
        res = await self._fetch(
            "POST",
            f"{self._accounts_url}/api/token",
            {"Content-Type": "application/x-www-form-urlencoded"},
            urlencode(form).encode("ascii"),
        )
        body = _mapping(_parse_json(res))
        if res.status == 200 and isinstance(body.get("access_token"), str):
            return body
        if res.status in (400, 401) and body.get("error") in ("invalid_grant", "invalid_client"):
            raise SpotifyAuthError(EXPIRED_MESSAGE)
        raise SpotifyError(OFFLINE_MESSAGE)

    def _keep_access(self, body: dict[str, Any]) -> None:
        lifetime = body.get("expires_in")
        seconds = lifetime if isinstance(lifetime, int) else 3600
        self._access = str(body["access_token"])
        self._expires_at = time.monotonic() + max(0, seconds - EXPIRY_MARGIN_S)

    async def _access_token(self, stale: str | None = None) -> str:
        """Token de acceso vigente. ``stale`` es uno que Spotify acaba de rechazar."""
        async with self._token_lock:
            fresh = self._access is not None and self._access != stale
            if fresh and self._access and time.monotonic() < self._expires_at:
                return self._access
            settings = self._store.settings
            if not settings.spotify_refresh_token:
                # Quien esperaba el cerrojo mientras se rechazaba la sesión llega aquí.
                expired = self._status is SpotifyStatus.EXPIRED
                raise SpotifyAuthError(EXPIRED_MESSAGE if expired else NOT_LINKED_MESSAGE)
            form = {
                "grant_type": "refresh_token",
                "refresh_token": settings.spotify_refresh_token,
                "client_id": settings.spotify_client_id,
            }
            try:
                body = await self._token_post(form)
            except SpotifyAuthError:
                log.warning("Spotify rechazó la sesión guardada")
                self._reset_session()
                self._set_status(SpotifyStatus.EXPIRED)
                self._save(spotify_refresh_token="")
                self.poke()
                raise
            self._keep_access(body)
            # Con PKCE el refresh token puede rotar: el anterior deja de valer.
            rotated = body.get("refresh_token")
            if isinstance(rotated, str) and rotated and rotated != settings.spotify_refresh_token:
                self._save(spotify_refresh_token=rotated)
            assert self._access is not None  # noqa: S101 - lo acaba de fijar _keep_access
            return self._access

    # --------------------------------------------------------------------- API
    async def _call(
        self,
        method: str,
        path: str,
        query: Mapping[str, str | int] | None = None,
        body: dict[str, Any] | None = None,
    ) -> HttpResponse:
        if time.monotonic() < self._retry_at:
            raise SpotifyError(RATE_LIMIT_MESSAGE)
        url = f"{self._api_url}{path}"
        if query:
            url += f"?{urlencode(query)}"
        data = None if body is None else json.dumps(body).encode("utf-8")
        # PUT y POST sin cuerpo necesitan uno vacío para llevar Content-Length.
        if data is None and method != "GET":
            data = b""

        async def send(token: str) -> HttpResponse:
            headers = {"Authorization": f"Bearer {token}"}
            if data is not None:  # sin esto, urllib declararía un formulario
                headers["Content-Type"] = "application/json"
            return await self._fetch(method, url, headers, data)

        token = await self._access_token()
        res = await send(token)
        if res.status == 401:
            res = await send(await self._access_token(stale=token))
        if res.status == 429:
            self._retry_at = time.monotonic() + _retry_after(res)
            raise SpotifyError(RATE_LIMIT_MESSAGE)
        if res.status >= 300:
            raise _api_error(res)
        return res

    async def _api(
        self, method: str, path: str, query: Mapping[str, str | int] | None = None
    ) -> Any:
        return _parse_json(await self._call(method, path, query))

    async def _ensure_user(self) -> str:
        if self._user_id is None:
            session = self._session
            me = _mapping(await self._api("GET", "/me"))
            user_id = me.get("id")
            if session != self._session or not isinstance(user_id, str) or not user_id:
                raise SpotifyError(OFFLINE_MESSAGE)
            self._user_id = user_id
            name = me.get("display_name")
            self._user = name if isinstance(name, str) and name else user_id
        return self._user_id

    # --------------------------------------------------------------- playlists
    def _playlist(self, raw: dict[str, Any], user_id: str) -> dict[str, Any] | None:
        playlist_id = raw.get("id")
        if not isinstance(playlist_id, str) or not re.fullmatch(PLAYLIST_ID_PATTERN, playlist_id):
            return None
        owner = _mapping(raw.get("owner"))
        # ``items`` es el campo actual; ``tracks`` es el nombre anterior a febrero de 2026.
        total = _mapping(raw.get("items") or raw.get("tracks")).get("total")
        collaborative = raw.get("collaborative") is True
        return {
            "id": playlist_id,
            "uri": f"spotify:playlist:{playlist_id}",
            "name": str(raw.get("name") or "Sin nombre"),
            "description": clean_text(raw.get("description")),
            "owner": str(owner.get("display_name") or owner.get("id") or ""),
            "total": total if isinstance(total, int) else None,
            "public": raw.get("public") if isinstance(raw.get("public"), bool) else None,
            "collaborative": collaborative,
            # Spotify solo entrega las canciones de las playlists propias o colaborativas.
            "readable": owner.get("id") == user_id or collaborative,
            "image": self._image_key(raw.get("images"), PLAYLIST_IMAGE_WIDTH),
        }

    async def playlists(self, offset: int) -> dict[str, Any]:
        user_id = await self._ensure_user()
        query = {"limit": PAGE_SIZE, "offset": offset}
        page = _mapping(await self._api("GET", "/me/playlists", query))
        items = [self._playlist(raw, user_id) for raw in _entries(page)]
        return {
            "items": [item for item in items if item is not None],
            "total": page.get("total"),
            "next_offset": _next_offset(page, offset),
        }

    def _track(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        # ``item`` es el campo actual; ``track`` es el nombre anterior a febrero de 2026.
        item = _mapping(entry.get("item") or entry.get("track"))
        title = item.get("name")
        if not isinstance(title, str) or not title:
            return None
        album = _mapping(item.get("album"))
        artists = [_mapping(a).get("name") for a in item.get("artists") or []]
        names = ", ".join(a for a in artists if isinstance(a, str))
        uri = item.get("uri")
        playable = (
            isinstance(uri, str)
            and re.fullmatch(ITEM_URI_PATTERN, uri) is not None
            and item.get("is_local") is not True
            and item.get("is_playable") is not False
        )
        return {
            "uri": uri if playable else None,  # los archivos locales no se pueden reproducir
            "title": title,
            "artists": names or str(_mapping(item.get("show")).get("name") or ""),
            "album": str(album.get("name") or ""),
            "image": self._image_key(album.get("images") or item.get("images"), TRACK_IMAGE_WIDTH),
        }

    async def playlist_tracks(self, playlist_id: str, offset: int) -> dict[str, Any]:
        query: dict[str, str | int] = {
            "limit": PAGE_SIZE,
            "offset": offset,
            "additional_types": "track,episode",
        }
        try:
            page = _mapping(await self._api("GET", f"/playlists/{playlist_id}/items", query))
        except SpotifyApiError as exc:
            if exc.status in (403, 404):
                return {"available": False, "items": [], "total": None, "next_offset": None}
            raise
        items = [self._track(entry) for entry in _entries(page)]
        return {
            "available": True,
            "items": [item for item in items if item is not None],
            "total": page.get("total"),
            "next_offset": _next_offset(page, offset),
        }

    # ---------------------------------------------------------------- portadas
    def _image_key(self, images: Any, min_width: int) -> str | None:
        url = pick_image(images, min_width)
        if url is None or not self._allow_image(url):
            return None
        key = hashlib.sha256(url.encode("utf-8")).hexdigest()[:32]
        self._image_urls[key] = url
        self._image_urls.move_to_end(key)
        while len(self._image_urls) > MAX_IMAGE_KEYS:
            self._image_urls.popitem(last=False)
        return key

    async def image(self, key: str) -> tuple[bytes, str] | None:
        """Portada de una clave emitida antes, o ``None`` si no existe."""
        cached = self._images.get(key)
        if cached is not None:
            self._images.move_to_end(key)
            return cached
        url = self._image_urls.get(key)
        if url is None or not self._allow_image(url):
            return None
        async with self._downloads:
            res = await self._fetch("GET", url, limit=MAX_IMAGE_BYTES)
        mime = res.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if res.status != 200 or mime not in IMAGE_TYPES:
            return None
        if key not in self._images:
            self._images[key] = (res.body, mime)
            self._image_bytes += len(res.body)
        while self._image_bytes > MAX_IMAGE_CACHE_BYTES:
            _, (data, _mime) = self._images.popitem(last=False)
            self._image_bytes -= len(data)
        return res.body, mime

    # ---------------------------------------------------------------- órdenes
    async def _command(self, method: str, path: str, body: dict[str, Any] | None = None) -> None:
        """Aplica una orden después de las anteriores, sin acumular si Spotify no responde."""
        if self._queued_commands >= MAX_QUEUED_COMMANDS:
            raise SpotifyError(BUSY_MESSAGE)
        self._queued_commands += 1
        try:
            async with self._command_lock:
                await self._send_command(method, path, body)
        finally:
            self._queued_commands -= 1
        self.poke(AFTER_COMMAND_S)

    async def _send_command(self, method: str, path: str, body: dict[str, Any] | None) -> None:
        try:
            try:
                await self._call(method, path, body=body)
            except SpotifyApiError as exc:
                if not exc.no_device:
                    raise
                await self._call(method, path, {"device_id": await self._device()}, body)
        except SpotifyApiError as exc:
            if exc.status >= 500:
                raise
            if exc.no_device:
                raise SpotifyError(NO_DEVICE_MESSAGE) from exc
            premium = exc.reason == "PREMIUM_REQUIRED"
            raise SpotifyError(PREMIUM_MESSAGE if premium else COMMAND_REFUSED_MESSAGE) from exc

    async def _device(self) -> str:
        data = _mapping(await self._api("GET", "/me/player/devices"))
        devices = data.get("devices")
        device = pick_device([d for d in devices if isinstance(d, dict)] if devices else [])
        if device is None:
            raise SpotifyError(NO_DEVICE_MESSAGE)
        return device

    async def control(self, action: MediaAction) -> None:
        method, path = PLAYER_COMMANDS[action]
        await self._command(method, path)

    async def play(self, context: str, track: str | None) -> None:
        """Reproduce una playlist, desde el principio o desde una de sus canciones."""
        body: dict[str, Any] = {"context_uri": context}
        if track is not None:
            body["offset"] = {"uri": track}
        await self._command("PUT", "/me/player/play", body)

    async def open_playlist(self, backend: PlatformBackend, uri: str) -> None:
        """Abre la playlist en la app de la PC; sin la app, en el navegador de la PC."""
        allowed = self._store.settings.allowed_url_schemes
        if "spotify" in allowed:
            try:
                await backend.open_uri(uri)
                return
            except PlatformError:
                log.info("La app de Spotify no abrió la playlist: se usa el navegador")
        if "https" not in allowed:
            raise SpotifyError(SCHEME_BLOCKED_MESSAGE)
        await backend.open_uri("https://open.spotify.com/playlist/" + uri.rsplit(":", 1)[1])

    # ------------------------------------------------------------------- bucle
    def _parse_player(self, raw: Any) -> dict[str, Any] | None:
        state = _mapping(raw)
        if not state:
            return None  # 204: ningún dispositivo está reproduciendo
        # Sin ``item`` sigue habiendo reproducción (un anuncio): los controles deben seguir.
        item = _mapping(state.get("item"))
        album = _mapping(item.get("album"))
        artists = [_mapping(a).get("name") for a in item.get("artists") or []]
        names = ", ".join(a for a in artists if isinstance(a, str))
        return {
            "playing": state.get("is_playing") is True,
            "title": str(item.get("name") or "Spotify"),
            "artists": names or str(_mapping(item.get("show")).get("name") or ""),
            "device": str(_mapping(state.get("device")).get("name") or ""),
            "image": self._image_key(album.get("images") or item.get("images"), TRACK_IMAGE_WIDTH),
        }

    async def _poll(self) -> float:
        """Actualiza el estado y devuelve cuánto esperar hasta la siguiente consulta."""
        delay = POLL_S
        settings = self._store.settings
        if settings.spotify_client_id and settings.spotify_refresh_token:
            session = self._session
            try:
                await self._ensure_user()
                raw = await self._api("GET", "/me/player", {"additional_types": "episode"})
            except SpotifyAuthError:
                pass  # _access_token ya dejó el estado en "caducada"
            except SpotifyError as exc:
                if session == self._session:
                    forbidden = isinstance(exc, SpotifyApiError) and exc.status == 403
                    status = SpotifyStatus.FORBIDDEN if forbidden else SpotifyStatus.OFFLINE
                    self._set_status(status, str(exc))
                    self._failures = min(self._failures + 1, MAX_BACKOFF_STEPS)
                    delay = min(MAX_RETRY_S, POLL_S * 2**self._failures)
            else:
                if session == self._session:
                    self._set_status(SpotifyStatus.ONLINE)
                    self._player = self._parse_player(raw)
                    self._failures = 0
        await self._publish()
        return max(delay, self._retry_at - time.monotonic())

    async def run(self) -> None:
        while True:
            watching = self.hub.subscribers(TOPIC) > 0
            if watching and time.monotonic() >= self._next_poll:
                try:
                    delay = await self._poll()
                except Exception:
                    log.exception("Error consultando Spotify")
                    delay = MAX_RETRY_S
                self._next_poll = time.monotonic() + delay
            remaining = self._next_poll - time.monotonic()
            await self.hub.wait_for_change(max(0.05, remaining) if watching else WAIT_IDLE_S)


async def spotify_service(state: Any) -> None:
    await state.spotify.run()
