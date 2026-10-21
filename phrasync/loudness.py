"""Loudness normalization for exports (EBU R128 / ITU-R BS.1770, two-pass).

The first pass measures the song over the export range; the second applies
one fixed gain (loudnorm linear mode) so the mix is not pumped, with a
-1 dBTP true-peak ceiling. Settings live in project.export.normalize.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from .media import run_ffmpeg

DEFAULT_TARGET = -14.0
TARGETS = (-14.0, -16.0, -23.0)
TRUE_PEAK = -1.0
LOUDNESS_RANGE = 11.0
OUTPUT_RATE = 48000
_JSON_BLOCK = re.compile(r"\{[^{}]*\"input_i\"[^{}]*\}", re.S)


def normalize_target(project: dict[str, Any]) -> float | None:
    """The LUFS target when normalizing is on (the default), else None."""
    settings = (project.get("export") or {}).get("normalize")
    if not isinstance(settings, dict):
        settings = {}
    if settings.get("enabled", True) is False:
        return None
    try:
        target = float(settings.get("target", DEFAULT_TARGET))
    except (TypeError, ValueError):
        return DEFAULT_TARGET
    return target if target in TARGETS else DEFAULT_TARGET


def _base(target: float) -> str:
    return f"loudnorm=I={target:g}:TP={TRUE_PEAK:g}:LRA={LOUDNESS_RANGE:g}"


def measure(path: Path, start: float, duration: float | None, target: float) -> dict[str, float] | None:
    args = ["-hide_banner", "-nostdin", "-ss", f"{start:.6f}", "-i", str(path)]
    if duration is not None:
        args.extend(["-t", f"{duration:.6f}"])
    args.extend(["-map", "0:a:0", "-af", f"{_base(target)}:print_format=json", "-f", "null", "-"])
    process = run_ffmpeg(args, check=False)
    match = _JSON_BLOCK.search(process.stderr.decode("utf-8", errors="replace"))
    if process.returncode != 0 or not match:
        return None
    try:
        values = {key: float(value) for key, value in json.loads(match.group(0)).items()
                  if key in {"input_i", "input_tp", "input_lra", "input_thresh", "target_offset"}}
    except (TypeError, ValueError):
        return None
    # Silence measures as -inf; there is nothing to normalize.
    if len(values) < 5 or any(abs(value) == float("inf") for value in values.values()):
        return None
    return values


def loudness_filter(project: dict[str, Any], path: Path, start: float, duration: float | None) -> str | None:
    """The -af chain that brings this song to the export's target, or None."""
    target = normalize_target(project)
    if target is None:
        return None
    measured = measure(path, start, duration, target)
    if measured is None:
        return None
    return (
        f"{_base(target)}:measured_I={measured['input_i']:.2f}:measured_TP={measured['input_tp']:.2f}"
        f":measured_LRA={measured['input_lra']:.2f}:measured_thresh={measured['input_thresh']:.2f}"
        f":offset={measured['target_offset']:.2f}:linear=true,aresample={OUTPUT_RATE}"
    )
