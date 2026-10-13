"""Browser QA for the Credit Crawl controls (plan Phase 2).

Checks, against a running app (app.py --no-browser --port 5507):
  1. crawl controls hidden for other presets, visible for credit-crawl
  2. moving a slider writes project.style.crawl and re-renders the stack
     (fewer visible cues when prev/next lines drop)
  3. preview and export engines resolve the same overrides
  4. saved project reload preserves style.crawl and the control values
  5. malformed persisted crawl falls back to the preset defaults

Run:
  1. .venv\\Scripts\\python.exe app.py --no-browser --port 5507
  2. .venv\\Scripts\\python.exe scripts/qa_crawl_controls.py --origin http://127.0.0.1:5507
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from phrasync import kinetic  # noqa: E402
from qa_scene import DevTools, chrome_path, websocket_url  # noqa: E402

CUES = [
    {"id": f"cc{i}", "start": i * 2.0, "end": i * 2.0 + 2.0,
     "text": f"crawl control line {i}", "words": []}
    for i in range(1, 8)
]

CDP_PORT = 9341


def seed_script() -> str:
    """Install synthetic cues + the crawl preset through the app's own state."""
    return """
(() => {
  project.cues = JSON.parse(unescape(%s));
  project.style.preset = "credit-crawl";
  project.style.fontSize = 100;
  project.style.lineGap = 0;
  project.background = {type:"dynamic", visual:"aurora",
      backgroundColor:"#101018", shade:1.0, visualIntensity:0.0};
  document.getElementById("stylePreset").value = "credit-crawl";
  applyProjectToControls();
  applyStageStyle();
  virtualTime = 0; virtualPlaying = false;
  restartLyricAnimation();
  virtualTime = 5.0; renderLyric(true);
  return {
    crawlVisible: !document.getElementById("crawlControls").hidden,
    cueCount: document.querySelectorAll("#lyricDisplay .lyric-cue").length
  };
})()
""" % json.dumps(json.dumps(CUES))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:5507")
    args = parser.parse_args()

    with tempfile.TemporaryDirectory(prefix="phrasync-crawl-controls-",
                                     ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen(
            [str(chrome_path()), "--headless=new", "--no-first-run",
             f"--remote-debugging-port={CDP_PORT}", "--remote-allow-origins=*",
             "--disable-gpu", "--window-size=1920,1080",
             f"--user-data-dir={profile}", f"{args.origin}/?desktop=1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(CDP_PORT))
            time.sleep(2.5)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")

            # --- 1. controls appear only for credit-crawl ---
            state = dev.eval(seed_script())
            assert state and state["crawlVisible"], f"crawl controls not visible: {state}"
            default_count = state["cueCount"]
            assert default_count >= 3, f"expected a stacked preview, got {default_count}"

            other = dev.eval("""
(() => {
  project.style.preset = "wipe-fill";
  document.getElementById("stylePreset").value = "wipe-fill";
  applyProjectToControls();
  const hidden = document.getElementById("crawlControls").hidden;
  project.style.preset = "credit-crawl";
  document.getElementById("stylePreset").value = "credit-crawl";
  applyProjectToControls();
  return {hidden, back: !document.getElementById("crawlControls").hidden};
})()
""")
            assert other and other["hidden"] and other["back"], f"preset toggle failed: {other}"

            # --- 2. sliders drive project.style.crawl and the rendered stack ---
            tuned = dev.eval("""
(() => {
  const prev = document.getElementById("crawlPrev");
  const next = document.getElementById("crawlNext");
  prev.value = "1"; prev.dispatchEvent(new Event("input"));
  next.value = "0"; next.dispatchEvent(new Event("input"));
  virtualTime = 5.0; virtualPlaying = false; renderLyric(true);
  return {
    crawl: project.style.crawl,
    cueCount: document.querySelectorAll("#lyricDisplay .lyric-cue").length,
    prevOut: document.getElementById("crawlPrevOut").value,
    nextOut: document.getElementById("crawlNextOut").value
  };
})()
""")
            assert tuned, "tune evaluate returned nothing"
            crawl = tuned["crawl"]
            assert crawl.get("prevLines") == 1 and crawl.get("nextLines") == 0, crawl
            assert tuned["cueCount"] < default_count, (
                f"stack did not shrink: {tuned['cueCount']} vs {default_count}")
            assert tuned["prevOut"] == "1" and tuned["nextOut"] == "0", tuned

            # --- 3. export engine resolves the same overrides from the style ---
            spec = kinetic.resolved_preset({"preset": "credit-crawl", "crawl": crawl})
            assert spec.crawl["prevLines"] == 1 and spec.crawl["nextLines"] == 0, spec.crawl
            preview_spec = dev.eval(
                "JSON.stringify(VFKinetic.resolvedPreset(project.style).crawl)")
            for key, value in json.loads(preview_spec).items():
                assert abs(value - spec.crawl[key]) < 1e-9, f"{key} preview/export mismatch"

            # --- 4. save + reload preserves style.crawl and the control values ---
            dev.eval("localStorage.setItem('phrasync.project.v1', JSON.stringify(project));")
            dev.call("Page.navigate", {"url": f"{args.origin}/?desktop=1"})
            time.sleep(1.5)
            dev.close()
            dev = DevTools(websocket_url(CDP_PORT))
            time.sleep(2.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            reloaded = dev.eval("""
(() => ({
  preset: project.style.preset,
  crawl: project.style.crawl,
  prevValue: document.getElementById("crawlPrev").value,
  nextValue: document.getElementById("crawlNext").value,
  visible: !document.getElementById("crawlControls").hidden
}))()
""")
            assert reloaded and reloaded["preset"] == "credit-crawl", reloaded
            assert reloaded["crawl"]["prevLines"] == 1 and reloaded["crawl"]["nextLines"] == 0, reloaded
            assert reloaded["prevValue"] == "1" and reloaded["nextValue"] == "0", reloaded
            assert reloaded["visible"], "controls not visible after reload"

            # --- 5. malformed persisted crawl must not poison the preview ---
            malformed = dev.eval("""
(() => {
  project.style.crawl = {prevLines: "lots", transition: null, nearOpacity: true};
  restartLyricAnimation();
  virtualTime = 5.0; virtualPlaying = false; renderLyric(true);
  const spec = VFKinetic.resolvedPreset(project.style);
  return {
    prev: spec.crawl.prevLines, transition: spec.crawl.transition,
    near: spec.crawl.nearOpacity,
    cueCount: document.querySelectorAll("#lyricDisplay .lyric-cue").length
  };
})()
""")
            base = kinetic.PRESETS["credit-crawl"].crawl
            assert malformed and malformed["prev"] == base["prevLines"], malformed
            assert abs(malformed["transition"] - base["transition"]) < 1e-9, malformed
            assert abs(malformed["near"] - base["nearOpacity"]) < 1e-9, malformed
            assert malformed["cueCount"] >= 3, malformed

            print("PASS credit-crawl controls QA (visibility, live tuning, "
                  "preview/export parity, save/reload, malformed fallback)")
            return 0
        finally:
            if dev is not None:
                try:
                    dev.close()
                except Exception:
                    pass
            browser.terminate()


if __name__ == "__main__":
    sys.exit(main())
