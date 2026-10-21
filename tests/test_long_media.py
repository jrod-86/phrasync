import asyncio
import json
import wave

import numpy as np
import pytest

from karaokesesh import audio_analysis as analysis
from karaokesesh import storage
from karaokesesh.config import MAX_UPLOAD_BYTES


def test_stream_upload_and_partial_cleanup(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)

    async def chunks():
        for chunk in (b"abc", b"def"):
            yield chunk

    asset = asyncio.run(storage.store_chunks("video", "movie.mp4", chunks(), 6))
    assert (tmp_path / asset.id).read_bytes() == b"abcdef"
    assert json.loads((tmp_path / f"{asset.id}.meta.json").read_text())["size"] == 6
    before = set(tmp_path.iterdir())
    with pytest.raises(ValueError, match="interrupted"):
        asyncio.run(storage.store_chunks("video", "movie.mp4", chunks(), 7))
    assert set(tmp_path.iterdir()) == before

    async def disconnect():
        yield b"abc"
        raise asyncio.CancelledError()

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(storage.store_chunks("video", "movie.mp4", disconnect()))
    assert set(tmp_path.iterdir()) == before


def test_stream_limit_checked_before_body_and_while_streaming(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(storage, "MAX_UPLOAD_BYTES", 5)

    async def unread():
        pytest.fail("Oversize Content-Length must reject before reading body")
        yield b""

    with pytest.raises(ValueError, match="limit"):
        asyncio.run(storage.store_chunks("video", "movie.mp4", unread(), 6))

    async def oversized():
        yield b"1234"
        yield b"56"

    with pytest.raises(ValueError, match="limit"):
        asyncio.run(storage.store_chunks("video", "movie.mp4", oversized()))
    assert list(tmp_path.iterdir()) == []
    assert MAX_UPLOAD_BYTES >= 10 * 1024**3


def test_batched_spectrogram_matches_reference():
    samples = np.random.default_rng(2).normal(size=analysis.HOP * 2500 + analysis.N_FFT).astype(np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(samples, analysis.N_FFT)[::analysis.HOP]
    expected = np.abs(np.fft.rfft(windows * np.hanning(analysis.N_FFT).astype(np.float32), axis=1))
    np.testing.assert_allclose(analysis._stft_magnitude(samples), expected, rtol=1e-6, atol=1e-6)


def test_long_analysis_aggregates_four_hours_without_pcm_allocation(monkeypatch, tmp_path):
    # Reuse a tiny block with a declared minute of features. The production
    # iterator owns PCM bounds; this verifies 4h offsets and feature growth.
    monkeypatch.setattr(analysis, "_decode_blocks", lambda path: (np.zeros(1) for _ in range(240)))
    monkeypatch.setattr(analysis, "_analyze_samples", lambda samples: {
        "duration": 60.0, "peaks": [10] * 3600, "peaksPerSecond": 60,
        "onsets": [1.0, 59.5], "onsetStrengths": [0.4, 0.5],
        "percussiveOnsets": [2.0], "energy": [10] * 1200, "energyRate": 20.0,
    })
    result = analysis._analyze_long(tmp_path / "long.mp4")
    assert result["duration"] == 14400
    assert len(result["peaks"]) == 14400 * 60
    assert len(result["energy"]) == 14400 * 20
    assert result["onsets"][-1] == 14399.5
    assert result["percussiveOnsets"][-1] == 14342


def test_fft_tempo_finds_regular_pulses():
    envelope = np.zeros(12000, dtype=np.float32)
    envelope[::50] = 1
    bpm, confidence = analysis._estimate_tempo(envelope, 100)
    assert bpm == 120
    assert confidence > 0.9


def test_real_decoder_and_envelope_across_minute_boundary(tmp_path):
    from karaokesesh.media import audio_envelope, decode_audio_mono

    rate, duration, fps = 8000, 61.25, 24
    path = tmp_path / "minute.wav"
    times = np.arange(int(rate * duration)) / rate
    signal = (np.sin(times * 2 * np.pi * 220) * (0.1 + 0.3 * (times > 60)) * 32767).astype(np.int16)
    with wave.open(str(path), "wb") as handle:
        handle.setnchannels(1)
        handle.setsampwidth(2)
        handle.setframerate(rate)
        handle.writeframes(signal.tobytes())
    blocks = list(analysis._decode_blocks(path, sample_rate=rate))
    assert [len(block) for block in blocks] == [60 * rate, int(1.25 * rate)]
    samples = decode_audio_mono(path, sample_rate=rate)
    expected = np.array([
        np.sqrt(np.mean(samples[int(i * rate / fps):int((i + 1) * rate / fps)] ** 2) + 1e-12)
        for i in range(round(duration * fps))
    ], dtype=np.float32)
    expected = np.clip(expected / np.percentile(expected, 98), 0, 1.25)
    expected = np.convolve(expected, np.array([.1, .2, .4, .2, .1], dtype=np.float32), mode="same")
    np.testing.assert_allclose(audio_envelope(path, duration, fps, rate), expected, rtol=2e-6, atol=2e-6)


def test_raw_upload_api_preserves_asset_schema(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    import app as app_module

    monkeypatch.setattr(storage, "UPLOADS_DIR", tmp_path)
    monkeypatch.setattr(app_module, "probe_duration", lambda path: 14400.0)
    response = TestClient(app_module.app).post("/api/assets/video/stream?filename=long.mp4", content=b"video-bytes")
    assert response.status_code == 200
    asset = response.json()
    assert asset["kind"] == "video"
    assert asset["size"] == 11
    assert asset["duration"] == 14400
    assert asset["url"] == f"/media/{asset['id']}"
    assert "path" not in asset


@pytest.mark.parametrize("padding", [0, 160])
@pytest.mark.parametrize("feature_size", [80, 128])
def test_bounded_whisper_features_preserve_time_grid_and_global_normalization(padding, feature_size):
    from faster_whisper.feature_extractor import FeatureExtractor
    from karaokesesh.long_audio import BoundedFeatureExtractor

    delegate = FeatureExtractor(feature_size=feature_size)
    # Quiet and loud regions deliberately span many batch boundaries.
    audio = np.random.default_rng(22).normal(size=16000 * 3 + 37).astype(np.float32)
    audio[:32000] *= 1e-4
    bounded = BoundedFeatureExtractor(delegate, threshold_seconds=0, batch_frames=37)
    expected = delegate(audio, padding=padding)
    result = bounded(audio, padding=padding)
    assert result.shape == expected.shape
    np.testing.assert_allclose(result, expected, rtol=2e-6, atol=2e-6)


def test_bounded_whisper_keeps_short_audio_on_original_path():
    from karaokesesh.long_audio import BoundedFeatureExtractor

    class Delegate:
        sampling_rate = 16000

        def __call__(self, audio, **kwargs):
            return "original"

    assert BoundedFeatureExtractor(Delegate())(np.zeros(16000)) == "original"
