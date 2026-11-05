"""Servicio "ahora suena": sesión multimedia de Windows (título, artista, portada, estado)."""

from __future__ import annotations

import asyncio
import io
import re
import time
from typing import Any

from phonedeck.platform.base import MediaInfo
from phonedeck.services.base import Poller
from phonedeck.state import Artwork

# Si la posición real se aleja más que esto de la estimada, se reenvía (el usuario buscó).
SEEK_THRESHOLD_S = 3.0
# Lado máximo de la portada enviada al celular (el widget la muestra a <= 160 px CSS).
ARTWORK_MAX_PX = 320


def sniff_image_mime(data: bytes) -> str:
    if data.startswith(b"\x89PNG"):
        return "image/png"
    if data.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    return "image/jpeg"


def optimize_artwork(data: bytes) -> tuple[bytes, str]:
    """Reduce la portada a JPEG de como mucho ``ARTWORK_MAX_PX`` px.

    Windows suele entregar PNG de ~30 KB; un JPEG de 320 px pesa bastante menos y lo
    entiende cualquier navegador (WebP no funciona en iPhone antiguos). Si el resultado
    no es más pequeño o la imagen no se puede leer, se conserva el original.
    """
    from PIL import Image, UnidentifiedImageError

    original_mime = sniff_image_mime(data)
    try:
        with Image.open(io.BytesIO(data)) as src:
            src.load()
            img: Image.Image = src
            if img.mode not in ("RGB", "L"):
                # Fondo oscuro como el del panel para las portadas con transparencia.
                background = Image.new("RGB", img.size, (26, 29, 36))
                background.paste(img, mask=img.convert("RGBA").split()[-1])
                img = background
            img.thumbnail((ARTWORK_MAX_PX, ARTWORK_MAX_PX), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            img.convert("RGB").save(out, format="JPEG", quality=82, optimize=True, progressive=True)
    except (UnidentifiedImageError, OSError, ValueError):
        return data, original_mime
    optimized = out.getvalue()
    if len(optimized) >= len(data):
        return data, original_mime
    return optimized, "image/jpeg"


def friendly_app_name(app_id: str) -> str:
    """'SpotifyAB.SpotifyMusic_zpdnekdrzrea0!Spotify' → 'Spotify'; 'chrome.exe' → 'Chrome'."""
    name = app_id.split("!")[-1]
    name = re.sub(r"\.exe$", "", name, flags=re.IGNORECASE)
    if "." in name:
        name = name.split("_")[0].split(".")[-1]
    return name[:1].upper() + name[1:] if name else ""


def media_payload(info: MediaInfo | None) -> dict[str, Any] | None:
    """Mensaje ``media`` para el celular (``None`` = nada sonando)."""
    if info is None or not (info.title or info.artist):
        return None
    return {
        "title": info.title,
        "artist": info.artist,
        "album": info.album,
        "app": friendly_app_name(info.app_id),
        "status": info.status,
        "position": round(info.position_s, 1) if info.position_s is not None else None,
        "duration": round(info.duration_s, 1) if info.duration_s else None,
        "artwork": f"/api/media/artwork?h={info.artwork_hash}" if info.artwork_hash else None,
    }


class NowPlayingService(Poller):
    name = "now_playing"
    topic = "media"
    interval = 1.0
    idle_interval = 4.0

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._key: tuple[Any, ...] | None = None
        self._sent_at = 0.0
        self._sent_position: float | None = None
        self._first = True

    def _position_jumped(self, payload: dict[str, Any]) -> bool:
        pos = payload.get("position")
        if pos is None or self._sent_position is None:
            return False
        expected = self._sent_position
        if payload["status"] == "playing":
            expected += time.monotonic() - self._sent_at
        return bool(abs(float(pos) - expected) > SEEK_THRESHOLD_S)

    async def tick(self) -> None:
        info = await self.state.backend.get_now_playing()
        if info is not None and info.artwork and info.artwork_hash:
            current = self.state.live.artwork
            if current is None or current.hash != info.artwork_hash:
                # Una vez por canción, en otro hilo (Pillow no debe bloquear el bucle).
                data, mime = await asyncio.to_thread(optimize_artwork, info.artwork)
                self.state.live.artwork = Artwork(info.artwork_hash, data, mime)
        payload = media_payload(info)
        key = (
            None
            if payload is None
            else (
                payload["title"],
                payload["artist"],
                payload["album"],
                payload["status"],
                payload["artwork"],
                payload["duration"],
            )
        )
        changed = self._first or key != self._key
        if not changed and payload is not None and self._position_jumped(payload):
            changed = True
        if not changed:
            return
        self._first = False
        self._key = key
        self._sent_at = time.monotonic()
        self._sent_position = payload.get("position") if payload else None
        if payload is None:
            self.state.live.artwork = None
        await self.state.hub.broadcast("media", payload)


async def now_playing_service(state: Any) -> None:
    await NowPlayingService(state).run()
