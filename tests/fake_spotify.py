"""Spotify simulado para las pruebas: cuentas, Web API y portadas sobre HTTP real.

Reproduce la forma de las respuestas posterior a febrero de 2026 (``items`` en vez de
``tracks``) y los errores que importan: 401, 403, 404 sin dispositivo y 429.
"""

from __future__ import annotations

import base64
import hashlib
import json
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlencode, urlsplit

ME = "demo"
JPEG = b"\xff\xd8\xff\xe0imagen"


def image(url: str, width: int = 300) -> dict[str, Any]:
    return {"url": url, "width": width, "height": width}


def playlist(
    playlist_id: str, owner: str = ME, total: int | None = 2, **extra: Any
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": playlist_id,
        "name": f"Playlist {playlist_id}",
        "description": "",
        "owner": {"id": owner, "display_name": owner.title()},
        "collaborative": False,
        "public": True,
        "images": [],
    }
    if total is not None:
        data["items"] = {"total": total}
    return data | extra


def track(track_id: str, title: str = "", **extra: Any) -> dict[str, Any]:
    item = {
        "type": "track",
        "uri": f"spotify:track:{track_id}",
        "name": title or f"Canción {track_id}",
        "artists": [{"name": "Artista"}],
        "album": {"name": "Álbum", "images": []},
    }
    return {"added_at": "2026-01-01T00:00:00Z", "item": item | extra}


class FakeSpotify:
    def __init__(self) -> None:
        self.playlists: list[dict[str, Any]] = [playlist("propia"), playlist("seguida", "spotify")]
        self.items: dict[str, list[dict[str, Any] | None]] = {"propia": [track("a1"), track("a2")]}
        self.player: dict[str, Any] | None = None
        self.devices: list[dict[str, Any]] = []
        self.active_device = True
        self.client_id = "0123456789abcdef0123456789abcdef"
        self.refresh_token = "refresh-1"
        self.access_token = "access-1"
        self.rotate = False
        self.expires_in = 3600
        self.reject_refresh = False
        self.reject_access_once = False
        self.me_status = 200
        self.rate_limited: int | None = None
        self.premium = True
        self.command_failure: tuple[int, dict[str, Any]] | None = None
        self.command_text: bytes | None = None
        self.image_status = 200
        self.image_type = "image/jpeg"
        self.image_body = JPEG
        self.image_redirect: str | None = None
        self.calls: list[str] = []  # "GET /v1/me/player"
        self.commands: list[tuple[str, str, Any]] = []
        self.content_types: list[str] = []
        self.tokens_requested = 0
        self.last_challenge = ""
        self._server: ThreadingHTTPServer | None = None

    # -------------------------------------------------------------- servidor
    def start(self, port: int = 0) -> None:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args: Any) -> None:
                return None

            def reply(
                self, status: int, body: Any = None, headers: dict[str, str] | None = None
            ) -> None:
                data = b"" if body is None else json.dumps(body).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                for key, value in (headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                self.wfile.write(data)

            def do_request(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                fake.handle(self, self.command, self.path, body)

            do_GET = do_POST = do_PUT = do_request

        self._server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
        threading.Thread(
            target=self._server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True
        ).start()

    def stop(self) -> None:
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None

    @property
    def port(self) -> int:
        assert self._server is not None
        return int(self._server.server_address[1])

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def api_url(self) -> str:
        return f"{self.url}/v1"

    # ----------------------------------------------------------------- rutas
    def handle(self, http: Any, method: str, target: str, body: bytes) -> None:
        parts = urlsplit(target)
        path = parts.path
        query = {k: v[0] for k, v in parse_qs(parts.query).items()}
        if path == "/authorize":
            self.authorize(http, query)
        elif path == "/api/token":
            self.token(http, {k: v[0] for k, v in parse_qs(body.decode()).items()})
        elif path.startswith("/img/"):
            self.serve_image(http)
        else:
            self.calls.append(f"{method} {path}")
            self.api(http, method, path, query, body)

    def authorize(self, http: Any, query: dict[str, str]) -> None:
        """Simula que el usuario acepta en la página de Spotify."""
        self.last_challenge = query.get("code_challenge", "")
        back = urlencode({"code": "codigo", "state": query.get("state", "")})
        http.send_response(302)
        http.send_header("Location", f"{query['redirect_uri']}?{back}")
        http.send_header("Content-Length", "0")
        http.end_headers()

    def token(self, http: Any, form: dict[str, str]) -> None:
        self.tokens_requested += 1
        if form.get("client_id") != self.client_id:
            http.reply(400, {"error": "invalid_client"})
            return
        if form.get("grant_type") == "authorization_code":
            verifier = form.get("code_verifier", "")
            digest = hashlib.sha256(verifier.encode()).digest()
            challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
            if form.get("code") != "codigo" or challenge != self.last_challenge:
                http.reply(400, {"error": "invalid_grant"})
                return
            http.reply(200, self.token_body(with_refresh=True))
            return
        if self.reject_refresh or form.get("refresh_token") != self.refresh_token:
            http.reply(
                400, {"error": "invalid_grant", "error_description": "Refresh token revoked"}
            )
            return
        self.access_token = f"access-{self.tokens_requested + 1}"
        if self.rotate:
            self.refresh_token = f"refresh-{self.tokens_requested + 1}"
        http.reply(200, self.token_body(with_refresh=self.rotate))

    def token_body(self, *, with_refresh: bool) -> dict[str, Any]:
        body: dict[str, Any] = {
            "access_token": self.access_token,
            "token_type": "Bearer",
            "expires_in": self.expires_in,
        }
        if with_refresh:
            body["refresh_token"] = self.refresh_token
        return body

    def serve_image(self, http: Any) -> None:
        http.send_response(302 if self.image_redirect else self.image_status)
        if self.image_redirect:
            http.send_header("Location", self.image_redirect)
        http.send_header("Content-Type", self.image_type)
        http.send_header("Content-Length", str(len(self.image_body)))
        http.end_headers()
        http.wfile.write(self.image_body)

    def api(self, http: Any, method: str, path: str, query: dict[str, str], raw: bytes) -> None:
        if self.reject_access_once:
            self.reject_access_once = False
            http.reply(401, {"error": {"status": 401, "message": "The access token expired"}})
            return
        if http.headers.get("Authorization") != f"Bearer {self.access_token}":
            http.reply(401, {"error": {"status": 401, "message": "Invalid access token"}})
            return
        if self.rate_limited is not None:
            http.reply(429, {"error": {"status": 429}}, {"Retry-After": str(self.rate_limited)})
            return
        match = re.fullmatch(r"/v1/playlists/([^/]+)/items", path)
        if path == "/v1/me":
            status = self.me_status
            http.reply(
                status, {"id": ME, "display_name": "Demo"} if status == 200 else {"error": {}}
            )
        elif path == "/v1/me/playlists":
            self.page(http, self.playlists, query)
        elif match:
            items = self.items.get(match.group(1))
            if items is None:
                http.reply(403, {"error": {"status": 403, "message": "Forbidden"}})
            else:
                self.page(http, items, query)
        elif path == "/v1/me/player" and method == "GET":
            http.reply(204 if self.player is None else 200, self.player_state(query))
        elif path == "/v1/me/player/devices":
            http.reply(200, {"devices": self.devices})
        else:
            self.command(http, method, path, query, raw)

    def player_state(self, query: dict[str, str]) -> dict[str, Any] | None:
        """Sin ``additional_types=episode``, Spotify devuelve ``item: null`` con un podcast."""
        state = self.player
        item = (state or {}).get("item") or {}
        if item.get("type") == "episode" and "episode" not in query.get("additional_types", ""):
            return (state or {}) | {"item": None}
        return state

    def command(self, http: Any, method: str, path: str, query: dict[str, str], raw: bytes) -> None:
        if not self.premium:
            http.reply(403, {"error": {"status": 403, "reason": "PREMIUM_REQUIRED"}})
            return
        if self.command_failure is not None:
            status, error = self.command_failure
            http.reply(status, {"error": {"status": status} | error})
            return
        if not self.active_device and "device_id" not in query:
            http.reply(404, {"error": {"status": 404, "reason": "NO_ACTIVE_DEVICE"}})
            return
        device = query.get("device_id", "")
        self.content_types.append(http.headers.get("Content-Type", ""))
        self.commands.append((f"{method} {path}", device, json.loads(raw) if raw else None))
        if self.command_text is not None:
            http.send_response(200)
            http.send_header("Content-Length", str(len(self.command_text)))
            http.end_headers()
            http.wfile.write(self.command_text)
            return
        http.reply(204)

    def page(self, http: Any, items: list[Any], query: dict[str, str]) -> None:
        limit = int(query.get("limit", 20))
        offset = int(query.get("offset", 0))
        chunk = items[offset : offset + limit]
        more = offset + limit < len(items)
        http.reply(
            200,
            {
                "items": chunk,
                "total": len(items),
                "limit": limit,
                "offset": offset,
                "next": "siguiente" if more else None,
            },
        )
