"""Mide el rendimiento del panel en un "celular viejo" emulado (Chrome headless + DevTools).

- Emulación móvil 393x786 y CPU frenada x4 (aprox. un Redmi 5 Plus).
- Primera carga y recarga: nº de peticiones, bytes transferidos y respuestas 304.
- Ventana en reposo de N segundos: mensajes WebSocket, mutaciones del DOM y tiempo de
  CPU en scripts/estilos/layout (Performance.getMetrics).

Uso:
    python scripts/perf_probe.py [--url http://127.0.0.1:8797/] [--seconds 10] [--js "..."]
"""

from __future__ import annotations

import argparse
import asyncio
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

PORT = 9335
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
    """Cliente CDP mínimo con lectura en segundo plano (respuestas + eventos)."""

    def __init__(self, ws: Any) -> None:
        self.ws = ws
        self.next_id = 0
        self.pending: dict[int, asyncio.Future[dict[str, Any]]] = {}
        self.events: list[dict[str, Any]] = []
        self.reader = asyncio.create_task(self._read())

    async def _read(self) -> None:
        async for raw in self.ws:
            msg = json.loads(raw)
            if "id" in msg and msg["id"] in self.pending:
                self.pending.pop(msg["id"]).set_result(msg)
            elif "method" in msg:
                self.events.append(msg)

    async def call(self, method: str, **params: Any) -> dict[str, Any]:
        self.next_id += 1
        fut: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self.pending[self.next_id] = fut
        await self.ws.send(json.dumps({"id": self.next_id, "method": method, "params": params}))
        msg = await asyncio.wait_for(fut, 30)
        if "error" in msg:
            raise RuntimeError(f"{method}: {msg['error']}")
        result: dict[str, Any] = msg.get("result", {})
        return result

    def take_events(self) -> list[dict[str, Any]]:
        events, self.events = self.events, []
        return events


def summarize_network(events: list[dict[str, Any]]) -> dict[str, Any]:
    requests = [e for e in events if e["method"] == "Network.requestWillBeSent"]
    finished = [e for e in events if e["method"] == "Network.loadingFinished"]
    responses = [e for e in events if e["method"] == "Network.responseReceived"]
    status = [e["params"]["response"]["status"] for e in responses]
    return {
        "peticiones": len(requests),
        "bytes": int(sum(e["params"].get("encodedDataLength", 0) for e in finished)),
        "respuestas_304": status.count(304),
        "desde_cache": sum(
            1
            for e in responses
            if e["params"]["response"].get("fromDiskCache")
            or e["params"]["response"].get("fromServiceWorker")
        ),
    }


async def metrics(cdp: Cdp) -> dict[str, float]:
    res = await cdp.call("Performance.getMetrics")
    return {m["name"]: m["value"] for m in res["metrics"]}


async def probe(ws_url: str, args: argparse.Namespace) -> dict[str, Any]:
    async with websockets.connect(ws_url, max_size=50_000_000) as ws:
        cdp = Cdp(ws)
        await cdp.call(
            "Emulation.setDeviceMetricsOverride",
            width=393,
            height=786,
            deviceScaleFactor=1,
            mobile=True,
        )
        await cdp.call("Emulation.setCPUThrottlingRate", rate=4)
        await cdp.call("Network.enable")
        await cdp.call("Page.enable")
        await cdp.call("Performance.enable")
        out: dict[str, Any] = {}

        cdp.take_events()
        await cdp.call("Page.navigate", url=args.url)
        await asyncio.sleep(4)
        out["primera_carga"] = summarize_network(cdp.take_events())

        if args.js:
            await cdp.call("Runtime.evaluate", expression=args.js, awaitPromise=True)
            await asyncio.sleep(1.5)
        await cdp.call(
            "Runtime.evaluate",
            expression=(
                "window.__mut=0; new MutationObserver(function(l){window.__mut+=l.length})"
                ".observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true});"
            ),
        )
        cdp.take_events()
        before = await metrics(cdp)
        await asyncio.sleep(args.seconds)
        after = await metrics(cdp)
        events = cdp.take_events()
        mut = await cdp.call("Runtime.evaluate", expression="window.__mut", returnByValue=True)
        out["reposo"] = {
            "segundos": args.seconds,
            "mensajes_ws": sum(
                1 for e in events if e["method"] == "Network.webSocketFrameReceived"
            ),
            "bytes_ws": sum(
                len(e["params"]["response"]["payloadData"])
                for e in events
                if e["method"] == "Network.webSocketFrameReceived"
            ),
            "mutaciones_dom": mut["result"]["value"],
            "cpu_scripts_ms": round((after["ScriptDuration"] - before["ScriptDuration"]) * 1000, 1),
            "cpu_estilos_ms": round(
                (after["RecalcStyleDuration"] - before["RecalcStyleDuration"]) * 1000, 1
            ),
            "cpu_layout_ms": round((after["LayoutDuration"] - before["LayoutDuration"]) * 1000, 1),
            "cpu_tareas_ms": round((after["TaskDuration"] - before["TaskDuration"]) * 1000, 1),
        }

        cdp.take_events()
        await cdp.call("Page.reload")
        await asyncio.sleep(4)
        out["recarga"] = summarize_network(cdp.take_events())
        cdp.reader.cancel()
        return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8797/")
    parser.add_argument("--seconds", type=float, default=10)
    parser.add_argument("--js", default="")
    args = parser.parse_args()
    with tempfile.TemporaryDirectory() as profile:
        proc = subprocess.Popen(
            [
                find_browser(),
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
            result = asyncio.run(probe(targets[0]["webSocketDebuggerUrl"], args))
        finally:
            proc.terminate()
            proc.wait(timeout=10)
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
