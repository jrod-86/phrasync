import base64

import pytest
from fastapi.testclient import TestClient

from app import app
from phrasync import library

JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(library, "LIBRARY_DIR", tmp_path / "library")
    monkeypatch.setattr(library, "TRASH_DIR", tmp_path / "library" / ".trash")
    return TestClient(app)


def project(title, end=12.5):
    return {"title": title, "mode": "lyric", "canvas": {"aspect": "16:9", "width": 1920, "height": 1080},
            "cues": [{"id": "a", "text": "Hello", "start": 1, "end": end}], "timing": {"offset": 0.5}}


def test_save_list_and_load(client):
    assert client.get("/api/library").json()["projects"] == []
    saved = client.put("/api/library/p-one-111", json={"project": project("Carpe Diem"), "thumbnail": JPEG}).json()
    assert saved["title"] == "Carpe Diem" and saved["duration"] == 13.0 and saved["cueCount"] == 1
    assert saved["thumbnail"].startswith("/api/library/p-one-111/thumbnail")
    assert client.get(saved["thumbnail"]).content.startswith(b"\xff\xd8\xff")
    client.put("/api/library/p-two-222", json={"project": project("Second")})
    listed = client.get("/api/library").json()["projects"]
    assert {item["title"] for item in listed} == {"Carpe Diem", "Second"}
    loaded = client.get("/api/library/p-one-111").json()
    assert loaded["id"] == "p-one-111" and loaded["cues"][0]["text"] == "Hello"


def test_rejects_bad_ids_and_bad_thumbnails(client):
    assert client.put("/api/library/..%2Fescape", json={"project": project("x")}).status_code in (400, 404)
    assert client.get("/api/library/UPPER").status_code == 400
    assert client.get("/api/library/p-missing-1").status_code == 404
    saved = client.put("/api/library/p-png-123", json={"project": project("x"), "thumbnail": "data:image/png;base64,AAAA"}).json()
    assert saved["thumbnail"] is None


def test_duplicate_delete_and_restore(client):
    client.put("/api/library/p-one-111", json={"project": project("Song"), "thumbnail": JPEG})
    copy = client.post("/api/library/p-one-111/duplicate").json()
    assert copy["title"] == "Song (copy)" and copy["id"] != "p-one-111" and copy["thumbnail"]
    assert client.delete("/api/library/p-one-111").json() == {"deleted": True}
    assert [item["title"] for item in client.get("/api/library").json()["projects"]] == ["Song (copy)"]
    assert client.post("/api/library/p-one-111/restore").json()["title"] == "Song"
    assert len(client.get("/api/library").json()["projects"]) == 2
    assert client.post("/api/library/p-none-123/restore").status_code == 404
