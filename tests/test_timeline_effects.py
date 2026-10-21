import re
from pathlib import Path

import pytest

from phrasync.footage import TIMELINE_EFFECTS, effects_enabled, prepare_footage

STATIC = Path(__file__).resolve().parent.parent / "static"


def clip(**changes):
    return {"id": "a", "type": "gold-sparkles", "start": 1, "end": 4, "track": 0, "params": {"speed": 34, "amount": 50}, **changes}


def test_effect_clips_switch_export_to_the_browser_renderer():
    assert not effects_enabled({"background": {}, "effects": []})
    assert effects_enabled({"background": {}, "effects": [clip()]})
    assert prepare_footage({"background": {}, "effects": [clip(), clip(id="b", type="pendulum", track=1)]})["effects"][1]["type"] == "pendulum"


@pytest.mark.parametrize("bad, message", [
    (clip(type="lasers"), "Unknown timeline effect"),
    (clip(start=5, end=2), "Invalid effect timing"),
    (clip(track=9), "Invalid effect timing"),
    (clip(params={"speed": 400}), "between 0 and 100"),
    (clip(start="soon"), "must be numbers"),
])
def test_bad_effect_clips_are_rejected(bad, message):
    with pytest.raises(ValueError, match=message):
        prepare_footage({"background": {}, "effects": [bad]})


def test_browser_and_server_list_the_same_seven_effects():
    source = (STATIC / "effects.js").read_text(encoding="utf-8")
    ids = set(re.findall(r'\{ id: "([a-z-]+)", name:', source))
    assert ids == TIMELINE_EFFECTS and len(ids) == 7
    html = (STATIC / "index.html").read_text(encoding="utf-8")
    assert 'id="effectsLane"' in html and 'id="effectGrid"' in html and 'id="effectSliders"' in html
