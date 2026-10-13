"""Browser QA for the Credit Crawl controls (plan Phase 2).

Checks, against a running app (app.py --no-browser --port 5507):
  1. real dropdown preset selection reveals/hides the crawl controls
     (Codex round-3 P1: the change handler must refresh panel visibility)
  2. switching away and back preserves saved crawl values
  3. moving a slider writes project.style.crawl and re-renders the stack
  4. preview and export engines resolve the same overrides
  5. saved project reload preserves style.crawl and the control values
  6. malformed saved-project reload: sliders display exactly the effective
     values both renderers resolve (Codex round-3 P2: hydration must use
     the validated merge, not unrestricted Number()); moving one slider
     must not change the other effective settings

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

# Representative malformed values (Codex round-3 P2). Expected effective
# resolution: every rejected value falls back to the preset default; the
# out-of-range number clamps to the limit.
MALFORMED = {
    "prevLines": "1_000",   # underscore grammar -> rejected -> default 2
    "nextLines": "0x10",    # hex grammar -> rejected -> default 2
    "transition": None,     # null -> rejected -> default 0.4 (400 ms)
    "nearOpacity": True,    # boolean -> rejected -> default 0.58 (58%)
    "blockGap": "",         # blank string -> rejected -> default 0.35 (35)
    "farOpacity": 999,      # out of range -> clamped -> 1.0 (100%)
}

CDP_PORT = 9341


def seed_script() -> str:
    """Install synthetic cues through the app's own state (preset untouched)."""
    return """
(() => {
  project.cues = JSON.parse(unescape(%s));
  project.style.fontSize = 100;
  project.style.lineGap = 0;
  project.background = {type:"dynamic", visual:"aurora",
      backgroundColor:"#101018", shade:1.0, visualIntensity:0.0};
  applyStageStyle();
  virtualTime = 0; virtualPlaying = false;
  return {
    preset: project.style.preset,
    crawlVisible: !document.getElementById("crawlControls").hidden
  };
})()
""" % json.dumps(json.dumps(CUES))


def select_preset_script(preset: str) -> str:
    """Select a preset the way a real user does: dropdown value + change event."""
    return """
(() => {
  const select = document.getElementById("stylePreset");
  select.value = %s;
  select.dispatchEvent(new Event("change"));
  virtualTime = 5.0; virtualPlaying = false;
  restartLyricAnimation();
  renderLyric(true);
  return {
    preset: project.style.preset,
    crawlVisible: !document.getElementById("crawlControls").hidden,
    cueCount: document.querySelectorAll("#lyricDisplay .lyric-cue").length
  };
})()
""" % json.dumps(preset)


def crawl_state_script() -> str:
    """Slider values + effective resolved crawl + raw saved crawl.

    Pumps the preview to t=5.0 first (the proven qa_credit_crawl.py pattern)
    so cueCount reflects the mid-song stack, not the initial t=0 render.
    """
    return """
(() => {
  virtualTime = 5.0; virtualPlaying = false;
  restartLyricAnimation();
  renderLyric(true);
  const spec = VFKinetic.resolvedPreset(project.style).crawl;
  return {
    saved: project.style.crawl,
    effective: spec,
    sliders: {
      prev: document.getElementById("crawlPrev").value,
      next: document.getElementById("crawlNext").value,
      transition: document.getElementById("crawlTransition").value,
      blockGap: document.getElementById("crawlBlockGap").value,
      near: document.getElementById("crawlNear").value,
      far: document.getElementById("crawlFar").value
    },
    visible: !document.getElementById("crawlControls").hidden,
    cueCount: document.querySelectorAll("#lyricDisplay .lyric-cue").length
  };
})()
"""


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

            # --- 1. controls hidden for the default preset ---
            state = dev.eval(seed_script())
            assert state and not state["crawlVisible"], \
                f"crawl controls visible for non-crawl preset: {state}"

            # --- 2. a REAL dropdown selection reveals the controls (P1) ---
            picked = dev.eval(select_preset_script("credit-crawl"))
            assert picked and picked["preset"] == "credit-crawl", picked
            assert picked["crawlVisible"], \
                "dropdown selection of credit-crawl left controls hidden"
            default_count = picked["cueCount"]
            assert default_count >= 3, f"expected a stacked preview, got {default_count}"

            # Another preset hides them again; back preserves saved values.
            away = dev.eval(select_preset_script("wipe-fill"))
            assert away and not away["crawlVisible"], f"preset switch left controls: {away}"

            # --- 3. sliders drive project.style.crawl and the rendered stack ---
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

            back = dev.eval(select_preset_script("credit-crawl"))
            assert back and back["crawlVisible"], \
                "controls not restored after switching back to credit-crawl"
            restored = dev.eval(crawl_state_script())
            assert restored["sliders"]["prev"] == "1" and restored["sliders"]["next"] == "0", \
                f"saved crawl values lost on preset switch: {restored['sliders']}"

            # --- 4. export engine resolves the same overrides from the style ---
            spec = kinetic.resolved_preset({"preset": "credit-crawl", "crawl": crawl})
            assert spec.crawl["prevLines"] == 1 and spec.crawl["nextLines"] == 0, spec.crawl
            for key, value in restored["effective"].items():
                assert abs(value - spec.crawl[key]) < 1e-9, f"{key} preview/export mismatch"

            # --- 5. save + reload preserves style.crawl and the control values ---
            dev.eval("localStorage.setItem('phrasync.project.v1', JSON.stringify(project));")
            dev.call("Page.navigate", {"url": f"{args.origin}/?desktop=1"})
            time.sleep(1.5)
            dev.close()
            dev = DevTools(websocket_url(CDP_PORT))
            time.sleep(2.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            reloaded = dev.eval(crawl_state_script())
            assert reloaded and reloaded["visible"], "controls not visible after reload"
            assert reloaded["saved"]["prevLines"] == 1 and reloaded["saved"]["nextLines"] == 0, reloaded
            assert reloaded["sliders"]["prev"] == "1" and reloaded["sliders"]["next"] == "0", reloaded

            # --- 6. malformed saved-project reload (P2): sliders must show the
            # exact effective values both renderers resolve. ---
            dev.eval("localStorage.setItem('phrasync.project.v1', JSON.stringify("
                     "{...project, style: {...project.style, preset: 'credit-crawl', "
                     "crawl: %s}}));" % json.dumps(MALFORMED))
            dev.call("Page.navigate", {"url": f"{args.origin}/?desktop=1"})
            time.sleep(1.5)
            dev.close()
            dev = DevTools(websocket_url(CDP_PORT))
            time.sleep(2.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            fixed = dev.eval(crawl_state_script())
            assert fixed and fixed["visible"], "controls not visible after malformed reload"

            base = kinetic.PRESETS["credit-crawl"].crawl
            expected = kinetic.merge_crawl_overrides(base, MALFORMED)
            assert expected["prevLines"] == base["prevLines"] == 2.0, expected
            assert expected["nextLines"] == base["nextLines"] == 2.0, expected
            assert abs(expected["transition"] - 0.4) < 1e-9, expected
            assert abs(expected["nearOpacity"] - base["nearOpacity"]) < 1e-9, expected
            assert abs(expected["blockGap"] - base["blockGap"]) < 1e-9, expected
            assert abs(expected["farOpacity"] - 1.0) < 1e-9, expected

            # JS effective == Python effective == slider display.
            for key, value in expected.items():
                assert abs(fixed["effective"][key] - value) < 1e-9, \
                    f"{key}: JS effective {fixed['effective'][key]} != Python {value}"
            want_sliders = {"prev": "2", "next": "2", "transition": "400",
                            "blockGap": "35", "near": "58", "far": "100"}
            assert fixed["sliders"] == want_sliders, \
                f"sliders disagree with effective values: {fixed['sliders']}"
            assert fixed["cueCount"] >= 3, fixed

            # Moving one slider must not rewrite the others into new behaviour.
            dev.eval("""
(() => {
  const prev = document.getElementById("crawlPrev");
  prev.value = "3"; prev.dispatchEvent(new Event("input"));
  virtualTime = 5.0; virtualPlaying = false; renderLyric(true);
})()
""")
            moved = dev.eval(crawl_state_script())
            assert moved["effective"]["prevLines"] == 3.0, moved
            for key, value in expected.items():
                if key == "prevLines":
                    continue
                assert abs(moved["effective"][key] - value) < 1e-9, \
                    f"{key} changed unexpectedly after moving prev slider: {moved['effective']}"

            # Valid settings still round-trip after the malformed reload.
            dev.eval("localStorage.setItem('phrasync.project.v1', JSON.stringify(project));")
            dev.call("Page.navigate", {"url": f"{args.origin}/?desktop=1"})
            time.sleep(1.5)
            dev.close()
            dev = DevTools(websocket_url(CDP_PORT))
            time.sleep(2.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            roundtrip = dev.eval(crawl_state_script())
            assert roundtrip and roundtrip["saved"]["prevLines"] == 3, roundtrip
            assert roundtrip["sliders"]["prev"] == "3", roundtrip

            print("PASS credit-crawl controls QA (dropdown visibility, saved-value "
                  "restore, live tuning, preview/export parity, save/reload, "
                  "malformed reload hydration)")
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
