"""Remaster an imported song to the studio master format.

Every song added from the Audio tab is converted to WAV, stereo, 48 kHz,
signed 32-bit PCM, so lyric timing, the vocal remover and exports all
work from one lossless, video-standard sample rate.
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path

from .media import run_ffmpeg
from .storage import Asset, delete_asset, store_path

SAMPLE_RATE = 48000
CHANNELS = 2
CODEC = "pcm_s32le"
MASTER_LABEL = "WAV · stereo · 48 kHz · 32-bit"

# soxr is the cleaner resampler; builds without it fall back to a long swr filter.
_RESAMPLERS = (
    f"aresample={SAMPLE_RATE}:resampler=soxr:precision=28",
    f"aresample={SAMPLE_RATE}:filter_size=64:phase_shift=10:cutoff=0.97",
)


def remaster_args(source: Path, destination: Path, resampler: str) -> list[str]:
    return [
        "-hide_banner", "-nostdin", "-y", "-i", str(source),
        "-map", "0:a:0", "-vn", "-sn", "-dn",
        "-af", resampler, "-ac", str(CHANNELS), "-ar", str(SAMPLE_RATE),
        "-c:a", CODEC, "-rf64", "auto", "-map_metadata", "0",
        str(destination),
    ]


def remaster_file(source: Path, destination: Path) -> None:
    error = ""
    for resampler in _RESAMPLERS:
        process = run_ffmpeg(remaster_args(source, destination, resampler), check=False)
        if process.returncode == 0 and destination.is_file() and destination.stat().st_size > 44:
            return
        error = process.stderr.decode("utf-8", errors="replace").strip().splitlines()[-1:] or [""]
        error = error[0]
    raise ValueError(f"Could not convert this song to WAV: {error or 'FFmpeg failed'}")


def remaster_asset(asset: Asset) -> Asset:
    """Replace an uploaded song with its 48 kHz / 32-bit stereo WAV master."""
    source = Path(asset.path)
    with tempfile.TemporaryDirectory(prefix="phrasync-remaster-") as folder:
        output = Path(folder) / "master.wav"
        try:
            remaster_file(source, output)
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError(f"Could not convert this song to WAV: {exc}") from exc
        master = store_path("audio", output, f"{Path(asset.name).stem}.wav")
    delete_asset(asset.id)
    return master
