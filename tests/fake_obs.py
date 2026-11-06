"""Servidor que habla el protocolo de obs-websocket 5, para probar sin OBS instalado.

Sigue la documentación oficial (Hello, Identify con reto SHA-256, cierre 4009, peticiones y
eventos). No sustituye a una prueba con OBS real.
"""

from __future__ import annotations

import base64
import hashlib
import json
from typing import Any

from websockets.asyncio.server import Server, ServerConnection, serve

SALT = "c2FsdA=="
CHALLENGE = "cmV0bw=="


def expected_auth(password: str) -> str:
    secret = base64.b64encode(hashlib.sha256((password + SALT).encode()).digest()).decode()
    digest = hashlib.sha256((secret + CHALLENGE).encode()).digest()
    return base64.b64encode(digest).decode()


class FakeObs:
    def __init__(self, scenes: list[str], password: str = "", port: int = 0) -> None:
        self.scenes = scenes  # en orden visual, de arriba abajo
        self.current = scenes[0] if scenes else None
        self.password = password
        self.port = port
        self.subscriptions: int | None = None
        self.requests: list[str] = []
        self.clients: set[ServerConnection] = set()
        self._server: Server | None = None

    async def start(self) -> None:
        self._server = await serve(
            self._handle, "127.0.0.1", self.port, subprotocols=["obswebsocket.json"]
        )
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()
            self._server = None

    async def _send(self, ws: ServerConnection, op: int, data: dict[str, Any]) -> None:
        await ws.send(json.dumps({"op": op, "d": data}))

    async def emit(self, kind: str, data: dict[str, Any] | None = None) -> None:
        for ws in list(self.clients):
            await self._send(ws, 5, {"eventType": kind, "eventIntent": 4, "eventData": data or {}})

    async def switch(self, name: str) -> None:
        """Cambio de escena hecho en OBS."""
        self.current = name
        await self.emit("CurrentProgramSceneChanged", {"sceneName": name, "sceneUuid": "x"})

    async def _handle(self, ws: ServerConnection) -> None:
        hello: dict[str, Any] = {"obsWebSocketVersion": "5.5.0", "rpcVersion": 1}
        if self.password:
            hello["authentication"] = {"challenge": CHALLENGE, "salt": SALT}
        await self._send(ws, 0, hello)
        identify = json.loads(await ws.recv())
        if self.password and identify["d"].get("authentication") != expected_auth(self.password):
            await ws.close(4009, "Authentication failed.")
            return
        self.subscriptions = identify["d"]["eventSubscriptions"]
        await self._send(ws, 2, {"negotiatedRpcVersion": 1})
        self.clients.add(ws)
        try:
            async for raw in ws:
                await self._on_request(ws, json.loads(raw)["d"])
        finally:
            self.clients.discard(ws)

    async def _on_request(self, ws: ServerConnection, request: dict[str, Any]) -> None:
        kind = request["requestType"]
        self.requests.append(kind)
        response: dict[str, Any] = {
            "requestType": kind,
            "requestId": request["requestId"],
            "requestStatus": {"result": True, "code": 100},
        }
        if kind == "GetSceneList":
            count = len(self.scenes)
            scenes = [
                {"sceneIndex": count - 1 - i, "sceneName": name, "sceneUuid": str(i)}
                for i, name in enumerate(self.scenes)
            ]
            response["responseData"] = {
                "currentProgramSceneName": self.current,
                "currentProgramSceneUuid": "x",
                "currentPreviewSceneName": None,
                "currentPreviewSceneUuid": None,
                "scenes": list(reversed(scenes)),
            }
        elif kind == "SetCurrentProgramScene":
            name = request["requestData"]["sceneName"]
            if name in self.scenes:
                await self._send(ws, 7, response)
                await self.switch(name)
                return
            response["requestStatus"] = {"result": False, "code": 600}
        await self._send(ws, 7, response)
