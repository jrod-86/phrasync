"""Project library behind the start page: every project autosaves here by id.

Each project is <id>.json (the editor's project object) with an optional
<id>.jpg thumbnail beside it. Deleting moves both into .trash so a mistaken
delete can be restored.
"""

from __future__ import annotations

import base64
import json
import os
import re
import secrets
import time
from pathlib import Path
from typing import Any

from .config import PROJECTS_DIR

LIBRARY_DIR = PROJECTS_DIR / "library"
TRASH_DIR = LIBRARY_DIR / ".trash"
_ID = re.compile(r"^[a-z0-9][a-z0-9-]{5,47}$")
MAX_THUMBNAIL_BYTES = 600_000


def valid_id(project_id: str) -> bool:
    return bool(_ID.match(project_id or ""))


def new_id() -> str:
    return f"p-{int(time.time() * 1000):x}-{secrets.token_hex(3)}"


def _paths(project_id: str, root: Path | None = None) -> tuple[Path, Path]:
    if not valid_id(project_id):
        raise ValueError("Invalid project id")
    root = root or LIBRARY_DIR
    return root / f"{project_id}.json", root / f"{project_id}.jpg"


def _duration(project: dict[str, Any]) -> float:
    ends = []
    for cue in project.get("cues") or []:
        try:
            ends.append(float(cue.get("end") or 0) + float((project.get("timing") or {}).get("offset", 0) or 0))
        except (TypeError, ValueError, AttributeError):
            continue
    audio = project.get("audio") or {}
    try:
        ends.append(float(audio.get("duration") or 0))
    except (TypeError, ValueError, AttributeError):
        pass
    try:
        ends.append(float(project.get("duration") or 0))
    except (TypeError, ValueError):
        pass
    return round(max(ends or [0.0]), 3)


def summary(path: Path) -> dict[str, Any] | None:
    try:
        project = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(project, dict):
        return None
    project_id = path.stem
    canvas = project.get("canvas") or {}
    thumb = path.with_suffix(".jpg")
    stat = path.stat()
    return {
        "id": project_id,
        "title": str(project.get("title") or "Untitled project")[:80],
        "mode": project.get("mode") or "lyric",
        "aspect": canvas.get("aspect") or "16:9",
        "width": canvas.get("width"),
        "height": canvas.get("height"),
        "duration": _duration(project),
        "cueCount": len(project.get("cues") or []),
        "updatedAt": stat.st_mtime,
        "size": stat.st_size,
        "thumbnail": f"/api/library/{project_id}/thumbnail?v={int(thumb.stat().st_mtime)}" if thumb.is_file() else None,
    }


def list_projects() -> list[dict[str, Any]]:
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    items = [summary(path) for path in LIBRARY_DIR.glob("*.json") if valid_id(path.stem)]
    return sorted((item for item in items if item), key=lambda item: item["updatedAt"], reverse=True)


def load_project(project_id: str) -> dict[str, Any]:
    path, _ = _paths(project_id)
    if not path.is_file():
        raise FileNotFoundError(project_id)
    return json.loads(path.read_text(encoding="utf-8"))


def _decode_thumbnail(data_url: str) -> bytes | None:
    prefix = "data:image/jpeg;base64,"
    if not isinstance(data_url, str) or not data_url.startswith(prefix):
        return None
    try:
        raw = base64.b64decode(data_url[len(prefix):], validate=True)
    except ValueError:
        return None
    return raw if raw[:3] == b"\xff\xd8\xff" and len(raw) <= MAX_THUMBNAIL_BYTES else None


def _write_atomic(path: Path, data: bytes) -> None:
    partial = path.with_name(f".{path.name}.{secrets.token_hex(3)}.part")
    partial.write_bytes(data)
    os.replace(partial, path)


def save_project(project_id: str, project: dict[str, Any], thumbnail: str | None = None) -> dict[str, Any]:
    if not isinstance(project, dict):
        raise ValueError("Project must be an object")
    path, thumb = _paths(project_id)
    LIBRARY_DIR.mkdir(parents=True, exist_ok=True)
    project = {**project, "id": project_id}
    _write_atomic(path, json.dumps(project, ensure_ascii=False).encode("utf-8"))
    image = _decode_thumbnail(thumbnail) if thumbnail else None
    if image:
        _write_atomic(thumb, image)
    return summary(path) or {"id": project_id}


def thumbnail_path(project_id: str) -> Path | None:
    _, thumb = _paths(project_id)
    return thumb if thumb.is_file() else None


def duplicate_project(project_id: str) -> dict[str, Any]:
    project = load_project(project_id)
    copy_id = new_id()
    project["title"] = f"{project.get('title') or 'Untitled project'} (copy)"[:80]
    _, thumb = _paths(project_id)
    result = save_project(copy_id, project)
    if thumb.is_file():
        _, copy_thumb = _paths(copy_id)
        _write_atomic(copy_thumb, thumb.read_bytes())
        result = summary(_paths(copy_id)[0]) or result
    return result


def delete_project(project_id: str) -> bool:
    TRASH_DIR.mkdir(parents=True, exist_ok=True)
    moved = False
    for source, target in zip(_paths(project_id), _paths(project_id, TRASH_DIR)):
        if source.is_file():
            os.replace(source, target)
            moved = True
    return moved


def restore_project(project_id: str) -> dict[str, Any] | None:
    for source, target in zip(_paths(project_id, TRASH_DIR), _paths(project_id)):
        if source.is_file():
            os.replace(source, target)
    path, _ = _paths(project_id)
    return summary(path) if path.is_file() else None
