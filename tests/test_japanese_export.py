from PIL import ImageFont

from karaokesesh.config import ASSETS_DIR
from karaokesesh.font_utils import load_font, load_font_for_text


def _glyph_signature(font, char):
    mask = font.getmask(char)
    return mask.size, bytes(mask)


def test_japanese_export_falls_back_only_for_missing_glyphs():
    impact = load_font(72, "impact")
    japanese = load_font_for_text(72, "impact", "日本語")

    assert load_font_for_text(72, "impact", "HELLO") is impact
    assert _glyph_signature(japanese, "日") != _glyph_signature(japanese, "本")
    assert _glyph_signature(japanese, "日") != _glyph_signature(japanese, "\U0010FFFF")
    assert japanese.path != impact.path


def test_bundled_font_covers_japanese_without_windows_language_pack():
    bundled = ASSETS_DIR / "NotoSansJP-VF.ttf"
    license_file = ASSETS_DIR / "NotoSansJP-OFL.txt"
    assert bundled.is_file()
    assert "SIL OPEN FONT LICENSE" in license_file.read_text(encoding="utf-8")
    font = ImageFont.truetype(str(bundled), 72)
    assert _glyph_signature(font, "日") != _glyph_signature(font, "本")
    assert _glyph_signature(font, "テ") != _glyph_signature(font, "\U0010FFFF")
