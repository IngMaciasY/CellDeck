"""Puente con OBS Studio por obs-websocket 5 (incluido en OBS desde la versión 28).

El celular nunca habla con OBS: habla con PhoneDeck por su WebSocket de siempre y este puente
habla con OBS. Por eso la contraseña no sale de la PC, OBS no necesita exponerse a la red, y
funciona igual por USB (donde ``adb reverse`` solo reenvía el puerto de PhoneDeck) y por WiFi
(donde el navegador, en HTTP, no tendría SHA-256 para autenticarse).

Alcance: leer las escenas y cambiar de escena. El puente no reenvía peticiones arbitrarias.

La conexión es bajo demanda: se abre cuando alguien mira la sección, se recupera sola si OBS
se cierra o se reinicia, y se cierra tras un minuto sin nadie mirando.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
import uuid
from collections.abc import Callable
from enum import StrEnum
from typing import Any

from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed, WebSocketException
from websockets.typing import Subprotocol

from phonedeck.config.settings import Settings
from phonedeck.platform.base import PlatformError
from phonedeck.ws import WebSocketHub

log = logging.getLogger(__name__)

TOPIC = "obs"
SUBPROTOCOL = Subprotocol("obswebsocket.json")
RPC_VERSION = 1
OP_HELLO, OP_IDENTIFY, OP_IDENTIFIED, OP_EVENT, OP_REQUEST, OP_RESPONSE = 0, 1, 2, 5, 6, 7
EVENTS_CONFIG = 1 << 1  # cambio de colección de escenas
EVENTS_SCENES = 1 << 2
CLOSE_AUTH_FAILED = 4009

# Eventos que pueden cambiar la lista de escenas: se vuelve a pedir entera.
LIST_EVENTS = frozenset(
    {
        "SceneListChanged",
        "SceneCreated",
        "SceneRemoved",
        "SceneNameChanged",
        "CurrentSceneCollectionChanged",
    }
)

CONNECT_TIMEOUT_S = 5.0
REQUEST_TIMEOUT_S = 5.0
MIN_RETRY_S = 2.0
MAX_RETRY_S = 30.0
IDLE_CLOSE_S = 60.0  # sin nadie mirando, se cierra la conexión pasado este tiempo
READ_CHECK_S = 5.0
WAIT_IDLE_S = 30.0

CONNECTING_MESSAGE = "Conectando con OBS…"
OFFLINE_MESSAGE = "OBS no está abierto o su servidor WebSocket está apagado"
AUTH_REJECTED_MESSAGE = "OBS rechazó la contraseña"
AUTH_MISSING_MESSAGE = "OBS pide contraseña y no hay ninguna guardada"


class ObsStatus(StrEnum):
    CONNECTING = "connecting"
    ONLINE = "online"
    OFFLINE = "offline"
    AUTH_FAILED = "auth_failed"


class ObsError(PlatformError):
    """Error apto para mostrar en el celular."""


class ObsAuthError(Exception):
    """OBS no aceptó la autenticación. No es un corte: reintentar no lo arregla."""


def auth_response(password: str, salt: str, challenge: str) -> str:
    """Respuesta al reto de autenticación de obs-websocket 5."""
    secret = base64.b64encode(hashlib.sha256((password + salt).encode("utf-8")).digest())
    answer = hashlib.sha256(secret + challenge.encode("utf-8")).digest()
    return base64.b64encode(answer).decode("ascii")


def scene_names(scenes: list[dict[str, Any]]) -> list[str]:
    """Nombres en el orden visual de OBS: la lista llega de abajo arriba."""
    ordered = sorted(scenes, key=lambda s: s.get("sceneIndex", 0), reverse=True)
    return [s["sceneName"] for s in ordered if isinstance(s.get("sceneName"), str)]


class ObsBridge:
    def __init__(self, hub: WebSocketHub, settings: Callable[[], Settings]) -> None:
        self.hub = hub
        self._settings = settings
        self._ws: ClientConnection | None = None
        self._status = ObsStatus.CONNECTING
        self._message = CONNECTING_MESSAGE
        self._scenes: list[str] = []
        self._current: str | None = None
        self._pending: dict[str, asyncio.Future[dict[str, Any]]] = {}
        self._reached_online = False
        self._settings_changed = False
        self._last_wanted = 0.0
        self._published: dict[str, Any] | None = None

    # ---------------------------------------------------------------- publicar
    def payload(self) -> dict[str, Any]:
        return {
            "status": self._status.value,
            "message": self._message,
            "scenes": self._scenes,
            "current": self._current,
        }

    async def _publish(self) -> None:
        payload = self.payload()
        if payload != self._published:
            self._published = payload
            await self.hub.broadcast(TOPIC, payload)

    async def _set_status(self, status: ObsStatus, message: str = "") -> None:
        self._status = status
        self._message = message
        if status is not ObsStatus.ONLINE:
            self._scenes = []
            self._current = None
        await self._publish()

    # ---------------------------------------------------------------- órdenes
    async def set_scene(self, name: str) -> None:
        ws = self._ws
        if ws is None or self._status is not ObsStatus.ONLINE:
            raise ObsError("OBS no está conectado")
        if name not in self._scenes:
            raise ObsError("Esa escena ya no existe en OBS")
        request_id = uuid.uuid4().hex
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = future
        try:
            await self._send_request(ws, "SetCurrentProgramScene", request_id, {"sceneName": name})
            async with asyncio.timeout(REQUEST_TIMEOUT_S):
                status = await future
        except (TimeoutError, ConnectionClosed) as exc:
            raise ObsError("OBS no respondió") from exc
        finally:
            self._pending.pop(request_id, None)
        if not status.get("result"):
            raise ObsError("OBS no pudo cambiar de escena")

    async def reconnect(self) -> None:
        """Vuelve a conectar ya, con los ajustes actuales (acaban de cambiar)."""
        self._settings_changed = True
        if self._ws is not None:
            await self._ws.close()
        self.hub.wake()

    # ----------------------------------------------------------------- bucle
    def _wanted(self) -> bool:
        if self.hub.subscribers(TOPIC) > 0:
            self._last_wanted = time.monotonic()
            return True
        return False

    def _abandoned(self) -> bool:
        return not self._wanted() and time.monotonic() - self._last_wanted >= IDLE_CLOSE_S

    async def run(self) -> None:
        delay = MIN_RETRY_S
        while True:
            if not self._wanted():
                await self.hub.wait_for_change(WAIT_IDLE_S)
                continue
            self._reached_online = False
            self._settings_changed = False
            try:
                await self._session()
                delay = MIN_RETRY_S
                continue
            except ObsAuthError as exc:
                await self._set_status(ObsStatus.AUTH_FAILED, str(exc))
            except (
                OSError,
                TimeoutError,
                WebSocketException,
                ValueError,
                KeyError,
                TypeError,
                AttributeError,  # JSON con otra forma: en ese puerto puede haber otro servicio
            ):
                log.debug("Sin conexión con OBS", exc_info=True)
                await self._set_status(ObsStatus.OFFLINE, OFFLINE_MESSAGE)
            if self._settings_changed:
                continue  # el intento fallido usaba los ajustes viejos
            delay = MIN_RETRY_S if self._reached_online else min(MAX_RETRY_S, delay * 2)
            # Un celular que entra a la sección o unos ajustes nuevos cortan la espera.
            await self.hub.wait_for_change(delay)

    async def _session(self) -> None:
        settings = self._settings()
        # Tras un fallo se mantiene el aviso mientras se reintenta: así no parpadea.
        if self._status is ObsStatus.ONLINE:
            await self._set_status(ObsStatus.CONNECTING, CONNECTING_MESSAGE)
        async with connect(
            f"ws://{settings.obs_host}:{settings.obs_port}",
            subprotocols=[SUBPROTOCOL],
            open_timeout=CONNECT_TIMEOUT_S,
            close_timeout=2,
            compression=None,
            proxy=None,
        ) as ws:
            await self._identify(ws, settings.obs_password)
            if self._settings_changed:
                return  # los ajustes cambiaron mientras se conectaba
            self._ws = ws
            self._reached_online = True
            log.info("Conectado a OBS en %s:%d", settings.obs_host, settings.obs_port)
            try:
                await self._request_scenes(ws)
                await self._read_loop(ws)
            finally:
                self._ws = None
                for future in self._pending.values():
                    if not future.done():
                        future.set_result({"result": False})
        await self._set_status(ObsStatus.CONNECTING, CONNECTING_MESSAGE)

    @staticmethod
    async def _identify(ws: ClientConnection, password: str) -> None:
        async with asyncio.timeout(CONNECT_TIMEOUT_S):
            hello = json.loads(await ws.recv())
            if hello.get("op") != OP_HELLO:
                raise ValueError("OBS no envió Hello")
            identify: dict[str, Any] = {
                "rpcVersion": RPC_VERSION,
                "eventSubscriptions": EVENTS_CONFIG | EVENTS_SCENES,
            }
            challenge = hello["d"].get("authentication")
            if challenge:
                if not password:
                    raise ObsAuthError(AUTH_MISSING_MESSAGE)
                identify["authentication"] = auth_response(
                    password, challenge["salt"], challenge["challenge"]
                )
            await ws.send(json.dumps({"op": OP_IDENTIFY, "d": identify}))
            try:
                identified = json.loads(await ws.recv())
            except ConnectionClosed as exc:
                if exc.rcvd is not None and exc.rcvd.code == CLOSE_AUTH_FAILED:
                    raise ObsAuthError(AUTH_REJECTED_MESSAGE) from exc
                raise
            if identified.get("op") != OP_IDENTIFIED:
                raise ValueError("OBS no confirmó la conexión")

    @staticmethod
    async def _send_request(
        ws: ClientConnection, kind: str, request_id: str, data: dict[str, Any] | None = None
    ) -> None:
        body: dict[str, Any] = {"requestType": kind, "requestId": request_id}
        if data is not None:
            body["requestData"] = data
        await ws.send(json.dumps({"op": OP_REQUEST, "d": body}))

    async def _request_scenes(self, ws: ClientConnection) -> None:
        await self._send_request(ws, "GetSceneList", uuid.uuid4().hex)

    async def _read_loop(self, ws: ClientConnection) -> None:
        while True:
            try:
                async with asyncio.timeout(READ_CHECK_S):
                    raw = await ws.recv()
            except TimeoutError:
                if self._abandoned():
                    return
                continue
            message = json.loads(raw)
            if message.get("op") == OP_EVENT:
                await self._on_event(ws, message["d"])
            elif message.get("op") == OP_RESPONSE:
                await self._on_response(message["d"])

    async def _on_event(self, ws: ClientConnection, event: dict[str, Any]) -> None:
        kind = event.get("eventType")
        if kind == "CurrentProgramSceneChanged":
            self._current = event["eventData"]["sceneName"]
            await self._publish()
        elif kind in LIST_EVENTS:
            await self._request_scenes(ws)

    async def _on_response(self, response: dict[str, Any]) -> None:
        future = self._pending.get(response.get("requestId", ""))
        if future is not None:
            if not future.done():
                future.set_result(response.get("requestStatus", {}))
            return
        if response.get("requestType") == "GetSceneList":
            if not response.get("requestStatus", {}).get("result"):
                raise ValueError("OBS no entregó las escenas")  # p. ej. aún está cargando
            data = response.get("responseData") or {}
            self._scenes = scene_names(data.get("scenes") or [])
            self._current = data.get("currentProgramSceneName")
            await self._set_status(ObsStatus.ONLINE)


async def obs_service(state: Any) -> None:
    await state.obs.run()
