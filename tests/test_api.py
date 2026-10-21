import json
import time
from pathlib import Path

import app as app_module
from fastapi.testclient import TestClient

from app import app


def test_health_and_home():
    client = TestClient(app)
    identity = client.get("/api/instance")
    assert identity.status_code == 200
    assert identity.json()["app"] == "KaraokeSesh"
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["app"] == "KaraokeSesh"
    home = client.get("/")
    assert home.status_code == 200
    assert "PHRA" in home.text


def test_project_save_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setattr(app_module, "PROJECTS_DIR", tmp_path)
    project = {
        "version": 1,
        "title": "My first / project",
        "canvas": {"width": 1280, "height": 720, "fps": 30},
        "timing": {"offset": 0.125},
        "cues": [{"id": "one", "start": 0, "end": 1, "text": "Hello"}],
    }
    client = TestClient(app)
    response = client.post("/api/projects/save", json={"project": project})
    assert response.status_code == 200
    saved = tmp_path / response.json()["filename"]
    assert saved.exists()
    assert json.loads(saved.read_text(encoding="utf-8")) == project
    assert saved.name == "My_first___project.karaokesesh.json"


def test_render_job_status_and_download(tmp_path, monkeypatch):
    import karaokesesh.jobs as jobs_module

    monkeypatch.setattr(jobs_module, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(jobs_module, "RENDERS_DIR", tmp_path)
    selected_dir = tmp_path / "selected exports"
    selected_dir.mkdir()
    monkeypatch.setattr(app_module.desktop_export, "_window", object())
    monkeypatch.setattr(app_module.desktop_export, "_directory", selected_dir)
    monkeypatch.setattr(app_module.desktop_export, "_directory_selected", True)
    client = TestClient(app)
    project = {
        "title": "API smoke",
        "duration": 0.6,
        "canvas": {"width": 320, "height": 320, "fps": 12},
        "background": {"type": "dynamic", "visual": "aurora", "shade": 0.2, "grain": 0},
        "style": {"preset": "minimal", "fontPreset": "modern", "fontSize": 90},
        "cues": [{"id": "one", "start": 0, "end": 0.6, "text": "API EXPORT"}],
        "export": {"crf": 30, "preset": "ultrafast"},
    }
    created = client.post("/api/render", json={"title": project["title"], "project": project})
    assert created.status_code == 202
    job_id = created.json()["id"]
    deadline = time.monotonic() + 15
    try:
        while time.monotonic() < deadline:
            status = client.get(f"/api/render/{job_id}").json()
            if status["state"] in {"complete", "failed", "cancelled"}:
                break
            time.sleep(0.05)
        assert status["state"] == "complete", json.dumps(status, indent=2)
        assert Path(status["result"]["path"]).parent == selected_dir
        assert list(selected_dir.glob("*.mp4")) == [selected_dir / "API_smoke.mp4"]
        download = client.get(f"/api/render/{job_id}/download")
        assert download.status_code == 200
        assert download.content.startswith(b"\x00\x00")
    finally:
        app_module.manager.jobs.pop(job_id, None)
