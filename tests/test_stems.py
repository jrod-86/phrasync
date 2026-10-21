"""Vocal remover: chunked MDX-Net separation and the stems job API."""

import time
import wave
from pathlib import Path

import numpy as np
from fastapi.testclient import TestClient

import app as app_module
from karaokesesh import jobs as jobs_module
from karaokesesh import stems
from karaokesesh.storage import store_path


class EchoModel:
    """Stand-in for the ONNX session: predicts the input spectrogram back."""

    def __init__(self):
        self.calls = 0

    def get_inputs(self):
        return [type("Input", (), {"name": "input"})()]

    def run(self, _outputs, feeds):
        self.calls += 1
        spec = feeds["input"]
        assert spec.shape == (1, 4, stems.DIM_F, stems.DIM_T)
        return [spec]


def test_chunked_separation_rebuilds_the_signal():
    rng = np.random.default_rng(3)
    length = stems.GEN * 2 + 12345  # three chunks, the last one partial
    t = np.arange(length) / stems.SAMPLE_RATE
    # Band-limited test signal: the model only sees bins below DIM_F.
    mix = np.stack([np.sin(2 * np.pi * 220 * t), np.sin(2 * np.pi * 330 * t + 1)]).astype(np.float32) * 0.5
    mix += rng.normal(0, 0.001, mix.shape).astype(np.float32)
    model = EchoModel()
    seen = []
    instrumental, vocals = stems.separate_array(mix, model, lambda value, _m: seen.append(value))
    assert model.calls == 3 and seen[-1] == 1.0
    assert instrumental.shape == mix.shape
    # An echo model keeps everything as "instrumental", scaled by UVR's
    # compensation, and the two stems always add back up to the mix.
    assert np.abs(instrumental - mix * stems.COMPENSATE).max() < 2e-3
    assert np.abs(instrumental + vocals - mix).max() < 1e-5


def test_wav_writer_round_trips(tmp_path):
    audio = np.stack([np.linspace(-1, 1, 1000), np.linspace(1, -1, 1000)]).astype(np.float32)
    path = tmp_path / "out.wav"
    stems.write_wav(path, audio)
    with wave.open(str(path)) as reader:
        assert (reader.getnchannels(), reader.getframerate(), reader.getnframes()) == (2, 44100, 1000)


def test_stems_job_stores_both_tracks(tmp_path, monkeypatch):
    monkeypatch.setattr(jobs_module, "JOBS_DIR", tmp_path)
    monkeypatch.setattr(jobs_module, "TMP_DIR", tmp_path)
    song = tmp_path / "My Song.wav"
    stems.write_wav(song, np.zeros((2, 4410), np.float32))
    source = store_path("audio", song)

    def fake_separate(path, out_dir, gpu, progress, cancelled):
        out_dir.mkdir(parents=True, exist_ok=True)
        progress(0.5, "Removing vocals (1 of 2)")
        outputs = {"instrumental": out_dir / "a.wav", "vocals": out_dir / "b.wav"}
        for target in outputs.values():
            stems.write_wav(target, np.zeros((2, 4410), np.float32))
        return outputs

    monkeypatch.setattr(jobs_module, "separate_file", fake_separate)
    client = TestClient(app_module.app)
    created = client.post("/api/stems", json={"assetId": source.id})
    assert created.status_code == 202
    job_id = created.json()["id"]
    for _ in range(100):
        job = client.get(f"/api/stems/{job_id}").json()
        if job["state"] in {"complete", "failed"}:
            break
        time.sleep(0.05)
    assert job["state"] == "complete", job
    assert job["result"]["instrumental"]["name"] == "My Song - Instrumental.wav"
    assert job["result"]["vocals"]["name"] == "My Song - Vocals.wav"
    assert job["result"]["vocals"]["url"].startswith("/media/")
    assert not (tmp_path / f"stems-{job_id}").exists()
    assert client.post("/api/stems", json={"assetId": "missing.wav"}).status_code == 404
