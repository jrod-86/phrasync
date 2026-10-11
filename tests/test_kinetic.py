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
out.crawl = [];
const crawlSpec = K.preset("credit-crawl");
for (const [name, cueList] of Object.entries(input.crawlCases)) {
  for (const t of input.crawlTimes) {
    const s = K.creditCrawlState(cueList, t, crawlSpec, input.budget);
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
    payload = {
        "cues": cues, "presets": presets, "times": times, "beats": beats,
        "styles": styles, "canvas": CANVAS, "tokens": tokens,
        "beatArgs": beat_args, "budget": 22,
        "crawlCases": crawl_cases, "crawlTimes": crawl_times,
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

    # Credit Crawl cue-stack state: the roll the preview shows must be the roll
    # the exporter composites, cue for cue, frame for frame.
    crawl_spec = kinetic.get_preset("credit-crawl")
    cursor = 0
    for name, cue_list in crawl_cases.items():
        for t in crawl_times:
            state = kinetic.credit_crawl_state(cue_list, t, crawl_spec, 22)
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
