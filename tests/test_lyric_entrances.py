"""Exercise actual browser timing helpers without a GPU or screenshot clock."""
import shutil
import subprocess
from pathlib import Path

import pytest
from phrasync import kinetic
from phrasync.renderer import RenderContext
from phrasync.render_typography import render_text_layer
import numpy as np


def test_3d_preloads_geometry_without_anticipating_the_first_word():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node.js is not installed")
    static = Path(__file__).resolve().parent.parent / "static"
    lyrics = (static / "app-lyrics.js").read_text(encoding="utf-8")
    helper = lyrics[lyrics.index("function preset3D("):lyrics.index("function updateLyricFrame(")]
    source = "global.window = global;\n" + (static / "kinetic.js").read_text(encoding="utf-8")
    source += "\nconst project = {background: {}}; const sceneSpeedFor = () => 2;\n" + helper
    source += """
const assert = require('node:assert/strict');
const cue = {start: 2, end: 3, text: 'Hello', words: [{text: 'Hello', start: 2, end: 3}]};
for (const preset of VFKinetic.PRESET_ORDER) {
  for (const lead of [0, .06, .2, .5]) {
    const spec = VFKinetic.resolvedPreset({preset, wordLead: lead});
    const lifecycle = preset3D(spec, true);
    const visible = preset3D(spec);
    assert.equal(lifecycle.lead, .6);
    assert.equal(visible.lead, lead);
    assert.equal(VFKinetic.activeCues([cue], 1.5, lifecycle).length, 1);
    const word = VFKinetic.cueWords(cue)[0];
    assert.equal(VFKinetic.wordState(word, cue, 1.5, visible, 0).opacity, 0);
    assert.equal(VFKinetic.wordState(word, cue, 1.999, visible, 0).opacity, 0);
    const paddedCue = {...cue, start: 1};
    assert.equal(VFKinetic.wordState(word, paddedCue, 1.999, visible, 0).opacity, 0);
    if (spec.hold === 'word') {
      const nextWord = {...word, start: 2.5, end: 3};
      assert.equal(VFKinetic.wordState(nextWord, cue, 2.49, visible, 0).opacity, 0);
    }
    assert.ok(VFKinetic.wordState(word, cue, 2.03, visible, 0).opacity > 0);
    assert.equal(cue.words[0].end, 3);
  }
}
"""
    result = subprocess.run([node, "-"], input=source, capture_output=True, text=True,
                            encoding="utf-8", timeout=30)
    assert result.returncode == 0, result.stderr


@pytest.mark.parametrize("preset", list(kinetic.PRESETS))
@pytest.mark.parametrize("lead", [0, .06, .5])
def test_flat_export_has_no_glyph_pixels_before_phrase_onset(preset, lead):
    cue = {"id": "opening", "start": .5, "end": 3, "text": "Hello world",
           "words": [{"text": "Hello", "start": 1, "end": 1.8},
                     {"text": "world", "start": 2, "end": 3}]}
    project = {"style": {"preset": preset, "wordLead": lead, "fontSize": 110},
               "timing": {"offset": 0}, "canvas": {"width": 640, "height": 360}}
    ctx = RenderContext(project, 640, 360, 30, 3, 90, [cue], None, None, None, np.zeros(90))
    if preset == "credit-crawl":
        # The crawl is a rolling stack: a line is readable from its cue start,
        # before its first timed word, exactly as the plan requires ("readable
        # in advance"). Its words still fill only on their own timing.
        before = render_text_layer(ctx, .999)
        assert before is not None and before.getchannel("A").getbbox() is not None
        after = render_text_layer(ctx, 1.12)
        assert after is not None and after.getchannel("A").getbbox() is not None
        return
    before = render_text_layer(ctx, .999)
    assert before is None or before.getchannel("A").getbbox() is None
    after = render_text_layer(ctx, 1.12)
    assert after is not None and after.getchannel("A").getbbox() is not None
