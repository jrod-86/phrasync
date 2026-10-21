from __future__ import annotations

import os
from pathlib import Path

APP_NAME = "KaraokeSesh"
APP_VERSION = "0.4.7"
# Earlier names of the app, newest first: Phrasync, and VerseFrame before it.
LEGACY_PREFIXES = ("PHRASYNC", "VERSEFRAME")
LEGACY_PREFIX = LEGACY_PREFIXES[-1]


def _env(name: str, default: str) -> str:
    """Read KARAOKESESH_<name>, falling back to the pre-rename PHRASYNC_/VERSEFRAME_<name>."""
    for prefix in ("KARAOKESESH", *LEGACY_PREFIXES):
        value = os.environ.get(f"{prefix}_{name}")
        if value:
            return value
    return default


DEFAULT_HOST = _env("HOST", "127.0.0.1")
DEFAULT_PORT = int(_env("PORT", "5500"))
PROJECT_ROOT = Path(__file__).resolve().parent.parent
STATIC_DIR = PROJECT_ROOT / "static"
ASSETS_DIR = PROJECT_ROOT / "assets"


def workspace_root() -> Path:
    """Resolve the workspace, adopting a pre-rename ~/.phrasync or ~/.verseframe folder once.

    That folder holds uploaded songs, saved projects and multi-gigabyte Whisper
    models, so the rename renames the directory rather than orphaning it. If the
    move is not possible the old folder keeps being used in place.
    """
    override = _env("HOME", "")
    if override:
        root = Path(override).expanduser()
    else:
        root = Path.home() / ".karaokesesh"
        legacy = next((path for path in (Path.home() / ".phrasync", Path.home() / ".verseframe") if path.is_dir()), None)
        if not root.exists() and legacy is not None:
            try:
                legacy.rename(root)
            except OSError:
                root = legacy
    root.mkdir(parents=True, exist_ok=True)
    for child in ("uploads", "renders", "jobs", "projects", "tmp"):
        (root / child).mkdir(exist_ok=True)
    return root


WORKSPACE = workspace_root()
UPLOADS_DIR = WORKSPACE / "uploads"
RENDERS_DIR = WORKSPACE / "renders"
JOBS_DIR = WORKSPACE / "jobs"
PROJECTS_DIR = WORKSPACE / "projects"
TMP_DIR = WORKSPACE / "tmp"

MAX_UPLOAD_BYTES = int(_env("MAX_UPLOAD_MB", "16384")) * 1024 * 1024
SUPPORTED_AUDIO = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
SUPPORTED_IMAGE = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SUPPORTED_VIDEO = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
SUPPORTED_FONT = {".ttf", ".otf", ".ttc"}
SUPPORTED_LYRICS = {".srt", ".lrc", ".txt", ".json", ".vtt"}

# Project files saved before the rename still open normally.
PROJECT_SUFFIX = ".karaokesesh.json"
LEGACY_PROJECT_SUFFIX = ".verseframe.json"
LEGACY_PROJECT_SUFFIXES = (".phrasync.json", LEGACY_PROJECT_SUFFIX)
