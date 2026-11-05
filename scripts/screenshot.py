"""Capturas de la interfaz emulando un celular (Chrome headless + DevTools Protocol).

Sirve para revisar el diseño sin el teléfono y para generar las imágenes de docs/.
Por defecto emula un Xiaomi Redmi 5 Plus (393x786 CSS px, DPR 2.75).

Uso:
    python scripts/screenshot.py salida.png [--url http://127.0.0.1:8765/] [--landscape]
                                 [--js "código a ejecutar antes de capturar"] [--wait 2.5]
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path
from typing import Any

import websockets

PORT = 9334
UA = (
    "Mozilla/5.0 (Linux; Android 8.1.0; Redmi 5 Plus) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/60.0.3112.116 Mobile Safari/537.36"
)
CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
]


def find_browser() -> str:
    for cand in CANDIDATES:
        path = os.path.expandvars(cand)
        if Path(path).is_file():
            return path
    found = shutil.which("chrome") or shutil.which("chromium")
    if not found:
        raise SystemExit("No se encontró Chrome/Edge/Brave")
    return found


class Cdp:
    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.next_id = 0

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.next_id += 1
        my_id = self.next_id
        await self.ws.send(json.dumps({"id": my_id, "method": method, "params": params}))
        while True:
            msg = json.loads(await self.ws.recv())
            if msg.get("id") == my_id:
                if "error" in msg:
                    raise RuntimeError(f"{method}: {msg['error']}")
                result: dict[str, Any] = msg.get("result", {})
                return result


async def capture(ws_url: str, args: argparse.Namespace) -> bytes:
    width, height = (int(v) for v in args.size.lower().split("x"))
    if args.landscape and height > width:
        width, height = height, width
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        cdp = Cdp(ws)
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            width=width,
            height=height,
            deviceScaleFactor=args.dpr,
            mobile=True,
            screenOrientation={
                "type": "landscapePrimary" if args.landscape else "portraitPrimary",
                "angle": 90 if args.landscape else 0,
            },
        )
        await cdp.call("Emulation.setTouchEmulationEnabled", enabled=True, maxTouchPoints=5)
        await cdp.call("Network.enable")
        await cdp.call("Network.setUserAgentOverride", userAgent=UA)
        await cdp.call("Page.enable")
        await cdp.call("Page.navigate", url=args.url)
        await asyncio.sleep(args.wait)
        if args.js:
            await cdp.call("Runtime.evaluate", expression=args.js, awaitPromise=True)
            await asyncio.sleep(0.8)
        shot = await cdp.call("Page.captureScreenshot", format="png")
        return base64.b64decode(shot["data"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--url", default="http://127.0.0.1:8765/")
    parser.add_argument("--landscape", action="store_true")
    parser.add_argument(
        "--size", default="393x786", help="Ancho x alto en px CSS (393x786 = Redmi 5 Plus)"
    )
    parser.add_argument("--js", default="")
    parser.add_argument("--wait", type=float, default=2.5)
    parser.add_argument("--dpr", type=float, default=1.0, help="2.75 = densidad real del Redmi")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [
                find_browser(),
                "--headless=new",
                f"--remote-debugging-port={PORT}",
                f"--user-data-dir={profile}",
                "--no-first-run",
                "--hide-scrollbars",
                "about:blank",
            ]
        )
        try:
            targets: list[dict[str, str]] = []
            for _ in range(50):
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{PORT}/json") as res:
                        targets = [t for t in json.load(res) if t.get("type") == "page"]
                    if targets:
                        break
                except OSError:
                    pass
                time.sleep(0.2)
            png = asyncio.run(capture(targets[0]["webSocketDebuggerUrl"], args))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    args.output.write_bytes(png)
    print(f"Captura guardada en {args.output}")


if __name__ == "__main__":
    main()
