"""Browser smoke test for every lyric-space/background combination.

Starts a temporary headless Chrome, drives the live editor, and verifies that
WebGL keeps advancing, lyrics remain world-planted, transitions clear old
meshes, and no browser exception is raised.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from websockets.sync.client import connect


PORT = 9226


def chrome_path() -> Path:
    for candidate in (
        shutil.which("chrome"),
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    ):
        if candidate and Path(candidate).exists():
            return Path(candidate)
    raise SystemExit("Chrome or Edge was not found")


def websocket_url() -> str:
    for _ in range(80):
        try:
            with urllib.request.urlopen(
                f"http://127.0.0.1:{PORT}/json/list", timeout=0.5
            ) as response:
                targets = json.load(response)
            return next(t for t in targets if t.get("type") == "page")[
                "webSocketDebuggerUrl"
            ]
        except (OSError, StopIteration):
            time.sleep(0.1)
    raise SystemExit("Chrome DevTools did not become ready")


class DevTools:
    def __init__(self, url: str):
        self.socket = connect(url, origin=f"http://localhost:{PORT}")
        self.counter = 0

    def call(self, method: str, params: dict | None = None) -> dict:
        self.counter += 1
        request_id = self.counter
        self.socket.send(json.dumps({
            "id": request_id, "method": method, "params": params or {}
        }))
        while True:
            reply = json.loads(self.socket.recv())
            if reply.get("id") != request_id:
                continue
            if "error" in reply:
                raise RuntimeError(f"{method}: {reply['error']}")
            return reply.get("result", {})

    def eval(self, expression: str):
        result = self.call("Runtime.evaluate", {
            "expression": expression, "awaitPromise": True, "returnByValue": True,
        })
        value = result.get("result", {})
        if value.get("subtype") == "error":
            raise RuntimeError(value.get("description", "browser evaluation failed"))
        return value.get("value")


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default="http://127.0.0.1:5500")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="karaokesesh-matrix-", ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen(
            [
                str(chrome_path()), "--headless=new", "--hide-scrollbars",
                "--use-angle=swiftshader", "--enable-unsafe-swiftshader",
                f"--remote-debugging-port={PORT}", "--remote-allow-origins=*",
                f"--user-data-dir={profile}", "--window-size=1440,1000", "about:blank",
            ],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        devtools = None
        try:
            devtools = DevTools(websocket_url())
            devtools.call("Page.enable")
            devtools.call("Runtime.enable")
            devtools.call("Page.addScriptToEvaluateOnNewDocument", {"source": """
window.__qaErrors = [];
window.addEventListener('error', e => __qaErrors.push(String(e.error || e.message)));
window.addEventListener('unhandledrejection', e => __qaErrors.push(String(e.reason)));
"""})
            devtools.call("Page.navigate", {"url": args.url})
            time.sleep(2.5)
            if not devtools.eval("Boolean(window.VFSceneGL?.ready)"):
                raise AssertionError("WebGL scene engine did not load")

            devtools.eval("""
project.duration = 6;
project.cues = [{id:'qa-cue', start:0, end:4, text:'WORLD SPACE LYRIC', words:[]}];
project.background.sceneSpeed = 1;
project.background.visualIntensity = 0.9;
restartLyricAnimation();
""")

            cases = [
                ("dynamic", "scene3d"),
                ("dynamic", "aurora"),
                ("image", "aurora"),
                ("video", "aurora"),
            ]
            report = []
            for background, visual in cases:
                devtools.eval(f"""
project.background.type = {json.dumps(background)};
project.background.visual = {json.dumps(visual)};
project.background.textSpace = 'scene';
applyBackgroundTypeUI(); applyBackgroundPreview(); restartLyricAnimation(); seekTo(1.2);
""")
                devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                first = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); const m=[...s.textMeshes.values()][0];
return {kit:s.kit, camZ:s.camera.position.z, meshZ:m?.position.z,
meshX:m?.position.x, meshY:m?.position.y, camX:s.camera.position.x,
visible:[...s.textMeshes.values()].filter(x=>x.visible).length,
glHidden:els.glCanvas.hidden, dom:els.lyricDisplay.style.visibility,
controls:els.sceneControls.hidden, needed:glLayerNeeded(),
mode:project.background.textSpace, bg:project.background.type,
visual:project.background.visual, errors:window.__qaErrors}; })()
""")
                devtools.eval("seekTo(1.45)")
                devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                second = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); const m=[...s.textMeshes.values()][0];
return {camZ:s.camera.position.z, meshZ:m?.position.z,
meshX:m?.position.x, meshY:m?.position.y, camX:s.camera.position.x,
visible:[...s.textMeshes.values()].filter(x=>x.visible).length}; })()
""")
                expected_kit = "japan" if visual == "scene3d" else "__text__"
                assert first["kit"] == expected_kit, (background, first)
                assert not first["glHidden"] and first["dom"] == "hidden", first
                assert not first["controls"] and first["visible"] > 0, first
                assert second["camZ"] < first["camZ"], (first, second)
                assert abs(second["meshZ"] - first["meshZ"]) < 1e-6, (first, second)
                assert abs(second["meshX"] - first["meshX"]) < 1e-6, (first, second)
                assert abs(second["meshY"] - first["meshY"]) < 1e-6, (first, second)
                assert first["meshY"] >= 0.32, first

                devtools.eval("""
project.background.textSpace='flat'; applyBackgroundTypeUI();
restartLyricAnimation(); seekTo(1.45);
""")
                devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                flat = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); return {
visible:[...s.textMeshes.values()].filter(x=>x.visible).length,
dom:els.lyricDisplay.style.visibility}; })()
""")
                assert flat["visible"] == 0 and flat["dom"] == "", flat
                report.append(f"3D/2D + {background}/{visual}: ok")

            # User offsets must move the board in world coordinates without
            # reintroducing any camera compensation.
            devtools.eval("""
project.background.type='dynamic'; project.background.visual='scene3d';
project.background.textSpace='scene'; project.style.offset3DX=0; project.style.offset3DY=0;
restartLyricAnimation(); seekTo(1.2);
""")
            devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            base_offset = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); const m=[...s.textMeshes.values()][0];
return {x:m.position.x,y:m.position.y}; })()
""")
            devtools.eval("project.style.offset3DX=2.5; project.style.offset3DY=-1.5; seekTo(1.2)")
            devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            moved_offset = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); const m=[...s.textMeshes.values()][0];
return {x:m.position.x,y:m.position.y}; })()
""")
            assert abs(moved_offset["x"] - base_offset["x"] - 2.5) < 1e-6, (base_offset, moved_offset)
            assert abs(moved_offset["y"] - base_offset["y"] + 1.5) < 1e-6, (base_offset, moved_offset)
            report.append("3D world-space X/Y offsets: ok")

            # The board must survive long enough to pass the lens at the lowest
            # speed and must also be cleaned after its computed lifecycle tail.
            for speed_factor in (0.2, 1.0, 2.6):
                speed = 9 * speed_factor * (0.7 + 0.9 * 0.45)
                tail = max(0.3, (8 - 1.2) / speed + 0.15)
                near_time = 2 + (8 - 1.3) / speed
                devtools.eval(f"""
project.background.type='dynamic'; project.background.visual='scene3d';
project.background.textSpace='scene'; project.background.sceneSpeed={speed_factor};
project.style.offset3DX=0; project.style.offset3DY=0;
project.cues=[{{id:'speed-cue',start:0,end:2,text:'KEEP MOVING',words:[]}}];
project.duration=8; restartLyricAnimation(); seekTo({near_time});
""")
                devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                visible_near = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas);
return [...s.textMeshes.values()].filter(x=>x.visible).length; })()
""")
                assert visible_near > 0, (speed_factor, visible_near)
                devtools.eval(f"seekTo({2 + tail + 0.05})")
                devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
                visible_after = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas);
return [...s.textMeshes.values()].filter(x=>x.visible).length; })()
""")
                assert visible_after == 0, (speed_factor, visible_after)
                report.append(f"fly-past at {speed_factor * 100:.0f}% speed: ok")

            # Project modes change the actual source workflow, while typography
            # swaps to the dedicated 3D names without changing saved preset ids.
            mode_ui = devtools.eval("""
(() => { project.mode='subtitles'; applyModeUI();
project.background.textSpace='scene'; updatePresetPresentation();
return {accept:els.audioInput.accept, panel:els.cuePanelTitle.textContent,
label:els.stylePreset.options[0].textContent}; })()
""")
            assert "video/mp4" in mode_ui["accept"] and "video/webm" in mode_ui["accept"], mode_ui
            assert mode_ui["panel"] == "Subtitles", mode_ui
            assert mode_ui["label"].startswith("Monolith"), mode_ui
            report.append("subtitle workflow + 3D preset catalogue: ok")

            # Weather/day/season must alter the live world, and automatic mode
            # must resolve to different states along the same deterministic clock.
            devtools.eval("""
project.background.type='dynamic'; project.background.visual='scene3d';
project.background.textSpace='flat'; project.background.environmentMode='manual';
project.background.weather='storm'; project.background.daytime='night';
project.background.season='autumn'; applyBackgroundTypeUI(); seekTo(1);
""")
            devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            storm = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); return {
rain:s.environment.rain.visible, flakes:s.environment.flakes.visible,
fogFar:s.scene.fog.far, stars:s.sky.children[1].material.opacity,
ground:s.ground.material.color.getHexString(),
finite:[...s.environment.rain.geometry.attributes.position.array].every(Number.isFinite)}; })()
""")
            assert storm["rain"] and not storm["flakes"] and storm["fogFar"] == 105, storm
            assert storm["stars"] == 1 and storm["finite"], storm
            devtools.eval("project.background.weather='snow'; project.background.season='winter'; seekTo(1.1)")
            devtools.eval("new Promise(r => requestAnimationFrame(() => requestAnimationFrame(r)))")
            snow = devtools.eval("""
(() => { const s=VFSceneGL.get(els.glCanvas); return {
rain:s.environment.rain.visible, flakes:s.environment.flakes.visible,
fogFar:s.scene.fog.far, ground:s.ground.material.color.getHexString(),
finite:[...s.environment.flakes.geometry.attributes.position.array].every(Number.isFinite)}; })()
""")
            assert not snow["rain"] and snow["flakes"] and snow["fogFar"] == 150, snow
            assert snow["ground"] != storm["ground"] and snow["finite"], (storm, snow)
            automatic = devtools.eval("""
(() => { project.background.environmentMode='auto'; return [0,13,25,49]
.map(t => resolvedEnvironmentAt(t)).map(x => `${x.season}/${x.daytime}/${x.weather}`); })()
""")
            assert len(set(automatic)) == 4, automatic
            report.append("weather + daytime + season + automatic journey: ok")

            errors = devtools.eval("window.__qaErrors")
            assert not errors, errors
            print("\n".join(report))
            print("Browser exceptions: 0")
        finally:
            if devtools:
                devtools.socket.close()
            browser.terminate()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
