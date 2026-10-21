from __future__ import annotations

import math
import wave
from pathlib import Path

import numpy as np
import pytest
from PIL import Image

from karaokesesh.font_utils import resolve_font_path
from karaokesesh.media import decode_test, probe_duration, run_ffmpeg
from karaokesesh.qa import postflight_render
from karaokesesh.renderer import render_project
from karaokesesh.storage import delete_asset, store_path


def make_tone(path: Path, duration: float = 2.0, rate: int = 16000) -> None:
    t = np.arange(int(duration * rate), dtype=np.float32) / rate
    signal = (np.sin(2 * math.pi * 220 * t) * 0.22 * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(signal.tobytes())


def make_project(*, duration: float, background: dict, font_asset_id: str | None = None) -> dict:
    return {
        "title": "Export matrix",
        "duration": duration,
        "canvas": {"width": 320, "height": 320, "fps": 12},
        "background": {"shade": 0.15, "grain": 0.04, **background},
        "style": {
            "preset": "bold-stack",
            "fontPreset": "modern",
            "fontAssetId": font_asset_id,
            "fontSize": 112,
            "topScale": 0.58,
            "maxWidth": 88,
            "positionY": 52,
            "lineGap": -4,
            "textColor": "#ffffff",
            "accentColor": "#ff3d7f",
            "accentColor2": "#8f5bff",
            "strokeColor": "#05040c",
            "strokeWidth": 2,
            "shadow": 3,
            "uppercase": True,
            "animation": 1,
        },
        "cues": [{"id": "late", "start": 0.0, "end": 1.1, "text": "SAVE THEN\nEXPORT"}],
        "export": {"crf": 28, "preset": "ultrafast"},
    }


def test_render_dynamic_mp4(tmp_path):
    tone = tmp_path / "tone.wav"
    make_tone(tone)
    asset = store_path("audio", tone)
    output = tmp_path / "smoke.mp4"
    project = {
        "title": "Smoke",
        "canvas": {"width": 640, "height": 360, "fps": 15},
        "audioAssetId": asset.id,
        "background": {
            "type": "dynamic",
            "visual": "equalizer",
            "shade": 0.2,
            "visualIntensity": 0.7,
            "grain": 0.08,
            "backgroundColor": "#080812",
            "secondaryColor": "#5cd7ff",
        },
        "style": {
            "preset": "bold-stack",
            "fontPreset": "impact",
            "fontSize": 150,
            "topScale": 0.58,
            "maxWidth": 88,
            "positionY": 52,
            "lineGap": -8,
            "textColor": "#f3d7ff",
            "accentColor": "#df5cff",
            "accentColor2": "#a64dff",
            "strokeColor": "#090811",
            "strokeWidth": 3,
            "shadow": 7,
            "uppercase": True,
            "animation": "pop",
        },
        "cues": [
            {"id": "a", "start": 0, "end": 1, "text": "STAND YOUR\nGROUND"},
            {"id": "b", "start": 1, "end": 2, "text": "KEEP MOVING"},
        ],
        "export": {"crf": 22, "preset": "ultrafast"},
    }
    try:
        result = render_project(project, output)
        assert output.exists()
        assert result["frames"] == 30
        report = postflight_render(output, 2.0)
        assert report.ok, report.public()
    finally:
        delete_asset(asset.id)


def test_render_flat_odyssey_mp4(tmp_path):
    visual = "scene"
    output = tmp_path / f"{visual}.mp4"
    project = make_project(
        duration=0.25,
        background={
            "type": "dynamic", "visual": visual, "textSpace": "flat",
            "sceneKit": "japan", "sceneDirection": "forward",
            "sceneSpeed": 1, "sceneDensity": 1, "sceneSeed": 1337,
            "weather": "rain", "daytime": "sunset", "season": "summer",
        },
    )
    result = render_project(project, output)
    assert result["frames"] == 14
    assert output.exists()
    assert decode_test(output)[0]


@pytest.mark.parametrize("background_kind", ["image", "video"])
def test_render_media_backgrounds_without_audio(tmp_path, background_kind):
    source = tmp_path / ("background.png" if background_kind == "image" else "background.mp4")
    if background_kind == "image":
        y, x = np.mgrid[0:180, 0:320]
        pixels = np.stack(((x * 3) % 255, (y * 5) % 255, (x + y * 2) % 255), axis=-1).astype(np.uint8)
        Image.fromarray(pixels, "RGB").save(source)
    else:
        run_ffmpeg([
            "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=0.35",
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(source),
        ])

    background_asset = store_path(background_kind, source)
    font_path = resolve_font_path("modern")
    assert font_path is not None
    font_asset = store_path("font", font_path)
    output = tmp_path / f"{background_kind}.mp4"
    project = make_project(
        duration=0.5,
        background={"type": background_kind, "assetId": background_asset.id, "motion": 0.2},
        font_asset_id=font_asset.id,
    )
    try:
        result = render_project(project, output)
        assert result["duration"] == pytest.approx(1.1)
        assert result["frames"] == 14
        assert probe_duration(output) == pytest.approx(1.1, abs=0.12)
        assert decode_test(output)[0]
    finally:
        delete_asset(background_asset.id)
        delete_asset(font_asset.id)


def test_subtitle_mode_uses_one_video_for_picture_and_audio(tmp_path):
    source = tmp_path / "spoken-source.mp4"
    run_ffmpeg([
        "-y", "-f", "lavfi", "-i", "testsrc2=size=320x180:rate=12:duration=0.6",
        "-f", "lavfi", "-i", "sine=frequency=330:sample_rate=16000:duration=0.6",
        "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source),
    ])
    asset = store_path("video", source)
    output = tmp_path / "subtitled.mp4"
    project = make_project(
        duration=0.6,
        background={"type": "video", "assetId": asset.id, "motion": 0},
    )
    project.update({
        "mode": "subtitles", "audioAssetId": asset.id,
        "sourceAssetId": asset.id, "sourceKind": "video",
    })
    try:
        result = render_project(project, output)
        assert result["duration"] == pytest.approx(0.6, abs=0.08)
        assert decode_test(output)[0]
        assert probe_duration(output) == pytest.approx(0.6, abs=0.12)
    finally:
        delete_asset(asset.id)
