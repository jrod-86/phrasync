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


def gpu_encoder(project: dict) -> int | None:
    """NVIDIA GPU index for hardware encoding (NVENC), or None for the CPU."""
    value = str(project.get("export", {}).get("encoder", "cpu") or "cpu")
    if not value.startswith("gpu:"):
        return None
    try:
        return max(0, int(value[4:]))
    except ValueError:
        return None


def encoder_args(project: dict) -> list[str]:
    """Encoder, speed preset and rate control for the chosen codec and device."""
    settings = project.get("export", {})
    hevc = video_codec(project) == "hevc"
    gpu = gpu_encoder(project)
    if gpu is None:
        return [*codec_args(project), "-preset", str(settings.get("preset", "medium")),
                *rate_control_args(project)]
    args = ["-c:v", "hevc_nvenc" if hevc else "h264_nvenc", "-gpu", str(gpu), "-preset", "p5"]
    if hevc:
        args += ["-tag:v", "hvc1"]
    rate = bitrate_bps(project)
    if rate is None:
        # Constant quality, like CRF on the CPU encoders.
        return args + ["-rc", "vbr", "-cq", str(settings.get("crf", 18)), "-b:v", "0"]
    return args + ["-rc", "cbr", "-b:v", str(rate), "-maxrate", str(rate), "-bufsize", str(rate * 2)]


def encoder_label(project: dict) -> str:
    gpu = gpu_encoder(project)
    return "CPU" if gpu is None else f"NVIDIA GPU {gpu}"


_NVENC_CHECKS: dict[tuple[int, bool], str | None] = {}


def nvenc_problem(project: dict) -> str | None:
    """Why NVIDIA encoding can't run for this project, or None when it can."""
    gpu = gpu_encoder(project)
    if gpu is None:
        return None
    key = (gpu, video_codec(project) == "hevc")
    if key not in _NVENC_CHECKS:
        import subprocess

        from .media import ffmpeg_exe
        from .processes import background_flags

        probe = {"export": {**project.get("export", {}), "bitrateMbps": None}}
        command = [ffmpeg_exe(), "-v", "error", "-f", "lavfi", "-i", "color=c=black:s=256x256:r=30:d=0.2",
                   *encoder_args(probe), "-f", "null", "-"]
        try:
            done = subprocess.run(command, capture_output=True, text=True, timeout=60,
                                  creationflags=background_flags())
            message = " ".join(done.stderr.strip().splitlines()[:2]) or "NVENC failed"
            _NVENC_CHECKS[key] = None if done.returncode == 0 else message
        except Exception as exc:  # missing driver, timeout
            _NVENC_CHECKS[key] = str(exc)
    return _NVENC_CHECKS[key]
