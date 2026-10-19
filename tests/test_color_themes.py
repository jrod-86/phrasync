from __future__ import annotations

import re
from pathlib import Path

STATIC = Path(__file__).resolve().parent.parent / "static"


def test_twenty_colour_themes_with_valid_colours():
    source = (STATIC / "app-color-themes.js").read_text(encoding="utf-8")
    themes = re.findall(r'\["([^"]+)", "(#[0-9a-f]{6})", "(#[0-9a-f]{6})", "(#[0-9a-f]{6})", "(#[0-9a-f]{6})"\]', source)
    assert len(themes) == 20
    assert len({name for name, *_ in themes}) == 20


def test_the_default_project_colours_are_the_first_theme():
    source = (STATIC / "app-color-themes.js").read_text(encoding="utf-8")
    state = (STATIC / "app-state.js").read_text(encoding="utf-8")
    first = re.search(r'\["Phrasync Neon", "(#\w+)", "(#\w+)", "(#\w+)", "(#\w+)"\]', source).groups()
    for key, colour in zip(["textColor", "accentColor", "accentColor2", "strokeColor"], first):
        assert f'{key}: "{colour}"' in state
