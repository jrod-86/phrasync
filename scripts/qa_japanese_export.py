"""Render a short Japanese sample through the actual MP4 export path."""

import subprocess
from pathlib import Path

from karaokesesh.media import ffmpeg_exe
from karaokesesh.renderer import render_project


def main() -> None:
    output = Path("qa_out/japanese-export-042.mp4")
    project = {
        "title": "Japanese export check",
        "duration": 1.0,
        "canvas": {"width": 640, "height": 360, "fps": 24},
        "background": {"type": "dynamic", "visual": "aurora", "shade": 0.2, "grain": 0},
        "style": {"preset": "minimal", "fontPreset": "impact", "fontSize": 150, "uppercase": False},
        "cues": [{"id": "jp", "start": 0, "end": 1, "text": "日本語 テスト"}],
        "export": {"crf": 24, "preset": "ultrafast"},
    }
    result = render_project(project, output)
    frame = output.with_suffix(".png")
    subprocess.run(
        [ffmpeg_exe(), "-y", "-ss", "0.5", "-i", str(output), "-frames:v", "1", str(frame)],
        check=True,
        capture_output=True,
    )
    print(result)
    print(frame.resolve())


if __name__ == "__main__":
    main()
