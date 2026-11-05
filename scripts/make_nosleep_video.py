"""Genera ``web/media/nosleep.webm``: vídeo mudo y diminuto para mantener la pantalla encendida.

Chrome 60 (Android 7/8) no tiene la Wake Lock API. Un ``<video>`` reproduciéndose en bucle
evita que la pantalla se apague (técnica "NoSleep"). Para no depender de ffmpeg ni de
archivos de terceros, el vídeo se graba con el propio Chrome en modo headless
(canvas → MediaRecorder VP8) a través del protocolo DevTools.

Uso:  python scripts/make_nosleep_video.py [ruta\\a\\chrome.exe]
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import websockets

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "web" / "media" / "nosleep.webm"
PORT = 9333

CANDIDATES = [
    r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
    r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
    r"%ProgramFiles%\BraveSoftware\Brave-Browser\Application\brave.exe",
]

# Graba 2 s de un canvas 32x32 casi negro a 4 fps con bitrate mínimo.
RECORD_JS = """
new Promise(function (resolve, reject) {
  var c = document.createElement('canvas'); c.width = 32; c.height = 32;
  var g = c.getContext('2d'); var n = 0;
  var stream = c.captureStream(4);
  var rec = new MediaRecorder(stream, {mimeType: 'video/webm;codecs=vp8', videoBitsPerSecond: 8000});
  var chunks = [];
  rec.ondataavailable = function (e) { if (e.data.size) chunks.push(e.data); };
  rec.onerror = function (e) { reject(String(e.error)); };
  rec.onstop = function () {
    var fr = new FileReader();
    fr.onload = function () { resolve(fr.result.split(',')[1]); };
    fr.readAsDataURL(new Blob(chunks, {type: 'video/webm'}));
  };
  var t = setInterval(function () { n++; g.fillStyle = n % 2 ? '#000' : '#010101'; g.fillRect(0, 0, 32, 32); }, 250);
  rec.start();
  setTimeout(function () { clearInterval(t); rec.stop(); }, 2000);
})
"""


def find_browser(arg: str | None) -> str:
    for cand in [arg, *CANDIDATES]:
        if cand:
            path = os.path.expandvars(cand)
            if Path(path).is_file():
                return path
    found = shutil.which("chrome") or shutil.which("chromium")
    if not found:
        sys.exit("No se encontró Chrome/Edge/Brave. Pasa la ruta como argumento.")
    return found


async def record(ws_url: str) -> bytes:
    async with websockets.connect(ws_url, max_size=10_000_000) as ws:
        await ws.send(
            json.dumps(
                {
                    "id": 1,
                    "method": "Runtime.evaluate",
                    "params": {
                        "expression": RECORD_JS,
                        "awaitPromise": True,
                        "returnByValue": True,
                    },
                }
            )
        )
        while True:
            msg = json.loads(await ws.recv())
            if msg.get("id") == 1:
                break
    result = msg.get("result", {})
    if "exceptionDetails" in result:
        raise RuntimeError(result["exceptionDetails"])
    return base64.b64decode(result["result"]["value"])


def main() -> None:
    browser = find_browser(sys.argv[1] if len(sys.argv) > 1 else None)
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [
                browser,
                "--headless=new",
                f"--remote-debugging-port={PORT}",
                f"--user-data-dir={profile}",
                "--no-first-run",
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
            if not targets:
                sys.exit("El navegador no expuso el puerto de depuración")
            data = asyncio.run(record(targets[0]["webSocketDebuggerUrl"]))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_bytes(data)
    print(f"Generado {OUT} ({len(data)} bytes)")


if __name__ == "__main__":
    main()
