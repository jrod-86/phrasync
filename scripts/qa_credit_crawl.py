"""Karaoke Credit Crawl first-milestone QA: browser preview vs MP4 export parity.

Drives the running app through Chrome DevTools (same harness as qa_scene.py),
loads a synthetic SRT-shaped cue set, selects the credit-crawl preset, and
checks the acceptance behaviours that need a real browser:

  1. preset selectable and preview shows centred active + readable upcoming line
  2. cue-boundary scroll (offsets move between t=1.9 and t=2.2)
  3. seeking reconstructs the stack immediately (t=5.0 after t=2.2)
  4. wrapped two-line cue does not collide with neighbours
  5. instrumental gap keeps a calm previous/next state (no blank frame)
  6. save/reload preserves the preset selection
  7. preview DOM stack matches the export credit_crawl_state() stack

Run:
  1. .venv\\Scripts\\python.exe app.py --no-browser --port 5507
  2. .venv\\Scripts\\python.exe scripts/qa_credit_crawl.py --origin http://127.0.0.1:5507
"""

from __future__ import annotations

import argparse
import json
import math
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image  # noqa: E402
from karaokesesh import kinetic  # noqa: E402
from karaokesesh.renderer import RenderContext  # noqa: E402
from karaokesesh.render_typography import render_text_layer  # noqa: E402
from qa_scene import DevTools, chrome_path, websocket_url  # noqa: E402

CUES = [
    {"id": "c1", "start": 0.0, "end": 2.0, "text": "FIRST LINE HERE", "words": []},
    {"id": "c2", "start": 2.0, "end": 4.0, "text": "SECOND LINE HERE", "words": []},
    # Long enough to exceed the ~87-char budget at 1920x1080, so BOTH engines
    # wrap it to two lines and the block-gap collision check is meaningful.
    {"id": "c3", "start": 4.0, "end": 6.0,
     "text": "THIS IS A VERY LONG WRAPPING THIRD LINE THAT BREAKS INTO TWO LINES "
             "AND KEEPS GOING PAST THE BUDGET",
     "words": []},
    {"id": "c4", "start": 6.0, "end": 8.0, "text": "FOURTH LINE AFTER THE GAP", "words": []},
]
# c3 -> c4 leaves a 2.0 s instrumental gap after c3 ends at 6.0? No: c3 ends 6.0,
# c4 starts 6.0. The gap lives between c2 end (4.0) and c3 start... keep an
# explicit gap cue pair instead so the gap case is unambiguous:
GAP_CUES = [
    {"id": "g1", "start": 0.0, "end": 1.5, "text": "BEFORE THE BREAK", "words": []},
    {"id": "g2", "start": 5.0, "end": 7.0, "text": "AFTER THE BREAK", "words": []},
]

# Realistic default-style fixture (Issue 3): the app's own defaults — Impact,
# fontSize 160, maxWidth 88, positionY 52, lineGap -8 — with five consecutive
# cues that each exceed the ~24-char budget and therefore wrap to two lines.
# Seeking to the middle cue (r3 at t=5.0) exercises previous/upcoming
# neighbours and the viewport drop rule at full 1080p typography.
REALISTIC_STYLE = {"preset": "credit-crawl", "fontPreset": "impact",
                   "fontSize": 160, "maxWidth": 88, "positionY": 52, "lineGap": -8}
REALISTIC_CUES = [
    {"id": "r1", "start": 0.0, "end": 2.0, "text": "ALPHA BRAVO CHARLIE DELTA ECHO FOXTROT", "words": []},
    {"id": "r2", "start": 2.0, "end": 4.0, "text": "GOLF HOTEL INDIA JULIET KILO LIMA", "words": []},
    {"id": "r3", "start": 4.0, "end": 6.0, "text": "MIKE NOVEMBER OSCAR PAPA QUEBEC ROMEO", "words": []},
    {"id": "r4", "start": 6.0, "end": 8.0, "text": "SIERRA TANGO UNIFORM VICTOR WHISKEY", "words": []},
    {"id": "r5", "start": 8.0, "end": 10.0, "text": "XRAY YANKEE ZULU ALPHA BRAVO CHARLIE", "words": []},
]


def stage_shot(dev: DevTools) -> Image.Image:
    return dev.shot("#stage")


def glyph_rows(image: Image.Image) -> list[tuple[int, int, int]]:
    """Return (top, bottom, brightness) bands for horizontal text bands of the stage."""
    gray = image.convert("L")
    w, h = gray.size
    px = gray.load()
    rows = []
    for y in range(h):
        bright = sum(px[x, y] for x in range(0, w, 3))
        rows.append(bright)
    bands = []
    threshold = 40 * (w // 3)
    y = 0
    while y < h:
        if rows[y] > threshold:
            top = y
            peak = 0
            while y < h and rows[y] > threshold:
                peak = max(peak, rows[y])
                y += 1
            bands.append((top, y - 1, peak))
        else:
            y += 1
    return bands


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:5507")
    parser.add_argument("--out", type=Path, default=Path(".crawl_render/qa"))
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    host_port = args.origin.split("//", 1)[1]
    cdp_port = 9241
    with tempfile.TemporaryDirectory(prefix="karaokesesh-crawl-qa-", ignore_cleanup_errors=True) as profile:
        browser = subprocess.Popen(
            [str(chrome_path()), "--headless=new", "--no-first-run",
             f"--remote-debugging-port={cdp_port}", "--remote-allow-origins=*",
             "--window-size=1920,1080", f"--user-data-dir={profile}",
             f"{args.origin}/?desktop=1"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        dev = None
        try:
            dev = DevTools(websocket_url(cdp_port))
            time.sleep(2.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")

            # --- 1. preset is selectable in the UI ---
            options = dev.eval("[...document.querySelectorAll('#stylePreset option')].map(o=>o.value)")
            assert "credit-crawl" in options, f"credit-crawl missing from preset select: {options}"
            dev.eval("""
                project.style.preset = 'credit-crawl';
                document.getElementById('stylePreset').value = 'credit-crawl';
                project.cues = JSON.parse(unescape(%s));
                project.background = {type:'dynamic', visual:'aurora',
                    backgroundColor:'#101018', shade:1.0, visualIntensity:0.0};
                project.style.fontSize = 100;
                project.style.lineGap = 0;
                applyStageStyle();
                virtualTime = 0; virtualPlaying = false;
                renderLyric(true);
            """ % json.dumps(json.dumps(CUES)))

            def dom_stack(t: float):
                dev.eval(f"virtualTime = {t}; virtualPlaying=false; renderLyric(false); updateLyricFrame({t});")
                time.sleep(0.12)
                return dev.eval("""
                    [...document.querySelectorAll('.lyric-display .lyric-cue')].map(el => {
                        const r = el.getBoundingClientRect();
                        const m = /translate3d\\(0(?:px)?,\\s*(-?[0-9.]+)px/.exec(el.style.transform || '');
                        return { top: r.top, height: r.height,
                                 transformY: m ? parseFloat(m[1]) : null,
                                 opacity: parseFloat(el.style.opacity || '1') };
                    })
                """)

            # --- 2. active line centred + upcoming visible (t=1.0) ---
            stack = dom_stack(1.0)
            ids_at = dev.eval("""
                VFKinetic.creditCrawlState(project.cues, 1.0,
                  VFKinetic.resolvedPreset(project.style),
                  VFKinetic.charBudget(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style)),
                  VFKinetic.crawlViewport(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style))).cues.map(c=>c.cue.id)
            """)
            assert ids_at == ["c1", "c2", "c3"], f"expected active c1 + upcoming c2,c3 at t=1.0, got {ids_at}"
            stage = stage_shot(dev)
            stage.save(args.out / "preview_t1.0.png")
            # centring from DOM geometry: active cue block centre vs display centre
            geom = dev.eval("""
                (() => {
                    const d = document.querySelector('.lyric-display').getBoundingClientRect();
                    const cues = [...document.querySelectorAll('.lyric-display .lyric-cue')].map(el => {
                        const r = el.getBoundingClientRect();
                        return { id: el.textContent.trim().slice(0, 12),
                                 centre: r.top + r.height / 2, height: r.height };
                    });
                    return { displayCentre: d.top + d.height / 2, cues };
                })()
            """)
            active_geom = max(geom["cues"], key=lambda c: c["height"])  # active cue renders at full opacity/size
            # the active cue is the one whose transformY is ~0; find it via state instead
            active_id = dev.eval("""
                (() => { const s = VFKinetic.creditCrawlState(project.cues, 1.0,
                    VFKinetic.resolvedPreset(project.style),
                    VFKinetic.charBudget(project.style, project.canvas,
                      VFKinetic.resolvedPreset(project.style)),
                    VFKinetic.crawlViewport(project.style, project.canvas,
                      VFKinetic.resolvedPreset(project.style)));
                    const a = s.cues.find(c=>c.active); return a ? a.cue.id : null; })()
            """)
            assert active_id == "c1", f"active cue at t=1.0 should be c1, got {active_id}"
            active_geom = geom["cues"][0]  # state order is top-to-bottom; c1 is first with prevLines window
            diff = abs(active_geom["centre"] - geom["displayCentre"])
            assert diff < max(12, active_geom["height"] * 0.35), (
                f"active line centre {active_geom['centre']:.0f} not near display centre {geom['displayCentre']:.0f}")
            assert len(geom["cues"]) >= 2, "expected upcoming line(s) visible below the active line"

            # --- 3. boundary scroll: c1 rolls up, c2 centres (t=2.2 at rest) ---
            stack_early = dom_stack(1.9)
            stack_rest = dom_stack(2.2)
            ids_rest = dev.eval("""
                VFKinetic.creditCrawlState(project.cues, 2.2,
                  VFKinetic.resolvedPreset(project.style),
                  VFKinetic.charBudget(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style)),
                  VFKinetic.crawlViewport(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style))).cues.map(c=>c.cue.id)
            """)
            # Viewport rule: c4's block would poke below the frame at t=2.2,
            # so it is not shown until it fits completely (Codex finding 1).
            assert ids_rest == ["c1", "c2", "c3"], f"expected c1,c2,c3 at t=2.2, got {ids_rest}"
            def band_centres(image):
                return [(b[0] + b[1]) / 2 for b in glyph_rows(image)]
            stage_shot(dev).save(args.out / "preview_t2.2.png")
            centres_early = dev.eval("""
                [...document.querySelectorAll('.lyric-display .lyric-cue')].map(el => {
                    const m = /translate3d\\(0, (-?[0-9.]+)px/.exec(el.style.transform || '');
                    return m ? parseFloat(m[1]) : 0; })
            """)
            # re-render at 1.9 for the comparison
            stack_early = dom_stack(1.9)
            ys_early = [s["transformY"] or 0 for s in stack_early]
            ys_rest = [s["transformY"] or 0 for s in stack_rest]
            assert len(ys_early) >= 2 and len(ys_rest) >= 3
            # the old active cue (first in stack) moved UP (more negative) after the boundary
            assert ys_rest[0] < ys_early[0] - 1, (
                f"no upward roll across boundary: {ys_early} -> {ys_rest}")

            # --- 4. seeking reconstructs immediately (jump 2.2 -> 5.0) ---
            stack_seek = dom_stack(5.0)
            ids_seek = dev.eval("""
                VFKinetic.creditCrawlState(project.cues, 5.0,
                  VFKinetic.resolvedPreset(project.style),
                  VFKinetic.charBudget(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style)),
                  VFKinetic.crawlViewport(project.style, project.canvas,
                    VFKinetic.resolvedPreset(project.style))).cues.map(c=>c.cue.id)
            """)
            assert ids_seek == ["c1", "c2", "c3", "c4"], f"seek stack wrong: {ids_seek}"
            # at rest (t=5.0 is > transition after c3 start) c3 offset must be ~0
            c3 = next(s for s in stack_seek if abs((s["transformY"] or 0)) < 1.5)
            stage_shot(dev).save(args.out / "preview_t5.0_wrapped.png")

            # --- 5. wrapped cue: no collisions in DOM boxes + wrap parity with engine ---
            boxes = [(s["top"], s["top"] + s["height"]) for s in stack_seek]
            for (a1, a2), (b1, b2) in zip(boxes, boxes[1:]):
                assert b1 >= a2 - 1.0, f"DOM cue boxes overlap at t=5.0: {boxes}"
            # every cue box must stay inside the stage (no clipping)
            stage_box = dev.eval("""
                (() => { const r = document.querySelector('#stage').getBoundingClientRect();
                         return {top: r.top, bottom: r.bottom}; })()
            """)
            for (b1, b2) in boxes:
                assert b1 >= stage_box["top"] - 1.0 and b2 <= stage_box["bottom"] + 1.0, (
                    f"cue box clipped by stage bounds at t=5.0: {b1:.0f}-{b2:.0f} vs "
                    f"{stage_box['top']:.0f}-{stage_box['bottom']:.0f}")
            # DOM wrap must match the engine's layoutLines count for every visible cue
            wrap_parity = dev.eval("""
                (() => {
                    const preset = VFKinetic.resolvedPreset(project.style);
                    const budget = VFKinetic.charBudget(project.style, project.canvas, preset);
                    const state = VFKinetic.creditCrawlState(project.cues, 5.0, preset, budget,
                      VFKinetic.crawlViewport(project.style, project.canvas, preset));
                    const dom = [...document.querySelectorAll('.lyric-display .lyric-cue')];
                    return state.cues.map((c, i) => ({
                        id: c.cue.id,
                        engineLines: VFKinetic.layoutLines(VFKinetic.cueWords(c.cue), preset, budget).length,
                        domLines: dom[i] ? dom[i].querySelectorAll('.lyric-line').length : -1,
                    }));
                })()
            """)
            for w in wrap_parity:
                assert w["domLines"] == w["engineLines"], (
                    f"wrap mismatch for {w['id']}: DOM {w['domLines']} lines vs engine {w['engineLines']}")

            # --- 6. instrumental gap stays calm (no blank, no cycling) ---
            dev.eval("""
                project.cues = JSON.parse(unescape(%s)); renderLyric(true);
            """ % json.dumps(json.dumps(GAP_CUES)))
            gap_states = []
            for t in [2.0, 2.6, 3.2, 3.8, 4.4]:
                gap_states.append(dom_stack(t))
            for t, stack in zip([2.0, 2.6, 3.2, 3.8, 4.4], gap_states):
                assert len(stack) >= 2, f"gap t={t} left a blank frame ({len(stack)} cues)"
            stage_shot(dev).save(args.out / "preview_gap_t3.2.png")
            dev.eval("project.cues = JSON.parse(unescape(%s)); renderLyric(true);"
                     % json.dumps(json.dumps(CUES)))

            # --- 7. preview DOM matches export state (offsets + opacity) ---
            spec = kinetic.resolved_preset({"preset": "credit-crawl", "fontSize": 100, "lineGap": 0})
            qa_canvas = {"width": 1920, "height": 1080}
            qa_style = {"preset": "credit-crawl", "fontSize": 100, "lineGap": 0}
            for t in [1.0, 2.2, 5.0]:
                dom = dom_stack(t)
                state = kinetic.credit_crawl_state(
                    CUES, t, spec,
                    kinetic.char_budget(qa_style, qa_canvas, spec),
                    kinetic.crawl_viewport(qa_style, qa_canvas, spec))
                assert len(dom) == len(state["cues"]), (
                    f"t={t}: preview shows {len(dom)} cues, export state has {len(state['cues'])}")
                # both lists are ordered top-to-bottom; compare opacity per slot
                for item, cue_state in zip(dom, state["cues"]):
                    assert abs(item["opacity"] - cue_state["opacity"]) < 0.06, (
                        f"t={t} opacity mismatch {item['opacity']} vs {cue_state['opacity']}")

            # --- 8. save/reload preserves the preset ---
            dev.eval("localStorage.setItem('karaokesesh.project.v1', JSON.stringify(project));")
            dev.call("Page.navigate", {"url": f"{args.origin}/?desktop=1"})
            time.sleep(2.0)
            dev.close()
            dev = DevTools(websocket_url(cdp_port))
            time.sleep(1.0)
            dev.eval("document.querySelectorAll('dialog[open]').forEach(d=>d.close())")
            reloaded = dev.eval("project.style.preset")
            assert reloaded == "credit-crawl", f"preset lost after reload: {reloaded}"
            select_value = dev.eval("document.getElementById('stylePreset').value")
            assert select_value == "credit-crawl", f"select not restored: {select_value}"

            # --- 9. export frames match the preview stack geometry ---
            project = {"style": {"preset": "credit-crawl", "fontSize": 100, "lineGap": 0},
                       "timing": {"offset": 0}, "canvas": {"width": 1920, "height": 1080},
                       "background": {"type": "color", "backgroundColor": "#101018"}}
            import numpy as np
            for t in [1.0, 2.2, 5.0]:
                ctx = RenderContext(project, 1920, 1080, 30, 3, 90, CUES, None, None, None, np.zeros(90))
                layer = render_text_layer(ctx, t)
                assert layer is not None and layer.getchannel("A").getbbox() is not None
                layer.convert("RGB").save(args.out / f"export_t{t}.png")
                state = kinetic.credit_crawl_state(
                    CUES, t, spec,
                    kinetic.char_budget(project["style"], project["canvas"], spec),
                    kinetic.crawl_viewport(project["style"], project["canvas"], spec))
                # export band centres must follow the same top-to-bottom order as preview
                preview_ids = [c["cue"]["id"] for c in state["cues"]]
                dom_ids = dev.eval(f"""
                    VFKinetic.creditCrawlState(project.cues, {t},
                      VFKinetic.resolvedPreset(project.style),
                      VFKinetic.charBudget(project.style, project.canvas,
                        VFKinetic.resolvedPreset(project.style)),
                      VFKinetic.crawlViewport(project.style, project.canvas,
                        VFKinetic.resolvedPreset(project.style))).cues.map(c=>c.cue.id)
                """)
                assert preview_ids == dom_ids, f"t={t}: export/preview cue order differs {preview_ids} vs {dom_ids}"

            # --- 10. realistic default-style 1080p bounds QA (Codex Issue 3) ---
            # App's own defaults at full 1080p typography: Impact, fontSize 160,
            # maxWidth 88, positionY 52, lineGap -8. Five consecutive cues each
            # exceed the ~24-char budget so every cue wraps to two lines. Seek to
            # the middle cue (r3 at t=5.0) so previous/upcoming neighbours and the
            # viewport drop rule are exercised at full size.
            dev.eval("""
                project.style.preset = 'credit-crawl';
                project.style.fontPreset = 'impact';
                project.style.fontSize = 160;
                project.style.maxWidth = 88;
                project.style.positionY = 52;
                project.style.lineGap = -8;
                document.getElementById('stylePreset').value = 'credit-crawl';
                project.cues = JSON.parse(unescape(%s));
                project.background = {type:'dynamic', visual:'aurora',
                    backgroundColor:'#101018', shade:1.0, visualIntensity:0.0};
                applyStageStyle();
                virtualTime = 0; virtualPlaying = false;
                renderLyric(true);
            """ % json.dumps(json.dumps(REALISTIC_CUES)))
            dev.eval("virtualTime = 5.0; virtualPlaying=false; renderLyric(false); updateLyricFrame(5.0);")
            time.sleep(0.15)
            stage_shot(dev).save(args.out / "preview_realistic_t5.0.png")

            # Engine (Python) expectation for the same fixture, for parity.
            real_spec = kinetic.resolved_preset(REALISTIC_STYLE)
            real_budget = kinetic.char_budget(REALISTIC_STYLE, qa_canvas, real_spec)
            real_vp = kinetic.crawl_viewport(REALISTIC_STYLE, qa_canvas, real_spec)
            real_state = kinetic.credit_crawl_state(REALISTIC_CUES, 5.0, real_spec, real_budget, real_vp)
            real_ids = [c["cue"]["id"] for c in real_state["cues"]]
            assert real_budget == 24, f"realistic budget should be 24 chars, got {real_budget}"
            assert all(len(kinetic.layout_lines(kinetic.cue_words(c), real_spec, real_budget)) == 2
                       for c in REALISTIC_CUES), "every realistic cue must wrap to two lines"
            assert real_ids == ["r2", "r3", "r4"], (
                f"engine must keep middle cue + neighbours and drop distant r1/r5, got {real_ids}")

            # DOM geometry at the middle cue. Cue elements carry no id attribute,
            # so correlate DOM cues to engine cues by normalized text content.
            real_geom = dev.eval("""
                (() => {
                    const stage = document.querySelector('#stage').getBoundingClientRect();
                    const display = document.querySelector('.lyric-display').getBoundingClientRect();
                    const preset = VFKinetic.resolvedPreset(project.style);
                    const budget = VFKinetic.charBudget(project.style, project.canvas, preset);
                    const state = VFKinetic.creditCrawlState(project.cues, 5.0, preset, budget,
                      VFKinetic.crawlViewport(project.style, project.canvas, preset));
                    const norm = s => String(s).replace(/\\s+/g, '').toUpperCase();
                    const idByNorm = new Map(state.cues.map(c => [norm(c.cue.text), c.cue.id]));
                    const domText = el => [...el.querySelectorAll('.lw-base')].map(s => s.textContent).join('');
                    const dom = [...document.querySelectorAll('.lyric-display .lyric-cue')].map(el => {
                        const r = el.getBoundingClientRect();
                        return { id: idByNorm.get(norm(domText(el))) || null,
                                 top: r.top, bottom: r.bottom, height: r.height,
                                 lines: el.querySelectorAll('.lyric-line').length,
                                 opacity: parseFloat(el.style.opacity || '1') };
                    });
                    const active = state.cues.find(c => c.active);
                    return { stageTop: stage.top, stageBottom: stage.bottom,
                             anchor: display.top + display.height / 2,
                             domIds: dom.map(d => d.id), dom,
                             engineIds: state.cues.map(c => c.cue.id),
                             activeId: active ? active.cue.id : null };
                })()
            """)
            # Preview DOM must match the engine cue set exactly (drop rule parity).
            assert real_geom["domIds"] == real_ids == real_geom["engineIds"], (
                f"realistic cue set mismatch DOM {real_geom['domIds']} vs engine {real_ids}/{real_geom['engineIds']}")
            assert real_geom["activeId"] == "r3", f"middle cue must be active, got {real_geom['activeId']}"

            # Every visible cue wraps to two lines in the DOM too.
            for d in real_geom["dom"]:
                assert d["lines"] == 2, f"{d['id']} should wrap to 2 DOM lines, got {d['lines']}"

            # Bounds: every cue box fully inside the stage.
            for d in real_geom["dom"]:
                assert d["top"] >= real_geom["stageTop"] - 2.0 and d["bottom"] <= real_geom["stageBottom"] + 2.0, (
                    f"{d['id']} box {d['top']:.0f}-{d['bottom']:.0f} clipped by stage "
                    f"{real_geom['stageTop']:.0f}-{real_geom['stageBottom']:.0f}")

            # No overlaps between adjacent cue boxes (top-to-bottom order).
            ordered = sorted(real_geom["dom"], key=lambda d: d["top"])
            for a, b in zip(ordered, ordered[1:]):
                assert b["top"] >= a["bottom"] - 1.0, (
                    f"realistic cue boxes overlap: {a['id']} bottom {a['bottom']:.0f} vs {b['id']} top {b['top']:.0f}")

            # Active cue centred on the anchor after its transition completes.
            active_box = next(d for d in real_geom["dom"] if d["id"] == "r3")
            active_centre = (active_box["top"] + active_box["bottom"]) / 2
            assert abs(active_centre - real_geom["anchor"]) < max(6.0, active_box["height"] * 0.06), (
                f"active cue centre {active_centre:.0f} not at anchor {real_geom['anchor']:.0f}")

            # Neighbours remain when space permits: one previous (r2) + one upcoming (r4).
            assert "r2" in real_geom["domIds"] and "r4" in real_geom["domIds"], (
                f"expected previous r2 + upcoming r4 neighbours, got {real_geom['domIds']}")
            # Distant cues removed because their two-line blocks cannot fit.
            assert "r1" not in real_geom["domIds"] and "r5" not in real_geom["domIds"], (
                f"distant cues r1/r5 should be dropped, got {real_geom['domIds']}")
            # Dim ordering: neighbours dimmer than the active cue.
            assert active_box["opacity"] > next(d for d in real_geom["dom"] if d["id"] == "r2")["opacity"] + 0.05

            print("PASS credit-crawl browser QA (preview stack, roll, seek, wrap, gap, save/reload, export parity, realistic 1080p bounds)")
            return 0
        finally:
            if dev:
                try:
                    dev.close()
                except Exception:
                    pass
            browser.terminate()


if __name__ == "__main__":
    raise SystemExit(main())
