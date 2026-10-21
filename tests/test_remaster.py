import wave

import pytest
from fastapi.testclient import TestClient

from app import app
from karaokesesh import storage
from karaokesesh.media import run_ffmpeg
from karaokesesh.remaster import remaster_file


def tone(path, rate=44100, channels=1, codec="libmp3lame"):
    run_ffmpeg(["-hide_banner", "-y", "-f", "lavfi", "-i", f"sine=frequency=440:sample_rate={rate}:duration=1",
                "-ac", str(channels), "-c:a", codec, str(path)])


def wav_format(path):
    with wave.open(str(path)) as reader:
        return reader.getnchannels(), reader.getframerate(), reader.getsampwidth(), reader.getnframes()


def test_remaster_makes_stereo_48k_32bit_wav(tmp_path):
    source = tmp_path / "song.mp3"
    tone(source)
    output = tmp_path / "master.wav"
    remaster_file(source, output)
    channels, rate, width, frames = wav_format(output)
    assert (channels, rate, width) == (2, 48000, 4)
    assert frames == pytest.approx(48000, abs=2400)


def test_remaster_rejects_files_without_audio(tmp_path):
    bad = tmp_path / "bad.mp3"
    bad.write_bytes(b"not audio at all")
    with pytest.raises(ValueError, match="Could not convert"):
        remaster_file(bad, tmp_path / "out.wav")


def test_song_upload_is_remastered(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path / "uploads")
    (tmp_path / "uploads").mkdir()
    source = tmp_path / "My Song.flac"
    tone(source, rate=96000, channels=2, codec="flac")
    client = TestClient(app)
    result = client.post("/api/assets/audio/stream?filename=My%20Song.flac&remaster=true", content=source.read_bytes()).json()
    assert result["name"] == "My Song.wav" and result["remastered"]
    assert result["duration"] == pytest.approx(1.0, abs=0.05)
    assert wav_format(tmp_path / "uploads" / result["id"])[:3] == (2, 48000, 4)
    assert sorted(path.suffix for path in (tmp_path / "uploads").iterdir() if path.suffix != ".json") == [".wav"]

    plain = client.post("/api/assets/audio/stream?filename=other.flac", content=source.read_bytes()).json()
    assert plain["name"] == "other.flac" and "remastered" not in plain
