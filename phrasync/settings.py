from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .config import WORKSPACE

SETTINGS_PATH = WORKSPACE / "settings.json"
_STARTUP_HF_TOKEN = os.environ.get("HF_TOKEN")


def _read(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _write(payload: dict[str, Any], path: Path = SETTINGS_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    try:
        temporary.chmod(0o600)
    except OSError:
        pass
    temporary.replace(path)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def _masked(token: str) -> str:
    if len(token) <= 8:
        return "••••••••"
    prefix = "hf_" if token.startswith("hf_") else ""
    return f"{prefix}••••••••{token[-4:]}"


def saved_hf_token(path: Path = SETTINGS_PATH) -> str | None:
    token = _read(path).get("huggingFaceToken")
    return token if isinstance(token, str) and token else None


def apply_saved_settings(path: Path = SETTINGS_PATH) -> None:
    token = saved_hf_token(path)
    if token and not os.environ.get("HF_TOKEN"):
        os.environ["HF_TOKEN"] = token


def hf_token_status(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    saved = saved_hf_token(path)
    active = os.environ.get("HF_TOKEN")
    if not active:
        return {"configured": False, "masked": None, "source": None, "canRemove": bool(saved)}
    source = "saved" if saved == active else "environment"
    return {
        "configured": True,
        "masked": _masked(active),
        "source": source,
        "canRemove": bool(saved),
    }


def save_hf_token(token: str, path: Path = SETTINGS_PATH) -> dict[str, Any]:
    token = token.strip()
    if not token.startswith("hf_") or len(token) < 12 or len(token) > 512 or any(char.isspace() for char in token):
        raise ValueError("Enter a valid Hugging Face token without spaces")
    payload = _read(path)
    payload["huggingFaceToken"] = token
    _write(payload, path)
    os.environ["HF_TOKEN"] = token
    return hf_token_status(path)


def remove_hf_token(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    payload = _read(path)
    saved = payload.pop("huggingFaceToken", None)
    if payload:
        _write(payload, path)
    else:
        path.unlink(missing_ok=True)
    if saved and os.environ.get("HF_TOKEN") == saved:
        if _STARTUP_HF_TOKEN:
            os.environ["HF_TOKEN"] = _STARTUP_HF_TOKEN
        else:
            os.environ.pop("HF_TOKEN", None)
    return hf_token_status(path)


# App preferences edited in the Settings window. Unknown keys are dropped and
# every value is clamped, so a hand-edited settings.json cannot break the app.
PREFERENCE_DEFAULTS: dict[str, Any] = {
    "exportDirectory": None,
    "exportThreads": 0,
    "stepSeconds": 1.0,
    "imageDuration": 5.0,
    "newAspect": "original",
    "newResolution": 1080,
    "newFps": 30,
    "defaultEncoder": "cpu",
    "exportSound": True,
    "startPage": True,
}
_ASPECTS = {"original", "16:9", "9:16", "1:1", "4:5", "4:3", "3:4", "2:1", "21:9", "2.35:1", "1.85:1"}


def _number(value: Any, default: float, low: float, high: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return default
    return min(high, max(low, number)) if number == number else default


def clean_preferences(raw: dict[str, Any]) -> dict[str, Any]:
    prefs = dict(PREFERENCE_DEFAULTS)
    raw = raw if isinstance(raw, dict) else {}
    directory = raw.get("exportDirectory")
    prefs["exportDirectory"] = directory if isinstance(directory, str) and directory.strip() else None
    prefs["exportThreads"] = int(_number(raw.get("exportThreads"), 0, 0, 64))
    prefs["stepSeconds"] = round(_number(raw.get("stepSeconds"), 1.0, 0.01, 30), 3)
    prefs["imageDuration"] = round(_number(raw.get("imageDuration"), 5.0, 0.5, 600), 2)
    prefs["newAspect"] = raw.get("newAspect") if raw.get("newAspect") in _ASPECTS else "original"
    prefs["newResolution"] = raw.get("newResolution") if raw.get("newResolution") in (720, 1080, 1440, 2160) else 1080
    prefs["newFps"] = raw.get("newFps") if raw.get("newFps") in (24, 25, 30, 50, 60) else 30
    encoder = str(raw.get("defaultEncoder") or "cpu")
    prefs["defaultEncoder"] = encoder if encoder == "cpu" or (encoder.startswith("gpu:") and encoder[4:].isdigit()) else "cpu"
    for key in ("exportSound", "startPage"):
        if isinstance(raw.get(key), bool):
            prefs[key] = raw[key]
    return prefs


def preferences(path: Path = SETTINGS_PATH) -> dict[str, Any]:
    return clean_preferences(_read(path).get("preferences") or {})


def save_preferences(changes: dict[str, Any], path: Path = SETTINGS_PATH) -> dict[str, Any]:
    payload = _read(path)
    merged = {**(payload.get("preferences") or {}), **(changes if isinstance(changes, dict) else {})}
    payload["preferences"] = clean_preferences(merged)
    _write(payload, path)
    return payload["preferences"]
