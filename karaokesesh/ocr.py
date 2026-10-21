from __future__ import annotations

import csv
import io
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path
from typing import Any
from .processes import background_flags


class OCRUnavailable(RuntimeError):
    pass


@lru_cache(maxsize=1)
def _rapid_engine():
    try:
        from rapidocr_onnxruntime import RapidOCR

        return RapidOCR()
    except Exception:
        return None


def rapidocr_available() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401

        return True
    except Exception:
        return False


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _sort_lines(lines: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def key(item: dict[str, Any]):
        box = item.get("box") or []
        if box and len(box) >= 4:
            xs = [float(point[0]) for point in box]
            ys = [float(point[1]) for point in box]
            return (sum(ys) / len(ys), sum(xs) / len(xs))
        return (float(item.get("top", 0)), float(item.get("left", 0)))

    return sorted(lines, key=key)


def _rapid_ocr(path: Path) -> dict[str, Any] | None:
    engine = _rapid_engine()
    if engine is None:
        return None
    result, elapsed = engine(str(path))
    lines: list[dict[str, Any]] = []
    for row in result or []:
        if not row or len(row) < 3:
            continue
        box, text, score = row[0], str(row[1]).strip(), float(row[2])
        if text:
            lines.append({"text": text, "confidence": score, "box": box})
    lines = _sort_lines(lines)
    return {
        "engine": "RapidOCR",
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "elapsed": elapsed,
    }


def _tesseract_ocr(path: Path, language: str = "eng") -> dict[str, Any] | None:
    executable = shutil.which("tesseract")
    if not executable:
        return None
    language = "eng" if not language or language == "auto" else language
    command = [executable, str(path), "stdout", "-l", language, "--psm", "6", "tsv"]
    process = subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=False, creationflags=background_flags())
    if process.returncode != 0:
        message = process.stderr.decode("utf-8", errors="replace").strip()
        raise RuntimeError(f"Tesseract failed: {message}")
    text = process.stdout.decode("utf-8", errors="replace")
    reader = csv.DictReader(io.StringIO(text), delimiter="\t")
    grouped: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
    for row in reader:
        token = (row.get("text") or "").strip()
        try:
            confidence = float(row.get("conf", "-1"))
        except ValueError:
            confidence = -1
        if not token or confidence < 0:
            continue
        key = (
            row.get("page_num", "1"),
            row.get("block_num", "0"),
            row.get("par_num", "0"),
            row.get("line_num", "0"),
        )
        grouped.setdefault(key, []).append(
            {
                "text": token,
                "confidence": confidence / 100.0,
                "left": int(row.get("left", "0") or 0),
                "top": int(row.get("top", "0") or 0),
                "width": int(row.get("width", "0") or 0),
                "height": int(row.get("height", "0") or 0),
            }
        )
    lines: list[dict[str, Any]] = []
    for tokens in grouped.values():
        tokens.sort(key=lambda token: token["left"])
        left = min(token["left"] for token in tokens)
        top = min(token["top"] for token in tokens)
        right = max(token["left"] + token["width"] for token in tokens)
        bottom = max(token["top"] + token["height"] for token in tokens)
        lines.append(
            {
                "text": " ".join(token["text"] for token in tokens),
                "confidence": sum(token["confidence"] for token in tokens) / len(tokens),
                "box": [[left, top], [right, top], [right, bottom], [left, bottom]],
            }
        )
    lines = _sort_lines(lines)
    return {
        "engine": "Tesseract",
        "text": "\n".join(line["text"] for line in lines),
        "lines": lines,
        "elapsed": None,
    }


def ocr_image(path: Path, language: str = "auto") -> dict[str, Any]:
    rapid = _rapid_ocr(path)
    if rapid is not None:
        return rapid
    tesseract = _tesseract_ocr(path, language=language)
    if tesseract is not None:
        return tesseract
    raise OCRUnavailable(
        "No OCR engine is available. Install requirements-ai.txt (RapidOCR) or Tesseract OCR."
    )


def capability_status() -> dict[str, bool]:
    return {
        "rapidocr": rapidocr_available(),
        "tesseract": tesseract_available(),
        "available": rapidocr_available() or tesseract_available(),
    }
