"""Capture README screenshots from a running local KaraokeSesh instance."""

from __future__ import annotations

import argparse
import base64
import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect


def chrome_path() -> Path:
    candidates = [
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ]
    for candidate in candidates:
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise RuntimeError("Chrome or Edge was not found")


class DevTools:
    def __init__(self, url: str):
        self.socket = connect(url, origin="http://localhost:9224")
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

    def evaluate(self, expression: str) -> object:
        result = self.call(
            "Runtime.evaluate",
            {"expression": expression, "awaitPromise": True, "returnByValue": True},
        )
        return result.get("result", {}).get("value")

    def screenshot(self, path: Path, selector: str | None = None) -> None:
        params: dict = {"format": "png", "fromSurface": True, "captureBeyondViewport": False}
        if selector:
            box = self.evaluate(
                "(() => { const r = document.querySelector(%s).getBoundingClientRect(); "
                "return {x:r.x,y:r.y,width:r.width,height:r.height}; })()" % json.dumps(selector)
            )
            params["clip"] = {**box, "scale": 1}
        data = self.call("Page.captureScreenshot", params)["data"]
        path.write_bytes(base64.b64decode(data))

    def close(self) -> None:
        self.socket.close()


def target_websocket(port: int) -> str:
    endpoint = f"http://127.0.0.1:{port}/json/list"
    for _ in range(50):
        try:
            with urllib.request.urlopen(endpoint, timeout=0.5) as response:
                targets = json.load(response)
            page = next(target for target in targets if target.get("type") == "page")
            return page["webSocketDebuggerUrl"]
        except (OSError, StopIteration):
            time.sleep(0.1)
    raise RuntimeError("Chrome DevTools did not become ready")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5500")
    parser.add_argument("--out", type=Path, default=Path("docs/media"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="karaokesesh-chrome-") as profile:
        process = subprocess.Popen(
            [
                str(chrome_path()),
                "--headless=new",
                "--disable-gpu",
                "--hide-scrollbars",
                "--remote-debugging-port=9224",
                "--remote-allow-origins=*",
                f"--user-data-dir={profile}",
                "--window-size=1440,1000",
                "about:blank",
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        devtools = None
        try:
            devtools = DevTools(target_websocket(9224))
            devtools.call("Page.enable")
            devtools.call("Runtime.enable")
            devtools.call(
                "Emulation.setDeviceMetricsOverride",
                {"width": 1440, "height": 1000, "deviceScaleFactor": 1, "mobile": False},
            )
            devtools.call("Page.navigate", {"url": args.url})
            time.sleep(2.0)
            if not devtools.evaluate("Boolean(document.querySelector('#stage'))"):
                raise RuntimeError("KaraokeSesh did not load")
            if devtools.evaluate("Boolean(document.querySelector('#onboardingDialog')?.open)"):
                devtools.screenshot(args.out / "first-run.png", "#onboardingDialog .modal-card")
                devtools.evaluate("document.querySelector('#onboardingContinue').click()")
                time.sleep(0.2)
            devtools.screenshot(args.out / "editor-overview.png")
            devtools.screenshot(args.out / "kinetic-preview.png", "#stageShell")
            devtools.screenshot(args.out / "timeline-editor.png", "#timelineDock")
            devtools.evaluate("document.querySelector('#settingsButton').click()")
            time.sleep(0.2)
            devtools.screenshot(args.out / "local-ai-settings.png", "#settingsDialog .modal-card")
        finally:
            if devtools:
                devtools.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    main()
