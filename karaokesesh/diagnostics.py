"""Small, local-only support log and hardware report.

The report is never transmitted to a developer. Users can inspect it before
choosing to copy or download it for support.
"""
from __future__ import annotations

import ctypes
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime, timezone
from logging.handlers import RotatingFileHandler
from pathlib import Path

from .config import APP_VERSION, WORKSPACE

LOG_DIR = WORKSPACE / "logs"
LOG_FILE = LOG_DIR / "karaokesesh.log"
_logger = logging.getLogger("karaokesesh.support")


def configure_logging() -> logging.Logger:
    if _logger.handlers:
        return _logger
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(LOG_FILE, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    formatter = logging.Formatter("%(asctime)s UTC | %(levelname)s | %(message)s")
    formatter.converter = __import__("time").gmtime
    handler.setFormatter(formatter)
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    _logger.propagate = False
    return _logger


def log_event(level: str, category: str, message: str) -> None:
    """Log bounded support events, not project/media contents or API bodies."""
    logger = configure_logging()
    safe_category = "".join(c for c in category if c.isalnum() or c in "-_")[:40] or "app"
    safe_message = " ".join(str(message).split())[:1000]
    getattr(logger, "error" if level == "error" else "warning" if level == "warning" else "info")(
        "%s | %s", safe_category, safe_message
    )


def log_exception(category: str, exc: BaseException) -> None:
    logger = configure_logging()
    logger.error("%s | %s: %s", category, type(exc).__name__, str(exc)[:500], exc_info=True)


def _windows_hardware() -> dict[str, str]:
    if os.name != "nt":
        return {}
    script = (
        "$cpu=Get-CimInstance Win32_Processor -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty Name;"
        "$gpu=Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue | "
        "Select-Object -ExpandProperty Name;"
        "[pscustomobject]@{cpu=$cpu;gpu=($gpu -join ', ')} | ConvertTo-Json -Compress"
    )
    try:
        result = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True, text=True, timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        if result.returncode == 0:
            import json
            data = json.loads(result.stdout)
            return {"cpu": str(data.get("cpu") or "Unknown"), "gpu": str(data.get("gpu") or "Unknown")}
    except (OSError, subprocess.TimeoutExpired, ValueError):
        pass
    return {}


def _ram_gib() -> str:
    if os.name != "nt":
        return "Unknown"

    class MemoryStatus(ctypes.Structure):
        _fields_ = [("length", ctypes.c_ulong), ("memory_load", ctypes.c_ulong),
                    ("total_physical", ctypes.c_ulonglong), ("available_physical", ctypes.c_ulonglong),
                    ("total_page", ctypes.c_ulonglong), ("available_page", ctypes.c_ulonglong),
                    ("total_virtual", ctypes.c_ulonglong), ("available_virtual", ctypes.c_ulonglong),
                    ("available_extended", ctypes.c_ulonglong)]

    status = MemoryStatus()
    status.length = ctypes.sizeof(status)
    return f"{status.total_physical / 1024**3:.1f} GiB" if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)) else "Unknown"


def system_summary() -> dict[str, str]:
    hardware = _windows_hardware()
    try:
        free_gib = f"{shutil.disk_usage(WORKSPACE).free / 1024**3:.1f} GiB"
    except OSError:
        free_gib = "Unknown"
    return {
        "KaraokeSesh": APP_VERSION,
        "Windows / OS": platform.platform(),
        "Architecture": platform.machine(),
        "CPU": hardware.get("cpu") or platform.processor() or "Unknown",
        "Logical CPU cores": str(os.cpu_count() or "Unknown"),
        "GPU": hardware.get("gpu") or "Unknown",
        "RAM": _ram_gib(),
        "Free workspace disk": free_gib,
        "Python runtime": platform.python_version(),
    }


def recent_log(max_bytes: int = 180_000) -> str:
    try:
        with LOG_FILE.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            stream.seek(max(0, stream.tell() - max_bytes))
            return stream.read().decode("utf-8", errors="replace")
    except OSError:
        return "No events recorded yet."


def support_report() -> str:
    lines = ["KaraokeSesh support report", f"Generated: {datetime.now(timezone.utc).isoformat()}", "",
             "System", "------"]
    lines.extend(f"{key}: {value}" for key, value in system_summary().items())
    lines.extend(["", "Recent events", "-------------", recent_log()])
    report = "\n".join(lines)
    report = re.sub(r"hf_[A-Za-z0-9_-]{8,}", "<REDACTED_TOKEN>", report)
    report = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._-]+", "Bearer <REDACTED_TOKEN>", report)
    home = str(Path.home())
    if home:
        for candidate in {home, home.replace("\\", "/"), home.replace("/", "\\")}:
            report = re.sub(re.escape(candidate), "<USER_HOME>", report, flags=re.IGNORECASE)
    return report


def install_exception_hooks() -> None:
    def exception_hook(exc_type, exc, traceback):
        log_exception("uncaught-main", exc)
        sys.__excepthook__(exc_type, exc, traceback)

    def thread_hook(args):
        log_exception(f"uncaught-thread-{args.thread.name}", args.exc_value)

    sys.excepthook = exception_hook
    threading.excepthook = thread_hook
