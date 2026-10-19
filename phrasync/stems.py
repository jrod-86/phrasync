"""Vocal remover: split a song into an instrumental and a vocal stem.

Runs a UVR MDX-Net model (UVR-MDX-NET-Inst_HQ_3, the karaoke instrumental
model Ultimate Vocal Remover ships) through onnxruntime, which the OCR pack
already installs, so no PyTorch is needed. The model predicts the
instrumental spectrogram one ~6 s chunk at a time; vocals are the mix minus
the instrumental, so the two stems always add back up to the original song.
"""

from __future__ import annotations

import threading
import urllib.request
import wave
from pathlib import Path
from typing import Callable

import numpy as np

from .config import WORKSPACE
from .media import run_ffmpeg

SAMPLE_RATE = 44100
STEMS_MODEL_DIR = WORKSPACE / "models" / "stems"
MODEL_NAME = "UVR-MDX-NET-Inst_HQ_3.onnx"
MODEL_URL = (
    "https://github.com/TRvlvr/model_repo/releases/download/"
    f"all_public_uvr_models/{MODEL_NAME}"
)
MODEL_BYTES = 66_759_214
# UVR's published parameters for this model (model_data.json).
N_FFT = 6144
HOP = 1024
DIM_F = 3072
DIM_T = 256
COMPENSATE = 1.022

CHUNK = HOP * (DIM_T - 1)
TRIM = N_FFT // 2
GEN = CHUNK - 2 * TRIM

_session_lock = threading.Lock()
_session = None


class StemsUnavailable(RuntimeError):
    pass


class StemsCancelled(RuntimeError):
    pass


Progress = Callable[[float, str], None]


def model_path() -> Path:
    return STEMS_MODEL_DIR / MODEL_NAME


def ensure_model(progress: Progress | None = None, cancelled: Callable[[], bool] | None = None) -> Path:
    """Download the separation model once (about 67 MB)."""
    path = model_path()
    if path.is_file() and path.stat().st_size == MODEL_BYTES:
        return path
    STEMS_MODEL_DIR.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".part")
    try:
        with urllib.request.urlopen(MODEL_URL, timeout=60) as response, partial.open("wb") as out:
            total = int(response.headers.get("Content-Length") or MODEL_BYTES)
            done = 0
            while chunk := response.read(1 << 20):
                if cancelled and cancelled():
                    raise StemsCancelled("Vocal removal cancelled")
                out.write(chunk)
                done += len(chunk)
                if progress:
                    progress(min(1.0, done / total), f"Downloading the vocal remover model ({done >> 20} of {total >> 20} MB)")
    except StemsCancelled:
        partial.unlink(missing_ok=True)
        raise
    except Exception as exc:
        partial.unlink(missing_ok=True)
        raise StemsUnavailable(f"Could not download the vocal remover model: {exc}") from exc
    partial.replace(path)
    return path


def _providers(gpu: int | None) -> list:
    import onnxruntime as ort

    available = ort.get_available_providers()
    providers: list = []
    if "CUDAExecutionProvider" in available:
        providers.append(("CUDAExecutionProvider", {"device_id": int(gpu or 0)}))
    if "DmlExecutionProvider" in available:
        providers.append(("DmlExecutionProvider", {"device_id": int(gpu or 0)}))
    providers.append("CPUExecutionProvider")
    return providers


def _load_session(path: Path, gpu: int | None):
    global _session
    try:
        import onnxruntime as ort
    except ImportError as exc:  # pragma: no cover - depends on the AI pack
        raise StemsUnavailable("The vocal remover needs onnxruntime (pip install -r requirements-ai.txt).") from exc
    with _session_lock:
        key = (str(path), gpu)
        if _session is None or _session[0] != key:
            options = ort.SessionOptions()
            options.log_severity_level = 3
            _session = (key, ort.InferenceSession(str(path), options, providers=_providers(gpu)))
        return _session[1]


def decode_stereo(path: Path) -> np.ndarray:
    """Decode any audio or video file to float32 stereo at 44.1 kHz, shape (2, n)."""
    process = run_ffmpeg(
        ["-v", "error", "-i", str(path), "-vn", "-ac", "2", "-ar", str(SAMPLE_RATE), "-f", "f32le", "pipe:1"],
        check=True,
    )
    samples = np.frombuffer(process.stdout or b"", dtype=np.float32)
    return samples.reshape(-1, 2).T.copy()


def write_wav(path: Path, audio: np.ndarray) -> None:
    """Write (2, n) float audio as 16-bit stereo WAV."""
    pcm = (np.clip(audio, -1.0, 1.0) * 32767.0).round().astype("<i2").T.copy()
    with wave.open(str(path), "wb") as out:
        out.setnchannels(2)
        out.setsampwidth(2)
        out.setframerate(SAMPLE_RATE)
        out.writeframes(pcm.tobytes())


_WINDOW = (0.5 - 0.5 * np.cos(2 * np.pi * np.arange(N_FFT) / N_FFT)).astype(np.float32)


def _stft(chunk: np.ndarray) -> np.ndarray:
    """Centred STFT of a (2, CHUNK) chunk, matching torch.stft(center=True)."""
    padded = np.pad(chunk, ((0, 0), (N_FFT // 2, N_FFT // 2)), mode="reflect")
    frames = np.lib.stride_tricks.sliding_window_view(padded, N_FFT, axis=1)[:, ::HOP]
    spec = np.fft.rfft(frames * _WINDOW, axis=-1)  # (2, T, N_FFT//2+1)
    return spec.transpose(0, 2, 1)[:, :DIM_F]  # (2, DIM_F, T)


def _istft(spec: np.ndarray, length: int) -> np.ndarray:
    full = np.zeros((2, N_FFT // 2 + 1, spec.shape[2]), dtype=np.complex64)
    full[:, :DIM_F] = spec
    frames = np.fft.irfft(full.transpose(0, 2, 1), n=N_FFT, axis=-1) * _WINDOW
    count = frames.shape[1]
    total = N_FFT + HOP * (count - 1)
    out = np.zeros((2, total), dtype=np.float32)
    norm = np.zeros(total, dtype=np.float32)
    for index in range(count):
        start = index * HOP
        out[:, start:start + N_FFT] += frames[:, index]
        norm[start:start + N_FFT] += _WINDOW ** 2
    out /= np.maximum(norm, 1e-8)
    return out[:, N_FFT // 2:N_FFT // 2 + length]


def _to_model(spec: np.ndarray) -> np.ndarray:
    # Channel order matches torch.view_as_real(...).permute(0, 1, 4, 2, 3):
    # left real, left imaginary, right real, right imaginary.
    return np.stack([spec.real, spec.imag], axis=1).reshape(1, 4, DIM_F, -1).astype(np.float32)


def _from_model(output: np.ndarray) -> np.ndarray:
    parts = output.reshape(2, 2, DIM_F, -1)
    return parts[:, 0] + 1j * parts[:, 1]


def separate_array(
    mix: np.ndarray,
    session,
    progress: Progress | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """Return (instrumental, vocals) for a (2, n) mix."""
    length = mix.shape[1]
    pad = GEN - length % GEN
    padded = np.concatenate(
        [np.zeros((2, TRIM), np.float32), mix, np.zeros((2, pad + TRIM), np.float32)], axis=1
    )
    input_name = session.get_inputs()[0].name
    pieces = []
    steps = range(0, length + pad, GEN)
    for number, start in enumerate(steps):
        if cancelled and cancelled():
            raise StemsCancelled("Vocal removal cancelled")
        chunk = padded[:, start:start + CHUNK]
        predicted = session.run(None, {input_name: _to_model(_stft(chunk))})[0]
        wave_out = _istft(_from_model(predicted), CHUNK)
        pieces.append(wave_out[:, TRIM:CHUNK - TRIM])
        if progress:
            progress((number + 1) / len(steps), f"Removing vocals ({number + 1} of {len(steps)})")
    instrumental = np.concatenate(pieces, axis=1)[:, :length] * COMPENSATE
    vocals = mix - instrumental
    return instrumental.astype(np.float32), vocals.astype(np.float32)


def separate_file(
    source: Path,
    output_dir: Path,
    gpu: int | None = None,
    progress: Progress | None = None,
    cancelled: Callable[[], bool] | None = None,
) -> dict[str, Path]:
    """Write <name> - Instrumental.wav and <name> - Vocals.wav into output_dir."""

    def report(share: tuple[float, float]):
        def inner(value: float, message: str) -> None:
            if progress:
                progress(share[0] + (share[1] - share[0]) * value, message)
        return inner

    path = ensure_model(report((0.0, 0.1)), cancelled)
    if progress:
        progress(0.1, "Reading the song")
    mix = decode_stereo(source)
    if mix.shape[1] == 0:
        raise ValueError("The song has no audio to separate.")
    session = _load_session(path, gpu)
    instrumental, vocals = separate_array(mix, session, report((0.12, 0.95)), cancelled)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = source.stem
    outputs = {
        "instrumental": output_dir / f"{stem} - Instrumental.wav",
        "vocals": output_dir / f"{stem} - Vocals.wav",
    }
    write_wav(outputs["instrumental"], instrumental)
    write_wav(outputs["vocals"], vocals)
    if progress:
        progress(1.0, "Vocals removed")
    return outputs
