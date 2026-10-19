from __future__ import annotations

import ctypes
import os
import shutil
import site
import subprocess
import sys
from importlib import import_module
from pathlib import Path

from .processes import background_flags

# Number GPUs by PCI bus, the order nvidia-smi uses, so a GPU picked in the
# UI is the same card CUDA opens. Must be set before CUDA initialises.
os.environ.setdefault("CUDA_DEVICE_ORDER", "PCI_BUS_ID")

_DLL_HANDLES: list[object] = []
_CONFIGURED_PATHS: list[str] = []


def _existing(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        try:
            resolved = path.resolve()
        except OSError:
            continue
        key = str(resolved).casefold()
        if resolved.is_dir() and key not in seen:
            seen.add(key)
            result.append(resolved)
    return result


def windows_cuda_directories() -> list[Path]:
    """Discover CUDA/cuDNN DLL folders without machine-specific paths."""
    if os.name != "nt":
        return []

    candidates: list[Path] = []
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path:
        candidates.append(Path(cuda_path) / "bin")

    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    cuda_root = program_files / "NVIDIA GPU Computing Toolkit" / "CUDA"
    if cuda_root.is_dir():
        candidates.extend(path / "bin" for path in sorted(cuda_root.glob("v*"), reverse=True))

    cudnn_root = program_files / "NVIDIA" / "CUDNN"
    if cudnn_root.is_dir():
        for version in sorted(cudnn_root.glob("v*"), reverse=True):
            bin_dir = version / "bin"
            candidates.append(bin_dir)
            if bin_dir.is_dir():
                candidates.extend(sorted((path for path in bin_dir.iterdir() if path.is_dir()), reverse=True))

    # Release builds vendor the redistributable CUDA runtime wheels so NVIDIA
    # acceleration works on a clean Store installation with only a compatible
    # display driver. Importing the namespace is more reliable than assuming a
    # conventional site-packages layout inside a PyInstaller bundle.
    for package in ("cublas", "cudnn"):
        try:
            module = import_module(f"nvidia.{package}")
            candidates.append(Path(module.__file__).resolve().parent / "bin")
        except (ImportError, AttributeError, OSError, TypeError):
            pass

    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        for package in ("cublas", "cudnn"):
            candidates.append(Path(bundle_root) / "nvidia" / package / "bin")

    site_roots = [Path(sys.prefix) / "Lib" / "site-packages"]
    try:
        site_roots.extend(Path(path) for path in site.getsitepackages())
    except AttributeError:
        pass
    for root in site_roots:
        candidates.extend((root / "nvidia" / package / "bin" for package in ("cublas", "cudnn")))

    return _existing(candidates)


def configure_cuda_paths() -> list[str]:
    """Expose discovered DLL folders to this Python process on Windows."""
    global _CONFIGURED_PATHS
    if os.name != "nt" or _CONFIGURED_PATHS:
        return list(_CONFIGURED_PATHS)

    directories = windows_cuda_directories()
    for directory in directories:
        try:
            _DLL_HANDLES.append(os.add_dll_directory(str(directory)))
        except (AttributeError, OSError):
            pass

    if directories:
        current = os.environ.get("PATH", "")
        os.environ["PATH"] = os.pathsep.join([*(str(path) for path in directories), current])
    _CONFIGURED_PATHS = [str(path) for path in directories]
    return list(_CONFIGURED_PATHS)


def cuda_runtime_available() -> bool:
    """Check the runtime libraries CTranslate2 needs before selecting CUDA."""
    configure_cuda_paths()
    libraries = (
        ("cublas64_12.dll", "cudnn_ops64_9.dll")
        if os.name == "nt"
        else ("libcublas.so.12", "libcudnn_ops.so.9")
    )
    try:
        for library in libraries:
            ctypes.CDLL(library)
    except OSError:
        return False
    return True


def cuda_diagnostics() -> dict[str, object]:
    """Return actionable GPU diagnostics for the UI and support reports."""
    paths = configure_cuda_paths()
    device_count = 0
    error = ""
    try:
        import ctranslate2

        device_count = int(ctranslate2.get_cuda_device_count())
    except Exception as exc:
        error = str(exc)
    runtime = cuda_runtime_available()
    if device_count < 1:
        reason = "No compatible NVIDIA GPU or driver was detected"
    elif not runtime:
        reason = "NVIDIA GPU detected, but the CUDA/cuDNN runtime is unavailable"
    else:
        reason = "NVIDIA CUDA acceleration is ready"
    return {
        "available": bool(device_count and runtime),
        "deviceCount": device_count,
        "runtimeAvailable": runtime,
        "paths": paths,
        "reason": reason,
        "error": error,
    }


def list_gpus() -> list[dict[str, object]]:
    """NVIDIA GPUs with name and memory in use, indexed as CUDA sees them.

    Empty when nvidia-smi is missing, or when CUDA_VISIBLE_DEVICES already
    restricts this process (its indices would no longer match).
    """
    if os.environ.get("CUDA_VISIBLE_DEVICES") is not None:
        return []
    smi = shutil.which("nvidia-smi")
    if not smi:
        return []
    try:
        output = subprocess.run(
            [smi, "--query-gpu=index,name,memory.used,memory.total,utilization.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5, creationflags=background_flags(),
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    gpus = []
    for line in output.splitlines():
        parts = [part.strip() for part in line.split(",")]
        if len(parts) < 5 or not parts[0].isdigit():
            continue
        def number(value: str) -> float | None:
            try:
                return float(value)
            except ValueError:
                return None
        gpus.append({
            "index": int(parts[0]),
            "name": parts[1],
            "memoryUsedMb": number(parts[2]),
            "memoryTotalMb": number(parts[3]),
            "utilization": number(parts[4]),
        })
    return gpus
