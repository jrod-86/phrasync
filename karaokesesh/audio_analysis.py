"""Local audio analysis: waveform envelope, onset detection and beat grid.

Everything here runs offline on the CPU with PyAV + NumPy so the timeline can
show a real waveform and the aligner can snap lyrics to musical events.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
from typing import Any

import numpy as np

from .config import WORKSPACE

ANALYSIS_DIR = WORKSPACE / "analysis"
ANALYSIS_DIR.mkdir(exist_ok=True)

SAMPLE_RATE = 22050
N_FFT = 1024
HOP = 256
PEAKS_PER_SECOND = 60
ANALYSIS_VERSION = 4


class AnalysisUnavailable(RuntimeError):
    pass


def _decode_mono(path: Path) -> np.ndarray:
    """Decode any supported audio file to mono float32 at SAMPLE_RATE."""
    return np.concatenate(list(_decode_blocks(path)))


def _decode_blocks(path: Path, sample_rate: int = SAMPLE_RATE):
    """Yield at most one minute of PCM; never retain an entire long video."""
    try:
        import av
    except Exception as exc:  # pragma: no cover - dependency is bundled
        raise AnalysisUnavailable("PyAV is required for audio analysis") from exc

    chunks: list[np.ndarray] = []
    count = 0
    block_size = sample_rate * 60
    found = False
    with av.open(str(path)) as container:
        stream = next((s for s in container.streams if s.type == "audio"), None)
        if stream is None:
            raise AnalysisUnavailable("File contains no audio stream")
        stream.thread_type = "AUTO"
        resampler = av.audio.resampler.AudioResampler(
            format="fltp", layout="mono", rate=sample_rate
        )
        for frame in container.decode(stream):
            for resampled in resampler.resample(frame):
                samples = resampled.to_ndarray().reshape(-1).astype(np.float32)
                while samples.size:
                    take = min(block_size - count, samples.size)
                    chunks.append(samples[:take])
                    count += take
                    samples = samples[take:]
                    if count == block_size:
                        found = True
                        yield np.concatenate(chunks)
                        chunks, count = [], 0
        for resampled in resampler.resample(None):
            chunks.append(resampled.to_ndarray().reshape(-1).astype(np.float32))

    if chunks:
        yield np.concatenate(chunks)
    elif not found:
        raise AnalysisUnavailable("Could not decode any audio samples")


def _stft_magnitude(samples: np.ndarray) -> np.ndarray:
    """Magnitude spectrogram, shape (frames, bins)."""
    if samples.size < N_FFT:
        samples = np.pad(samples, (0, N_FFT - samples.size))
    frame_count = 1 + (samples.size - N_FFT) // HOP
    window = np.hanning(N_FFT).astype(np.float32)
    result = np.empty((frame_count, N_FFT // 2 + 1), dtype=np.float32)
    windows = np.lib.stride_tricks.sliding_window_view(samples, N_FFT)[::HOP]
    for start in range(0, frame_count, 2048):
        frames = windows[start:start + 2048] * window
        result[start:start + len(frames)] = np.abs(np.fft.rfft(frames, axis=1))
    return result


def _flux(magnitude: np.ndarray, low_bin: int, high_bin: int) -> np.ndarray:
    """Half-wave rectified spectral flux over a frequency band."""
    band = magnitude[:, low_bin:high_bin]
    log_band = np.log1p(band * 8.0)
    diff = np.diff(log_band, axis=0, prepend=log_band[:1])
    flux = np.maximum(diff, 0.0).sum(axis=1)
    if flux.max() > 0:
        flux = flux / flux.max()
    return flux.astype(np.float32)


def _smooth(values: np.ndarray, width: int) -> np.ndarray:
    if width < 2:
        return values
    kernel = np.ones(width, dtype=np.float32) / width
    return np.convolve(values, kernel, mode="same").astype(np.float32)


def _pick_peaks(
    envelope: np.ndarray,
    frame_times: np.ndarray,
    delta: float = 0.055,
    min_gap_frames: int = 5,
    window: int = 24,
) -> list[dict[str, float]]:
    """Adaptive-threshold peak picking over an onset envelope."""
    if envelope.size == 0:
        return []
    threshold = _smooth(envelope, window) + delta
    peaks: list[dict[str, float]] = []
    last_index = -min_gap_frames * 2
    for index in range(1, envelope.size - 1):
        value = envelope[index]
        if value < threshold[index]:
            continue
        if value < envelope[index - 1] or value < envelope[index + 1]:
            continue
        if index - last_index < min_gap_frames:
            # Keep the stronger of two peaks that fall too close together.
            if peaks and value > peaks[-1]["strength"]:
                peaks[-1] = {"time": float(frame_times[index]), "strength": float(value)}
                last_index = index
            continue
        peaks.append({"time": float(frame_times[index]), "strength": float(value)})
        last_index = index
    return peaks


def _estimate_tempo(envelope: np.ndarray, frame_rate: float) -> tuple[float, float]:
    """Return (bpm, confidence) from the autocorrelation of the onset envelope."""
    if envelope.size < 64:
        return 0.0, 0.0
    centered = envelope - envelope.mean()
    fft_size = 1 << (2 * centered.size - 1).bit_length()
    spectrum = np.fft.rfft(centered, n=fft_size)
    correlation = np.fft.irfft(spectrum * spectrum.conj(), n=fft_size)[:centered.size]
    if correlation[0] <= 0:
        return 0.0, 0.0
    correlation = correlation / correlation[0]
    min_lag = max(1, int(frame_rate * 60.0 / 200.0))
    max_lag = min(correlation.size - 1, int(frame_rate * 60.0 / 55.0))
    if max_lag <= min_lag:
        return 0.0, 0.0
    window = correlation[min_lag : max_lag + 1]
    best = int(np.argmax(window)) + min_lag
    bpm = 60.0 * frame_rate / best
    confidence = float(np.clip(window.max(), 0.0, 1.0))
    while bpm < 70:
        bpm *= 2
    while bpm > 180:
        bpm /= 2
    return float(bpm), confidence


def _beat_phase(onsets: list[dict[str, float]], bpm: float) -> float:
    """Find the beat-grid offset that best explains the detected onsets."""
    if bpm <= 0 or not onsets:
        return 0.0
    period = 60.0 / bpm
    times = np.array([o["time"] for o in onsets], dtype=np.float32)
    weights = np.array([o["strength"] for o in onsets], dtype=np.float32)
    candidates = np.linspace(0.0, period, 64, endpoint=False)
    best_offset = 0.0
    best_score = -1.0
    for offset in candidates:
        residual = np.abs(((times - offset + period / 2) % period) - period / 2)
        score = float((weights * np.exp(-((residual / (period * 0.14)) ** 2))).sum())
        if score > best_score:
            best_score = score
            best_offset = float(offset)
    return best_offset


def _waveform_peaks(samples: np.ndarray, duration: float) -> list[int]:
    """Downsample to an 0-255 amplitude envelope for the timeline canvas."""
    bucket_count = max(1, int(duration * PEAKS_PER_SECOND))
    bucket_size = max(1, samples.size // bucket_count)
    usable = bucket_count * bucket_size
    if usable > samples.size:
        samples = np.pad(samples, (0, usable - samples.size))
    reshaped = np.abs(samples[:usable]).reshape(bucket_count, bucket_size)
    envelope = reshaped.max(axis=1)
    ceiling = float(np.percentile(envelope, 99.5)) or 1.0
    scaled = np.clip(envelope / ceiling, 0.0, 1.0)
    # Perceptual curve keeps quiet passages visible in the waveform strip.
    scaled = np.power(scaled, 0.62)
    return [int(round(float(v) * 255)) for v in scaled]


def _cache_path(path: Path) -> Path:
    stat = path.stat()
    key = f"{path.name}:{stat.st_size}:{int(stat.st_mtime)}:{ANALYSIS_VERSION}"
    digest = hashlib.sha1(key.encode("utf-8")).hexdigest()[:20]
    return ANALYSIS_DIR / f"{digest}.json"


def analyze_audio(path: Path, use_cache: bool = True) -> dict[str, Any]:
    cache = _cache_path(path)
    if use_cache and cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Keep ordinary songs on the original globally normalized analysis path.
    # Long media is analyzed a minute at a time with compact features retained.
    from .media import probe_duration
    media_duration = probe_duration(path)
    if media_duration is None or media_duration > 600:
        result = _analyze_long(path)
    else:
        result = _analyze_samples(_decode_mono(path))
    try:
        cache.write_text(json.dumps(result), encoding="utf-8")
    except Exception:
        pass
    return result


def _analyze_samples(samples: np.ndarray) -> dict[str, Any]:
    duration = samples.size / SAMPLE_RATE
    magnitude = _stft_magnitude(samples)
    frame_rate = SAMPLE_RATE / HOP
    frame_times = (np.arange(magnitude.shape[0]) * HOP + N_FFT / 2) / SAMPLE_RATE

    bin_hz = SAMPLE_RATE / N_FFT
    full_flux = _smooth(_flux(magnitude, 1, magnitude.shape[1]), 3)
    # 180-5200 Hz carries most sung-consonant energy, so it locates lyric onsets
    # far better than a full-spectrum flux dominated by kick and hi-hat.
    vocal_flux = _smooth(
        _flux(magnitude, max(1, int(180 / bin_hz)), min(magnitude.shape[1], int(5200 / bin_hz))),
        3,
    )
    percussive_flux = _smooth(_flux(magnitude, 1, max(2, int(180 / bin_hz))), 2)

    onsets = _pick_peaks(vocal_flux, frame_times, delta=0.045, min_gap_frames=4)
    percussive = _pick_peaks(percussive_flux, frame_times, delta=0.09, min_gap_frames=8)
    bpm, tempo_confidence = _estimate_tempo(full_flux, frame_rate)
    offset = _beat_phase(percussive or onsets, bpm)

    rms_frames = np.sqrt(np.maximum(np.mean(magnitude**2, axis=1), 0.0))
    if rms_frames.max() > 0:
        rms_frames = rms_frames / rms_frames.max()
    energy_step = max(1, int(frame_rate / 20))

    result: dict[str, Any] = {
        "version": ANALYSIS_VERSION,
        "duration": float(duration),
        "sampleRate": SAMPLE_RATE,
        "peaksPerSecond": PEAKS_PER_SECOND,
        "peaks": _waveform_peaks(samples, duration),
        "onsets": [round(o["time"], 4) for o in onsets],
        "onsetStrengths": [round(o["strength"], 3) for o in onsets],
        "percussiveOnsets": [round(o["time"], 4) for o in percussive],
        "bpm": round(bpm, 2),
        "tempoConfidence": round(tempo_confidence, 3),
        "beatOffset": round(offset, 4),
        "energy": [int(round(float(v) * 255)) for v in rms_frames[::energy_step]],
        "energyRate": float(frame_rate / energy_step),
    }
    return result


def _analyze_long(path: Path) -> dict[str, Any]:
    combined = None
    offset = 0.0
    # Fixed 20 Hz energy output avoids drift at chunk boundaries.
    for samples in _decode_blocks(path):
        part = _analyze_samples(samples)
        if combined is None:
            combined = {**part, "peaks": [], "onsets": [], "onsetStrengths": [],
                        "percussiveOnsets": [], "energy": [], "energyRate": 20.0,
                        "bpm": 0.0, "tempoConfidence": 0.0, "beatOffset": 0.0}
        combined["peaks"].extend(part["peaks"])
        for key in ("onsets", "percussiveOnsets"):
            combined[key].extend(round(t + offset, 4) for t in part[key])
        combined["onsetStrengths"].extend(part["onsetStrengths"])
        energy = np.asarray(part["energy"])
        positions = np.arange(max(1, round(part["duration"] * 20))) / 20
        combined["energy"].extend(np.rint(np.interp(positions, np.arange(len(energy)) / part["energyRate"], energy)).astype(int).tolist())
        offset += part["duration"]
    if combined is None:
        raise AnalysisUnavailable("Could not decode any audio samples")
    combined["duration"] = offset
    return combined


def beat_times(bpm: float, offset: float, duration: float) -> list[float]:
    if bpm <= 0:
        return []
    period = 60.0 / bpm
    count = int(math.floor((duration - offset) / period)) + 1
    return [round(offset + index * period, 4) for index in range(max(0, count))]
