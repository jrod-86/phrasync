"""Exercise a REAL model transfer through jobs/API, skipping AI inference."""
import json
import os
from pathlib import Path
import sys
import time
from types import SimpleNamespace

root = Path(sys.argv[1]).resolve()
root.mkdir(parents=True, exist_ok=True)
os.environ["HF_HOME"] = str(root / "hf")
os.environ["HF_XET_CACHE"] = str(root / "xet")
os.environ["KARAOKESESH_HOME"] = str(root / "workspace")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient
import app
from karaokesesh import jobs
from karaokesesh.model_download import ensure_model


def transfer_only(path, model, language, vad_filter, progress, **kwargs):
    ensure_model("tiny.en", root / "models", progress=progress)
    return {"cues": [], "qaNote": "Real download; inference intentionally skipped"}


jobs.transcribe_audio = transfer_only
app.get_av_asset = lambda asset_id: SimpleNamespace(path="qa-transfer-only.wav")
client = TestClient(app.app)
started = time.monotonic()
created = client.post("/api/transcriptions", json={"assetId": "qa", "model": "tiny.en", "align": False})
created.raise_for_status()
job_id = created.json()["id"]
events = []
while True:
    value = client.get(f"/api/transcriptions/{job_id}").json()
    value["elapsed"] = round(time.monotonic() - started, 2)
    events.append(value)
    print(json.dumps({key: value.get(key) for key in ("elapsed", "state", "phase", "progress", "downloaded_bytes", "total_bytes", "eta_seconds")}), flush=True)
    if value["state"] in {"complete", "failed", "cancelled"}:
        break
    time.sleep(.3)
(root / (sys.argv[2] if len(sys.argv) > 2 else "api-progress.json")).write_text(json.dumps(events, indent=2), encoding="utf-8")
assert value["state"] == "complete", value.get("error")
