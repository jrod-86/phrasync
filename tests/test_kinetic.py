"""Preview/export parity for the kinetic lyric engine.

static/kinetic.js drives the browser preview and phrasync/kinetic.py drives the
MP4 export. They must agree, so this evaluates the JavaScript in Node and
compares it against the Python implementation over a grid of inputs. When Node
is unavailable the JS half is skipped and the Python invariants still run.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from phrasync import kinetic

ROOT = Path(__file__).resolve().parent.parent
KINETIC_JS = ROOT / "static" / "kinetic.js"

CUE = {"id": "cue-1", "start": 2.0, "end": 6.0, "text": "hold the line tonight", "words": []}
TIMED_CUE = {
    "id": "cue-2",
    "start": 1.0,
    "end": 4.0,
    "text": "one two three",
    "words": [
        {"text": "one", "start": 1.0, "end": 1.6},
        {"text": "two", "start": 1.8, "end": 2.4},
        {"text": "three", "start": 2.6, "end": 3.9},
    ],
}
STYLE = {"fontSize": 160, "maxWidth": 88, "fontPreset": "impact"}
CANVAS = {"width": 1920, "height": 1080}

HARNESS = r"""
const fs = require("fs");
global.window = {};
new Function(fs.readFileSync(process.argv[2], "utf8"))();
const K = global.window.VFKinetic;
const input = JSON.parse(fs.readFileSync(process.argv[3], "utf8"));

const out = { words: {}, states: [], budget: [], focus: {}, beat: [], lines: {} };

for (const [name, cue] of Object.entries(input.cues)) {
  out.words[name] = K.cueWords(cue).map(w => [w.text, +w.start.toFixed(6), +w.end.toFixed(6)]);
}
for (const [name, cue] of Object.entries(input.cues)) {
  const words = K.cueWords(cue);
  for (const presetId of input.presets) {
    const spec = K.preset(presetId);
    for (const t of input.times) {
      for (const beat of input.beats) {
        for (const word of words) {
          const s = K.wordState(word, cue, t, spec, beat);
          out.states.push([
            name, presetId, t, beat, word.text,
            s.visible ? 1 : 0,
            +s.opacity.toFixed(6), +s.scale.toFixed(6), +s.dx.toFixed(6),
            +s.dy.toFixed(6), +s.rotate.toFixed(6), +s.blur.toFixed(6),
            +s.fill.toFixed(6), +s.fillAlpha.toFixed(6), +s.glow.toFixed(6), s.role
          ]);
        }
      }
    }
  }
}
out.budget = [];
for (const presetId of input.presets)
  for (const style of input.styles)
    out.budget.push(K.charBudget(style, input.canvas, K.preset(presetId)));
for (const token of input.tokens) out.focus[token] = +K.focusScale(token).toFixed(6);
for (const [t, bpm, offset] of input.beatArgs) out.beat.push(+K.beatPulse(t, bpm, offset).toFixed(6));
for (const presetId of input.presets) {
  const words = K.cueWords(input.cues.plain);
  out.lines[presetId] = K.layoutLines(words, K.preset(presetId), input.budget)
    .map(line => line.map(w => w.text));
}
out.genuine = {};
for (const [name, cue] of Object.entries(input.cues)) {
  out.genuine[name] = K.hasGenuineWordTiming(cue) ? 1 : 0;
}
out.viewport = input.crawlStyles.map(style => {
  const v = K.crawlViewport(style, input.canvas, K.preset("credit-crawl"));
  return [+v.above.toFixed(6), +v.below.toFixed(6)];
});
const crawlSpec = K.preset("credit-crawl");
const crawlViewport = K.crawlViewport(input.crawlStyles[0], input.canvas, crawlSpec);
out.crawl = [];
for (const [name, cueList] of Object.entries(input.crawlCases)) {
  for (const t of input.crawlTimes) {
    const s = K.creditCrawlState(cueList, t, crawlSpec, input.budget, crawlViewport);
    out.crawl.push([name, t, s.activeIndex, s.cues.map(c => [
      c.index, +c.offset.toFixed(6), +c.opacity.toFixed(6), c.active ? 1 : 0
    ])]);
  }
}
process.stdout.write(JSON.stringify(out));
"""


def _node_results(payload: dict) -> dict:
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed; skipping cross-engine parity check")
    tmp = ROOT / ".kinetic_parity"
    tmp.mkdir(exist_ok=True)
    harness = tmp / "harness.js"
    data = tmp / "input.json"
    try:
        harness.write_text(HARNESS, encoding="utf-8")
        data.write_text(json.dumps(payload), encoding="utf-8")
        result = subprocess.run(
            [node, str(harness), str(KINETIC_JS), str(data)],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            pytest.fail(f"Node harness failed: {result.stderr[:800]}")
        return json.loads(result.stdout)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_python_word_timing_is_monotonic():
    words = kinetic.cue_words(CUE)
    assert len(words) == 4
    assert words[0]["start"] == pytest.approx(CUE["start"])
    for previous, current in zip(words, words[1:]):
        assert current["start"] >= previous["start"]
        assert current["end"] > current["start"]


def test_every_preset_has_a_python_and_js_twin():
    js = KINETIC_JS.read_text(encoding="utf-8")
    for preset_id in kinetic.PRESETS:
        assert f'"{preset_id}"' in js, f"{preset_id} missing from static/kinetic.js"


def test_credit_crawl_blocks_never_collide():
    """Wrapped cues occupy their true height in stack space, so neighbours
    never collide at any time: offset_j - offset_i == c_j - c_i >=
    lines_i/2 + blockGap + lines_j/2, and the centre term cancels."""
    spec = kinetic.get_preset("credit-crawl")
    cases = {
        "wrapped": [
            {"id": "w1", "start": 0.0, "end": 2.0, "text": "THIS IS A VERY LONG\nFIRST LINE WRAPPING", "words": []},
            {"id": "w2", "start": 2.0, "end": 4.0, "text": "SECOND LINE AFTER IT", "words": []},
            {"id": "w3", "start": 4.0, "end": 6.0, "text": "THIRD LINE HERE", "words": []},
        ],
        "overlap": [
            {"id": "o1", "start": 0.0, "end": 1.0, "text": "quick one", "words": []},
            {"id": "o2", "start": 1.2, "end": 2.2, "text": "quick two", "words": []},
            {"id": "o3", "start": 1.4, "end": 2.6, "text": "quick three", "words": []},
        ],
    }
    for name, cue_list in cases.items():
        for t in [0.0, 0.4, 1.0, 1.9, 2.0, 2.2, 3.0, 4.0, 5.0]:
            state = kinetic.credit_crawl_state(cue_list, t, spec, 24)
            heights = [
                max(1, len(kinetic.layout_lines(kinetic.cue_words(item["cue"]), spec, 24)))
                for item in state["cues"]
            ]
            for (a, ha), (b, hb) in zip(zip(state["cues"], heights), list(zip(state["cues"], heights))[1:]):
                assert b["offset"] - a["offset"] >= ha / 2 + hb / 2 - 1e-9, (
                    f"{name} t={t} blocks {a['cue']['id']}/{b['cue']['id']} collide"
                )


def test_phrase_only_cues_have_no_estimated_word_wipe():
    """Codex finding 2: phrase-only SRT cues must not present estimated word
    timing as word-accurate. has_genuine_word_timing is False for them, and
    the crawl word state fills the whole phrase together over the step ease
    instead of wiping word by word."""
    spec = kinetic.get_preset("credit-crawl")
    phrase_cue = {"id": "p1", "start": 2.0, "end": 6.0,
                  "text": "hold the line tonight", "words": []}
    timed_cue = {
        "id": "p2", "start": 1.0, "end": 4.0, "text": "one two three",
        "words": [
            {"text": "one", "start": 1.0, "end": 1.6},
            {"text": "two", "start": 1.8, "end": 2.4},
            {"text": "three", "start": 2.6, "end": 3.9},
        ],
    }
    assert kinetic.has_genuine_word_timing(phrase_cue) is False
    assert kinetic.has_genuine_word_timing(timed_cue) is True
    # A words array that does not line up with the tokens is not genuine either.
    mismatched = {"id": "p3", "start": 0.0, "end": 2.0, "text": "a b c",
                  "words": [{"text": "a", "start": 0.0, "end": 1.0}]}
    assert kinetic.has_genuine_word_timing(mismatched) is False

    words = kinetic.cue_words(phrase_cue)
    # Every word of the phrase shares the same fill at any instant: the phrase
    # switches to the accent colour together, no per-word wipe.
    for t in [1.0, 2.0, 2.1, 3.0, 5.99, 6.0, 7.0]:
        fills = {kinetic.word_state(w, phrase_cue, t, spec).fill for w in words}
        assert len(fills) == 1, f"t={t} produced a per-word wipe: {fills}"
    # Pending before the cue, filled after it, eased during it.
    assert kinetic.word_state(words[0], phrase_cue, 1.0, spec).role == "pending"
    assert kinetic.word_state(words[0], phrase_cue, 1.0, spec).fill == 0.0
    mid = kinetic.word_state(words[0], phrase_cue, 2.1, spec)
    assert mid.role == "active" and 0.0 < mid.fill < 1.0
    assert kinetic.word_state(words[0], phrase_cue, 6.5, spec).fill == 1.0

    # Genuine word timing still wipes word by word.
    timed_words = kinetic.cue_words(timed_cue)
    fills_at_2_0 = {kinetic.word_state(w, timed_cue, 2.0, spec).fill for w in timed_words}
    assert len(fills_at_2_0) > 1, "genuine word timings collapsed into a phrase fill"


def test_overlap_keeps_exactly_one_active_cue():
    """Codex finding 3: when cues overlap in time, exactly one cue — the most
    recently started one that is still playing — is active; older overlapping
    cues are treated as completed/previous."""
    spec = kinetic.get_preset("credit-crawl")
    cues = [
        {"id": "o1", "start": 0.0, "end": 3.0, "text": "first long cue", "words": []},
        {"id": "o2", "start": 1.0, "end": 4.0, "text": "second cue", "words": []},
        {"id": "o3", "start": 2.0, "end": 5.0, "text": "third cue", "words": []},
    ]
    for t in [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.5, 5.5]:
        state = kinetic.credit_crawl_state(cues, t, spec, 22)
        active = [c for c in state["cues"] if c["active"]]
        assert len(active) <= 1, f"t={t} has {len(active)} active cues"
        if active:
            expected_id = {0.5: "o1", 1.0: "o2", 1.5: "o2", 2.0: "o3",
                           2.5: "o3", 3.0: "o3", 3.5: "o3", 4.5: "o3"}[t]
            assert active[0]["cue"]["id"] == expected_id, (
                f"t={t} active cue is {active[0]['cue']['id']}, expected {expected_id}")
            # The active cue owns offset 0 at rest (transition passed).
            if t >= 3.0:
                assert abs(active[0]["offset"]) < 1e-9
        else:
            # t=5.5: every cue has ended, so nothing is active; the last cue
            # still holds the centre as a completed cue.
            assert t == 5.5
            assert state["activeIndex"] == 2
            assert state["cues"], "gap after the last cue left a blank frame"
            anchor = next(c for c in state["cues"] if c["index"] == state["activeIndex"])
            assert abs(anchor["offset"]) < 1e-9


def test_viewport_keeps_wrapped_blocks_inside():
    """Codex finding 1: with a viewport supplied, a previous/upcoming cue is
    shown only while its COMPLETE wrapped block fits inside the frame; the
    most distant cue is dropped first and prevLines/nextLines stay hard caps."""
    spec = kinetic.get_preset("credit-crawl")
    cues = [
        {"id": "w1", "start": 0.0, "end": 2.0,
         "text": "THIS IS A VERY LONG WRAPPING FIRST LINE THAT BREAKS INTO TWO LINES",
         "words": []},
        {"id": "w2", "start": 2.0, "end": 4.0, "text": "SECOND LINE HERE", "words": []},
        {"id": "w3", "start": 4.0, "end": 6.0, "text": "THIRD LINE HERE", "words": []},
        {"id": "w4", "start": 6.0, "end": 8.0, "text": "FOURTH LINE HERE", "words": []},
    ]
    budget = 24
    # A viewport that only fits ~2 line units above/below: a 2-line wrapped
    # block cannot be a neighbour, but it is never shrunk when it is the active cue.
    tight = {"above": 2.0, "below": 2.0}
    state = kinetic.credit_crawl_state(cues, 3.0, spec, budget, tight)
    ids = [c["cue"]["id"] for c in state["cues"]]
    assert "w1" not in ids, f"wrapped w1 block left outside the viewport: {ids}"
    assert "w2" in ids and "w3" in ids
    for item in state["cues"]:
        lines = max(1, len(kinetic.layout_lines(kinetic.cue_words(item["cue"]), spec, budget)))
        half = lines / 2
        assert item["offset"] - half >= -2.0 - 0.02 or item["active"], (
            f"{item['cue']['id']} block pokes above the viewport")
        assert item["offset"] + half <= 2.0 + 0.02 or item["active"], (
            f"{item['cue']['id']} block pokes below the viewport")
    # The active cue is never dropped to fit neighbours.
    state = kinetic.credit_crawl_state(cues, 1.0, spec, budget, tight)
    active = [c for c in state["cues"] if c["active"]]
    assert len(active) == 1 and active[0]["cue"]["id"] == "w1"
    # prevLines/nextLines remain hard caps even with a generous viewport.
    wide = {"above": 50.0, "below": 50.0}
    state = kinetic.credit_crawl_state(cues, 3.0, spec, budget, wide)
    crawl_cfg = spec.crawl or {}
    assert len(state["cues"]) <= 1 + crawl_cfg.get("prevLines", 2) + crawl_cfg.get("nextLines", 2)
    # Without a viewport the old behaviour stands: neighbours are capped only
    # by prevLines/nextLines (parity with callers that pass none).
    state = kinetic.credit_crawl_state(cues, 3.0, spec, budget)
    assert "w1" in [c["cue"]["id"] for c in state["cues"]]


def test_engines_agree():
    presets = list(kinetic.PRESETS)
    times = [0.5, 1.9, 2.0, 2.05, 2.3, 3.0, 4.4, 5.9, 6.0, 6.15, 6.4, 7.5]
    beats = [0.0, 0.7]
    tokens = ["I", "love", "passwords", "certainty", "a"]
    beat_args = [[1.0, 120.0, 0.2], [2.34, 139.67, 0.4094], [5.0, 0.0, 0.0]]
    styles = [
        {"fontSize": 160, "maxWidth": 88, "fontPreset": "impact"},
        {"fontSize": 90, "maxWidth": 70, "fontPreset": "modern"},
        {"fontSize": 240, "maxWidth": 96, "fontPreset": "mono"},
    ]
    cues = {"plain": CUE, "timed": TIMED_CUE}
    crawl_cases = {
        "even": [
            {"id": "c1", "start": 0.0, "end": 2.0, "text": "first line here", "words": []},
            {"id": "c2", "start": 2.0, "end": 4.0, "text": "second line here", "words": []},
            {"id": "c3", "start": 4.0, "end": 6.0, "text": "third line here", "words": []},
            {"id": "c4", "start": 6.0, "end": 8.0, "text": "fourth line here", "words": []},
            {"id": "c5", "start": 8.0, "end": 10.0, "text": "fifth line here", "words": []},
        ],
        "gap": [
            {"id": "g1", "start": 0.0, "end": 1.5, "text": "before the break", "words": []},
            {"id": "g2", "start": 5.0, "end": 7.0, "text": "after the break", "words": []},
        ],
        "overlap": [
            {"id": "o1", "start": 0.0, "end": 1.0, "text": "quick one", "words": []},
            {"id": "o2", "start": 1.2, "end": 2.2, "text": "quick two", "words": []},
            {"id": "o3", "start": 1.4, "end": 2.6, "text": "quick three", "words": []},
        ],
        "wrapped": [
            {"id": "w1", "start": 0.0, "end": 2.0, "text": "THIS IS A VERY LONG\nFIRST LINE WRAPPING", "words": []},
            {"id": "w2", "start": 2.0, "end": 4.0, "text": "SECOND LINE AFTER IT", "words": []},
            {"id": "w3", "start": 4.0, "end": 6.0, "text": "THIRD LINE HERE", "words": []},
        ],
    }
    crawl_times = [-1.0, 0.0, 0.2, 1.0, 1.9, 2.0, 2.2, 3.0, 4.0, 5.5, 6.0, 7.9, 8.0, 9.5, 12.0]
    crawl_styles = [
        {"fontSize": 160, "maxWidth": 88, "fontPreset": "impact", "lineGap": -8, "positionY": 52},
        {"fontSize": 44, "maxWidth": 88, "fontPreset": "modern", "lineGap": 0, "positionY": 52},
    ]
    payload = {
        "cues": cues, "presets": presets, "times": times, "beats": beats,
        "styles": styles, "canvas": CANVAS, "tokens": tokens,
        "beatArgs": beat_args, "budget": 22,
        "crawlCases": crawl_cases, "crawlTimes": crawl_times,
        "crawlStyles": crawl_styles,
    }
    js = _node_results(payload)

    for name, cue in cues.items():
        expected = [
            [word["text"], round(word["start"], 6), round(word["end"], 6)]
            for word in kinetic.cue_words(cue)
        ]
        assert js["words"][name] == expected, f"cue_words mismatch for {name}"

    index = 0
    for name, cue in cues.items():
        words = kinetic.cue_words(cue)
        for preset_id in presets:
            spec = kinetic.get_preset(preset_id)
            for t in times:
                for beat in beats:
                    for word in words:
                        state = kinetic.word_state(word, cue, t, spec, beat)
                        row = js["states"][index]
                        index += 1
                        label = f"{name}/{preset_id}/t={t}/beat={beat}/{word['text']}"
                        assert row[:5] == [name, preset_id, t, beat, word["text"]], label
                        assert row[5] == (1 if state.visible else 0), label
                        for offset, value in enumerate(
                            [state.opacity, state.scale, state.dx, state.dy,
                             state.rotate, state.blur, state.fill, state.fill_alpha,
                             state.glow]
                        ):
                            assert row[6 + offset] == pytest.approx(value, abs=1e-6), (
                                f"{label} field {offset}"
                            )
                        assert row[15] == state.role, label
    assert index == len(js["states"])

    cursor = 0
    for preset_id in presets:
        spec = kinetic.get_preset(preset_id)
        for style in styles:
            assert js["budget"][cursor] == kinetic.char_budget(style, CANVAS, spec), (preset_id, style)
            cursor += 1
    for token in tokens:
        assert js["focus"][token] == pytest.approx(kinetic.focus_scale(token), abs=1e-6)
    for row, (t, bpm, offset) in zip(js["beat"], beat_args):
        assert row == pytest.approx(kinetic.beat_pulse(t, bpm, offset), abs=1e-6)

    words = kinetic.cue_words(CUE)
    for preset_id in presets:
        spec = kinetic.get_preset(preset_id)
        expected = [[word["text"] for word in line] for line in kinetic.layout_lines(words, spec, 22)]
        assert js["lines"][preset_id] == expected, f"layout mismatch for {preset_id}"

    # Genuine word timing: phrase-only SRT cues must report False, cues with
    # stored word arrays that line up with their tokens must report True.
    for name, cue in cues.items():
        expected = kinetic.has_genuine_word_timing(cue)
        assert bool(js["genuine"][name]) is expected, f"hasGenuineWordTiming mismatch for {name}"

    # Viewport bounds: identical from style + canvas in both engines.
    crawl_spec = kinetic.get_preset("credit-crawl")
    cursor = 0
    for style in crawl_styles:
        viewport = kinetic.crawl_viewport(style, CANVAS, crawl_spec)
        row = js["viewport"][cursor]
        cursor += 1
        assert row[0] == pytest.approx(viewport["above"], abs=1e-6), f"viewport above mismatch {style}"
        assert row[1] == pytest.approx(viewport["below"], abs=1e-6), f"viewport below mismatch {style}"

    # Credit Crawl cue-stack state: the roll the preview shows must be the roll
    # the exporter composites, cue for cue, frame for frame.
    crawl_viewport = kinetic.crawl_viewport(crawl_styles[0], CANVAS, crawl_spec)
    cursor = 0
    for name, cue_list in crawl_cases.items():
        for t in crawl_times:
            state = kinetic.credit_crawl_state(cue_list, t, crawl_spec, 22, crawl_viewport)
            row = js["crawl"][cursor]
            cursor += 1
            label = f"crawl {name} t={t}"
            assert row[:2] == [name, t], label
            assert row[2] == state["activeIndex"], f"{label} activeIndex"
            assert len(row[3]) == len(state["cues"]), f"{label} cue count"
            for js_cue, cue in zip(row[3], state["cues"]):
                assert js_cue[0] == cue["index"], f"{label} index"
                assert js_cue[1] == pytest.approx(cue["offset"], abs=1e-6), f"{label} offset"
                assert js_cue[2] == pytest.approx(cue["opacity"], abs=1e-6), f"{label} opacity"
                assert js_cue[3] == (1 if cue["active"] else 0), f"{label} active"
    assert cursor == len(js["crawl"])
