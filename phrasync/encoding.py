"""Shared rate control for every export engine (Mbps in saved projects)."""
from __future__ import annotations

import math


def bitrate_bps(project: dict) -> int | None:
    value = project.get("export", {}).get("bitrateMbps")
    if value in (None, ""):
        return None
    try:
        rate = float(value)
    except (TypeError, ValueError):
        raise ValueError("Video bitrate must be a positive number in Mbps") from None
    if not math.isfinite(rate) or rate <= 0:
        raise ValueError("Video bitrate must be a positive number in Mbps")
    result = round(rate * 1_000_000)
    if result < 1 or result > 2_147_483_647:
        raise ValueError("Video bitrate exceeds the encoder's supported range")
    return result


def video_codec(project: dict) -> str:
    """"h264" (plays everywhere) or "hevc" (H.265: smaller files at the same quality)."""
    return "hevc" if str(project.get("export", {}).get("codec", "h264")).lower() in {"hevc", "h265"} else "h264"


def container(project: dict) -> str:
    """Output file extension without the dot: mp4 or mov."""
    return "mov" if str(project.get("export", {}).get("format", "mp4")).lower() == "mov" else "mp4"


def video_enabled(project: dict) -> bool:
    return project.get("export", {}).get("video", True) is not False


def codec_args(project: dict) -> list[str]:
    """Encoder and tag. hvc1 lets QuickTime, iPhones and CapCut open HEVC files."""
    if video_codec(project) == "hevc":
        return ["-c:v", "libx265", "-tag:v", "hvc1"]
    return ["-c:v", "libx264"]


def rate_control_args(project: dict) -> list[str]:
    rate = bitrate_bps(project)
    hevc = video_codec(project) == "hevc"
    if rate is None:
        crf = ["-crf", str(project.get("export", {}).get("crf", 18))]
        return crf + (["-x265-params", "log-level=error"] if hevc else [])
    if hevc:
        return ["-b:v", str(rate), "-maxrate", str(rate), "-bufsize", str(rate * 2),
                "-x265-params", "log-level=error"]
    # CBR with filler: simple scenes must not silently fall far below the user's rate.
    return ["-b:v", str(rate), "-minrate", str(rate), "-maxrate", str(rate),
            "-bufsize", str(rate), "-x264-params", "nal-hrd=cbr:filler=1"]
