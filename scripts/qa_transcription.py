"""Run the local transcription gauntlet against one audio/video asset."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from karaokesesh.settings import apply_saved_settings
from karaokesesh.transcribe import transcribe_audio


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="backslashreplace")

    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--model", default="large-v3")
    parser.add_argument("--language", default="auto")
    parser.add_argument("--vad", action="store_true")
    args = parser.parse_args()

    apply_saved_settings()
    result = transcribe_audio(
        args.source,
        model_name=args.model,
        language=args.language,
        vad_filter=args.vad,
        progress=lambda value, message: print(f"{value:6.1%}  {message}", flush=True),
    )
    print(
        f"mode={result['languageMode']} dominant={result['language']} "
        f"probability={result['languageProbability']:.4f}"
    )
    for span in result.get("languageSpans") or []:
        print(f"  span {span['start']:8.2f}-{span['end']:8.2f}  {span['language']}  p={span['probability']}")
    print(f"gauntlet={result['transcriptionGauntlet']}")
    for segment in result["rawSegments"]:
        tag = segment.get("language") or "--"
        print(f"{segment['start']:8.2f}-{segment['end']:8.2f}  [{tag}]  {segment['text']}")
    return 1 if result["transcriptionGauntlet"]["unstableSegments"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
