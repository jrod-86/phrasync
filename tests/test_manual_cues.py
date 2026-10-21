"""Manually added lyrics must survive overlaps in preview and MP4 export."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import numpy as np

from karaokesesh import kinetic
from karaokesesh import render_typography
from karaokesesh.renderer import RenderContext
from karaokesesh.subtitles import normalize_cues


ROOT = Path(__file__).resolve().parent.parent


def _cues(manual=True, old_project=False):
    word = lambda text, start, end: [{"text": text, "start": start, "end": end}]
    added = {"id": "added", "start": 1.5, "end": 4.0, "text": "New line", "words": []}
    if manual and not old_project:
        added["manual"] = True
    return [
        {"id": "first", "start": 1, "end": 5, "text": "First", "words": word("First", 1, 5)},
        added,
        {"id": "later-1", "start": 2, "end": 4, "text": "Later", "words": word("Later", 2, 4)},
        {"id": "later-2", "start": 3, "end": 4, "text": "Last", "words": word("Last", 3, 4)},
    ]


@pytest.mark.parametrize("old_project", [False, True])
def test_manual_cue_is_visible_in_python_and_browser(old_project):
    cues = normalize_cues(_cues(old_project=old_project))
    assert cues[1].get("manual") is (None if old_project else True)
    spec = kinetic.resolved_preset({"preset": "kinetic-slam"})
    ids = [cue["id"] for cue in kinetic.active_cues(cues, 3.5, spec)]
    assert ids == ["added"]
    pair = [cues[1], cues[2]]
    assert [cue["id"] for cue in kinetic.active_cues(pair, 3.5, spec)] == ["added"]
    # Once the manual cue ends, the ordinary two-cue transition resumes.
    after = [cue["id"] for cue in kinetic.active_cues(cues, 4.5, spec)]
    assert "added" not in after

    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    source = "global.window = global;\n" + (ROOT / "static/kinetic.js").read_text(encoding="utf-8")
    source += "\nconst cues = " + json.dumps(cues) + ";\n"
    source += """
const spec = VFKinetic.resolvedPreset({preset: 'kinetic-slam'});
console.log(JSON.stringify({during: VFKinetic.activeCues(cues, 3.5, spec).map(c => c.id),
  pair: VFKinetic.activeCues([cues[1], cues[2]], 3.5, spec).map(c => c.id),
  after: VFKinetic.activeCues(cues, 4.5, spec).map(c => c.id)}));
"""
    result = subprocess.run([node, "-"], input=source, capture_output=True,
                            text=True, encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr
    browser = json.loads(result.stdout)
    assert browser["during"] == ids
    assert browser["pair"] == ["added"]
    assert browser["after"] == after


def test_ordinary_untimed_cues_keep_their_two_cue_dissolve():
    spec = kinetic.resolved_preset({"preset": "kinetic-slam"})
    cues = [{"id": "first", "start": 1, "end": 2, "text": "First", "words": []},
            {"id": "next", "start": 2, "end": 3, "text": "Next", "words": []}]
    assert [cue["id"] for cue in kinetic.active_cues(cues, 2.01, spec)] == ["first", "next"]


def test_mp4_text_layer_uses_manual_cue_during_overlap(monkeypatch):
    cues = normalize_cues(_cues())
    project = {"style": {"preset": "kinetic-slam", "fontSize": 40}, "timing": {"offset": 0}}
    ctx = RenderContext(project, 320, 180, 30, 5, 150, cues, None, None, None, np.zeros(150))
    rendered = []

    def record(_ctx, cue, *_args):
        rendered.append(cue["id"])
        return None

    monkeypatch.setattr(render_typography, "_render_kinetic", record)
    render_typography.render_text_layer(ctx, 3.5)
    assert rendered == ["added"]


def test_new_manual_cues_keep_their_marker_through_normalization():
    source = (ROOT / "static/app.js").read_text(encoding="utf-8")
    ui = (ROOT / "static/app-ui.js").read_text(encoding="utf-8")
    assert 'text: "NEW LYRIC", words: [], manual: true' in source
    assert 'cue.manual === true ? { manual: true }' in ui
    assert normalize_cues([{"start": 1, "end": 2, "text": "Added", "manual": True}])[0]["manual"] is True
