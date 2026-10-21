from pathlib import Path

import pytest

from karaokesesh.ocr import capability_status, ocr_image


def test_reference_image_ocr():
    if not capability_status()["available"]:
        pytest.skip("No OCR engine installed")
    path = Path(__file__).resolve().parent.parent / "assets" / "style_reference.png"
    result = ocr_image(path)
    normalized = result["text"].upper()
    assert "STAND" in normalized
    assert "GROUND" in normalized
