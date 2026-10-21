import ast
import os
import subprocess
import sys
from pathlib import Path

import pytest
from karaokesesh.processes import background_flags


def test_all_application_subprocesses_hide_console():
    root = Path(__file__).resolve().parents[1] / "karaokesesh"
    count = 0
    for source in root.glob("*.py"):
        for node in ast.walk(ast.parse(source.read_text(encoding="utf-8"))):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if isinstance(node.func.value, ast.Name) and node.func.value.id == "subprocess" and node.func.attr in {"run", "Popen"}:
                assert "creationflags" in {kw.arg for kw in node.keywords}, f"{source.name}:{node.lineno}"
                count += 1
    assert count >= 9


@pytest.mark.skipif(os.name != "nt", reason="Windows native console behavior")
def test_hidden_child_has_no_console_window():
    result = subprocess.run([sys.executable, "-c", "import ctypes; print(ctypes.windll.kernel32.GetConsoleWindow())"],
        capture_output=True, text=True, check=True, creationflags=background_flags())
    assert result.stdout.strip() == "0"


def test_native_window_explicit_icon_and_identity():
    source = (Path(__file__).resolve().parents[1] / "app.py").read_text(encoding="utf-8")
    assert 'icon=str(ASSETS_DIR / "KaraokeSesh.ico")' in source
    assert 'SetCurrentProcessExplicitAppUserModelID("KaraokeSesh.Desktop")' in source


def test_packaging_includes_whisper_vad_and_ocr_models():
    source = (Path(__file__).resolve().parents[1] / "scripts/build_portable.py").read_text(encoding="utf-8")
    assert '"faster_whisper"' in source
    assert '"rapidocr_onnxruntime"' in source
