"""Real isolated download probe: python scripts/qa_model_download.py <folder>."""
import json
import os
from pathlib import Path
import sys
import time

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(root / "hf")
os.environ["HF_XET_CACHE"] = str(root / "xet")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from karaokesesh.model_download import ensure_model, downloaded_bytes, model_path

events = []
started = time.monotonic()


def progress(ratio, message, details=None):
    event = {"elapsed": round(time.monotonic() - started, 2), "ratio": ratio,
             "message": message, **(details or {}),
             "fileSizeBytes": downloaded_bytes(model_path(root / "models", "tiny.en"))}
    events.append(event)
    print(json.dumps(event), flush=True)


try:
    result = ensure_model("tiny.en", root / "models", progress=progress)
    print(f"COMPLETE {result}", flush=True)
finally:
    (root / "progress.json").write_text(json.dumps(events, indent=2), encoding="utf-8")
