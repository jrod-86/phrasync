"""Capture the live stage for each 3D scene kit into one small contact sheet.

Drives the running app through Chrome DevTools, so what lands in the sheet is
exactly what the preview renders. Deliberately low resolution: this is a review
aid, not an asset pipeline.

    python scripts/qa_scene.py --kits japan,italy,china,usa --t 6
"""

from __future__ import annotations

import argparse
import base64
import io
import json
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402
from websockets.sync.client import connect  # noqa: E402


def chrome_path() -> Path:
    for candidate in (
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise SystemExit("Chrome or Edge was not found")


class DevTools:
    def __init__(self, url: str, origin: str | None = "http://localhost:9225"):
        self.socket = connect(url, origin=origin)
        self.counter = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.counter += 1
        request_id = self.counter
        self.socket.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
        while True:
            reply = json.loads(self.socket.recv())
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise RuntimeError(f"{method}: {reply['error']}")
            return reply.get("result", {})

    def eval(self, expression: str):
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        if result.get("exceptionDetails"):
            raise RuntimeError(json.dumps(result["exceptionDetails"]))
        return result.get("result", {}).get("value")

    def shot(self, selector: str) -> Image.Image:
        box = self.eval(
            "(() => { const r = document.querySelector(%s).getBoundingClientRect(); "
            "return {x:r.x,y:r.y,width:r.width,height:r.height}; })()" % json.dumps(selector)
        )
        data = self.call("Page.captureScreenshot", {
            "format": "png", "fromSurface": True, "captureBeyondViewport": False,
            "clip": {**box, "scale": 1},
        })["data"]
        return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")

    def close(self) -> None:
        self.socket.close()


def websocket_url(port: int) -> str:
    for _ in range(60):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/json/list", timeout=0.5) as response:
                targets = json.load(response)
            return next(t for t in targets if t.get("type") == "page")["webSocketDebuggerUrl"]
        except (OSError, StopIteration):
            time.sleep(0.1)
    raise SystemExit("Chrome DevTools did not become ready")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5500")
    parser.add_argument("--out", type=Path, default=Path("qa_out/scene.png"))
    parser.add_argument("--kits", default="japan,italy,china,usa")
    parser.add_argument("--direction", default="forward")
    parser.add_argument("--art-style", default="cinematic")
    parser.add_argument("--secondary-motion", default="none")
    parser.add_argument("--visual", default="scene3d", help="scene3d (WebGL) or scene (flat)")
    parser.add_argument("--t", type=float, default=6.0, help="scene time to freeze at")
    parser.add_argument("--tile", type=int, default=440, help="tile width in the sheet")
    parser.add_argument("--project", type=Path, help="seed this saved project so real lyrics appear")
    parser.add_argument("--time", type=float, help="seek the transport here before capturing")
    parser.add_argument("--text-space", choices=("flat", "scene"), default="flat")
    parser.add_argument("--environment", choices=("manual", "auto"), default="manual")
    parser.add_argument("--weather", choices=("clear", "rain", "snow", "fog", "storm", "leaves"), default="clear")
    parser.add_argument("--daytime", choices=("dawn", "day", "sunset", "night"), default="sunset")
    parser.add_argument("--season", choices=("spring", "summer", "autumn", "winter"), default="summer")
    parser.add_argument("--presets", help="comma separated style presets, one tile each")
    parser.add_argument("--times", help="comma separated seek points; one tile each, single browser session")
    args = parser.parse_args()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    kits = [k.strip() for k in args.kits.split(",") if k.strip()]

    with tempfile.TemporaryDirectory(prefix="karaokesesh-qa-", ignore_cleanup_errors=True) as profile:
        process = subprocess.Popen(
            [str(chrome_path()), "--headless=new", "--disable-gpu", "--hide-scrollbars",
             "--remote-debugging-port=9225", "--remote-allow-origins=*",
             f"--user-data-dir={profile}", "--window-size=1440,1000", "about:blank"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        devtools = None
        try:
            devtools = DevTools(websocket_url(9225))
            devtools.call("Page.enable")
            devtools.call("Runtime.enable")
            devtools.call("Emulation.setDeviceMetricsOverride",
                          {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False})
            devtools.call("Page.navigate", {"url": args.url})
            time.sleep(2.2)

            if args.project:
                # A fresh Chrome profile starts on the placeholder project, so
                # push the real one in and reload to see actual lyrics in 3D.
                payload = json.loads(args.project.read_text(encoding="utf-8"))
                devtools.eval(
                    "(() => { localStorage.setItem('karaokesesh.project.v1', %s); return true; })()"
                    % json.dumps(json.dumps(payload.get("project", payload)))
                )
                devtools.call("Page.reload", {})
                time.sleep(2.6)
            if not devtools.eval("Boolean(window.VFSceneDraw) && Boolean(window.VFSceneGL)"):
                raise SystemExit("The scene engine did not load")
            devtools.eval("document.querySelectorAll('dialog[open]').forEach(d => d.close())")
            devtools.eval("(() => { for (const [id, value] of " + json.dumps([
                ['sceneArtStyle', args.art_style], ['secondaryMotion', args.secondary_motion]
            ]) + ") { const el = document.getElementById(id); el.value = value; el.dispatchEvent(new Event('input')); el.dispatchEvent(new Event('change')); } })()")

            # Drive the real controls: the app's own animation loop owns the
            # canvas, so painting a one-off frame would be overwritten at once.
            devtools.eval(
                "(() => { const set = (id, v) => { const el = document.querySelector(id);"
                " el.value = v; el.dispatchEvent(new Event('change', {bubbles:true}));"
                " el.dispatchEvent(new Event('input', {bubbles:true})); };"
                " set('#visualSelect', %s); set('#sceneDirection', %s);"
                " set('#textSpace', %s); set('#environmentMode', %s);"
                " set('#weather', %s); set('#daytime', %s); set('#season', %s); return true; })()"
                % (json.dumps(args.visual), json.dumps(args.direction),
                   json.dumps(args.text_space), json.dumps(args.environment),
                   json.dumps(args.weather), json.dumps(args.daytime), json.dumps(args.season))
            )
            time.sleep(0.4)

            stamps = [float(v) for v in args.times.split(",")] if args.times else [args.time]
            presets = [p.strip() for p in args.presets.split(",")] if args.presets else [None]

            tiles = []
            for kit in kits:
                devtools.eval(
                    "(() => { const el = document.querySelector('#sceneKit'); el.value = %s;"
                    " el.dispatchEvent(new Event('change', {bubbles:true}));"
                    " el.dispatchEvent(new Event('input', {bubbles:true})); return true; })()"
                    % json.dumps(kit)
                )
                time.sleep(2.0)
                for style_preset in presets:
                  if style_preset:
                    devtools.eval(
                        "(() => { const el = document.querySelector('#stylePreset'); el.value = %s;"
                        " el.dispatchEvent(new Event('change', {bubbles:true}));"
                        " el.dispatchEvent(new Event('input', {bubbles:true})); return true; })()"
                        % json.dumps(style_preset)
                    )
                    time.sleep(0.6)
                  for stamp in stamps:
                    if stamp is not None:
                        devtools.eval(
                            "(() => { const s = document.querySelector('#seekBar'); s.value = '%f';"
                            " s.dispatchEvent(new Event('input', {bubbles:true})); return true; })()" % stamp
                        )
                        time.sleep(0.7)
                    label = (style_preset or kit) + ("" if stamp is None else f"@{stamp:g}")
                    tiles.append((label, devtools.shot("#stage")))

            width = args.tile
            height = round(width * tiles[0][1].height / tiles[0][1].width)
            columns = 2
            rows = (len(tiles) + columns - 1) // columns
            sheet = Image.new("RGB", (width * columns, height * rows), (8, 8, 14))
            for index, (_, tile) in enumerate(tiles):
                sheet.paste(tile.resize((width, height), Image.Resampling.LANCZOS),
                            ((index % columns) * width, (index // columns) * height))
            sheet.save(args.out)
            print(f"{args.out}  ({', '.join(k for k, _ in tiles)})")
        finally:
            if devtools:
                devtools.close()
            process.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
