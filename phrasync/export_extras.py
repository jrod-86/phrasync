"""Audio-only and caption files written beside (or instead of) the video export."""

from __future__ import annotations

import math
import subprocess
from pathlib import Path
from typing import Any

from .media import ffmpeg_exe
from .processes import background_flags
from .storage import get_av_asset
from .subtitles import cues_to_ass, cues_to_lrc, cues_to_srt, cues_to_vtt, normalize_cues

AUDIO_FORMATS = {
    "mp3": ("mp3", ["-c:a", "libmp3lame", "-b:a", "320k"]),
    "wav": ("wav", ["-c:a", "pcm_s16le"]),
    "aac": ("m4a", ["-c:a", "aac", "-b:a", "256k", "-movflags", "+faststart"]),
}
CAPTION_FORMATS = {"srt", "vtt", "lrc", "ass"}


def reserve_path(output_dir: Path, base: str, extension: str) -> Path:
    """Create an empty file named base.ext, or base (2).ext and so on, never overwriting."""
    index = 1
    while True:
        path = output_dir / f"{base}{f' ({index})' if index > 1 else ''}.{extension}"
        try:
            with path.open("xb"):
                return path
        except FileExistsError:
            index += 1


def export_window(project: dict[str, Any]) -> tuple[float, float | None]:
    """(start, duration) of the export range; duration None means to the end."""
    export_range = project.get("exportRange")
    if isinstance(export_range, dict):
        try:
            start, end = float(export_range.get("in", 0)), float(export_range.get("out"))
        except (TypeError, ValueError):
            return 0.0, None
        if math.isfinite(start) and math.isfinite(end) and 0 <= start < end:
            return start, end - start
    return 0.0, None


def export_audio(project: dict[str, Any], output_dir: Path, base: str, fmt: str) -> Path:
    """The song track picked in the editor, trimmed to the export range."""
    asset = get_av_asset(project.get("audioAssetId")) if project.get("audioAssetId") else None
    if not asset:
        raise ValueError("Add a song before exporting audio.")
    extension, codec = AUDIO_FORMATS.get(fmt, AUDIO_FORMATS["mp3"])
    path = reserve_path(output_dir, base, extension)
    start, duration = export_window(project)
    command = [ffmpeg_exe(), "-y", "-v", "error", "-ss", f"{start:.6f}", "-i", asset.path, "-vn", "-map", "0:a:0"]
    if duration is not None:
        command.extend(["-t", f"{duration:.6f}"])
    command.extend([*codec, str(path)])
    completed = subprocess.run(command, capture_output=True, text=True, creationflags=background_flags())
    if completed.returncode != 0:
        path.unlink(missing_ok=True)
        raise RuntimeError(f"Audio export failed: {completed.stderr.strip() or 'unknown error'}")
    return path


def _shift_cues(cues: list[dict[str, Any]], shift: float, limit: float | None) -> list[dict[str, Any]]:
    """Move cues by shift seconds and keep only what falls inside [0, limit]."""
    shifted = []
    for cue in normalize_cues(cues):
        start, end = float(cue["start"]) + shift, float(cue["end"]) + shift
        if end <= 0 or (limit is not None and start >= limit):
            continue
        clip = (lambda value: max(0.0, value if limit is None else min(limit, value)))
        words = []
        for word in cue.get("words") or []:
            try:
                ws, we = float(word["start"]) + shift, float(word["end"]) + shift
            except (KeyError, TypeError, ValueError):
                continue
            words.append({**word, "start": clip(ws), "end": clip(we)})
        shifted.append({**cue, "start": clip(start), "end": clip(end), "words": words})
    return shifted


def export_captions(project: dict[str, Any], output_dir: Path, base: str, fmt: str) -> Path:
    """Lyrics as a caption file timed to the exported video (range and lyric offset applied)."""
    fmt = fmt if fmt in CAPTION_FORMATS else "srt"
    start, duration = export_window(project)
    offset = float((project.get("timing") or {}).get("offset", 0) or 0)
    cues = _shift_cues(project.get("cues") or [], offset - start, duration)
    if fmt == "srt":
        text = cues_to_srt(cues)
    elif fmt == "vtt":
        text = cues_to_vtt(cues)
    elif fmt == "lrc":
        text = cues_to_lrc(cues)
    else:
        text = cues_to_ass(cues, project.get("style") or {}, project.get("canvas") or {})
    path = reserve_path(output_dir, base, fmt)
    path.write_text(text, encoding="utf-8")
    return path
