"""Real 4K scene export and measured custom bitrate, without touching user projects."""
import argparse
import json
import re
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karaokesesh.renderer import render_project
from karaokesesh.webgl_renderer import _DevTools
from karaokesesh.media import run_ffmpeg, decode_test, probe_duration


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--origin", default="http://127.0.0.1:5507")
    args = parser.parse_args()
    root = Path("qa_out/render-045")
    root.mkdir(parents=True, exist_ok=True)
    project = {
        "title": "4K compatibility test", "duration": .5,
        "__renderOrigin": args.origin,
        "canvas": {"width": 3840, "height": 2160, "fps": 12, "aspect": "16:9"},
        "background": {"type": "dynamic", "visual": "scene3d", "sceneKit": "ocean",
                       "textSpace": "scene", "daytime": "sunset", "shade": .1},
        "style": {"preset": "kinetic-slam", "fontPreset": "modern", "fontSize": 100},
        "cues": [{"id": "test", "start": 0, "end": .5, "text": "4K TEST", "manual": True}],
        "export": {"crf": 22, "preset": "ultrafast"},
    }
    # Reproduce the user's missing browser codec, but render a real scene and encode real frames.
    original = _DevTools.evaluate
    def missing_codec(self, expression, **kwargs):
        if "const encoderConfig" in expression:
            original(self, "VideoEncoder.isConfigSupported=async()=>({supported:false})")
        return original(self, expression, **kwargs)
    _DevTools.evaluate = missing_codec
    output = root / "4k-fallback.mp4"
    result = render_project(project, output, progress=lambda _, message: print(message, flush=True))
    assert result["width"] == 3840 and result["height"] == 2160
    assert decode_test(output)[0]
    frame = run_ffmpeg(["-i", str(output), "-frames:v", "1", "-f", "image2pipe", "-vcodec", "png", "pipe:1"], check=True)
    from PIL import Image
    import io
    image = Image.open(io.BytesIO(frame.stdout)).convert("RGB")
    assert image.size == (3840, 2160)
    assert max(image.resize((64, 36)).getextrema()[0]) > 20, "Fallback exported a black canvas"
    image.resize((960, 540)).save(root / "4k-frame.png")
    assert not list(root.glob("*.partial.*"))
    print("PASS real WebGL 4K with browser H.264 disabled:", json.dumps(result), flush=True)
    _DevTools.evaluate = original
    project.update(duration=2, canvas={"width": 640, "height": 360, "fps": 30},
                   background={"type": "dynamic", "visual": "aurora", "grain": 0},
                   cues=[{"id": "rate", "start": 0, "end": 2, "text": "150 Mbps"}])
    project["export"]["bitrateMbps"] = 150
    rate_output = root / "150mbps.mp4"
    render_project(project, rate_output)
    measured = rate_output.stat().st_size * 8 / probe_duration(rate_output) / 1e6
    assert measured > 100, measured  # Short clip includes VBV startup; not the old 28 Mbps ceiling.
    assert decode_test(rate_output)[0]
    print(f"PASS custom 150 Mbps export: measured {measured:.1f} Mbps (2-second clip)", flush=True)


if __name__ == "__main__":
    main()
