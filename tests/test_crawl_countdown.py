"""Credit Crawl countdown dots in the exported video."""

import numpy as np

from karaokesesh.render_typography import render_text_layer
from karaokesesh.renderer import RenderContext

ACCENT = (255, 40, 40)
CUES = [
    {"id": "c1", "start": 12.0, "end": 15.0, "text": "back again", "words": []},
    {"id": "c2", "start": 15.0, "end": 18.0, "text": "and again", "words": []},
]


def _context(style_extra=None):
    style = {"preset": "credit-crawl", "fontSize": 120, "accentColor": "#ff2828",
             "accentColor2": "#ff2828", "textColor": "#ffffff", "strokeWidth": 0,
             "shadow": 0, "positionY": 50, **(style_extra or {})}
    project = {"style": style, "timing": {}, "canvas": {"width": 960, "height": 540}}
    return RenderContext(project=project, width=960, height=540, fps=30, duration=20.0,
                         frame_count=600, cues=CUES, audio=None, background_asset=None,
                         font_asset=None, envelope=np.zeros(600))


def _accent_left_of_text(layer):
    """Count accent dot blobs left of the leftmost white text pixel."""
    pixels = np.asarray(layer).astype(int)
    alpha = pixels[..., 3] > 60
    white = alpha & (pixels[..., 0] > 200) & (pixels[..., 1] > 200)
    red = alpha & (pixels[..., 0] > 200) & (pixels[..., 1] < 90)
    text_left = np.argwhere(white)[:, 1].min()
    columns = red[:, :text_left].any(axis=0)
    blobs = int(np.sum(columns[1:] & ~columns[:-1]) + columns[0])
    return blobs


def test_dots_count_down_before_the_line_after_a_long_intro():
    ctx = _context()
    assert _accent_left_of_text(render_text_layer(ctx, 9.5)) == 3
    assert _accent_left_of_text(render_text_layer(ctx, 10.5)) == 2
    assert _accent_left_of_text(render_text_layer(ctx, 11.5)) == 1
    assert _accent_left_of_text(render_text_layer(ctx, 8.0)) == 0
