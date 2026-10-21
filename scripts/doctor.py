from __future__ import annotations

import json
import platform
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaokesesh.font_utils import font_status
from karaokesesh.media import ffmpeg_exe
from karaokesesh.ocr import capability_status as ocr_status
from karaokesesh.transcribe import capability_status as transcription_status


def main() -> None:
    report = {
        "python": sys.version,
        "platform": platform.platform(),
        "ffmpeg": None,
        "ocr": ocr_status(),
        "transcription": transcription_status(),
        "fonts": font_status(),
    }
    try:
        report["ffmpeg"] = {"available": True, "path": ffmpeg_exe()}
    except Exception as exc:
        report["ffmpeg"] = {"available": False, "error": str(exc)}
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
