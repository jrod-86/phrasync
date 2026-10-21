from __future__ import annotations

from pathlib import Path

from karaokesesh.model_download import downloaded_bytes


ROOT = Path(__file__).resolve().parent.parent


def test_store_build_is_windowed_and_embeds_webview_and_cuda_runtime():
    build = (ROOT / "scripts" / "build_portable.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    ai_requirements = (ROOT / "requirements-ai.txt").read_text(encoding="utf-8")

    assert '"--windowed"' in build
    assert '"webview.platforms.edgechromium"' in build
    assert '"nvidia.cublas"' in build
    assert '"nvidia.cudnn"' in build
    assert "pywebview" in requirements
    assert "nvidia-cublas-cu12" in ai_requirements
    assert "nvidia-cudnn-cu12" in ai_requirements


def test_launcher_uses_native_window_by_default():
    launcher = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "def _open_desktop_window" in launcher
    assert 'webview.start(gui="edgechromium"' in launcher
    assert "WEBVIEW2_ADDITIONAL_BROWSER_ARGUMENTS" in launcher
    assert "--enable-gpu-rasterization" in launcher
    assert "desktop=1" in launcher
    compile(launcher, str(ROOT / "app.py"), "exec")
    assert "log_config=None" in launcher
    assert "server_thread.start()" in launcher
    assert "_open_desktop_window(url)" in launcher
    assert "if args.external_browser" in launcher


def test_model_download_reports_progress_and_eta():
    source = (ROOT / "karaokesesh" / "model_download.py").read_text(encoding="utf-8")
    jobs = (ROOT / "karaokesesh" / "jobs.py").read_text(encoding="utf-8")
    assert '"phase": "model-download"' in source
    assert '"downloadedBytes": current_bytes' in source
    assert '"etaSeconds": round(eta)' in source
    assert "downloaded_bytes" in jobs
    assert "total_bytes" in jobs
    assert "eta_seconds" in jobs


def test_model_download_counts_active_huggingface_payload(tmp_path):
    model = tmp_path / "small"
    model.mkdir()
    (model / "config.json").write_bytes(b"config")
    cache = model / ".cache" / "huggingface" / "download"
    cache.mkdir(parents=True)
    (cache / "model.bin.lock").write_bytes(b"lock metadata is not payload")
    (cache / "model.bin.123.incomplete").write_bytes(b"x" * 4096)

    assert downloaded_bytes(model) == len(b"config") + 4096


def test_store_build_embeds_application_icon():
    build = (ROOT / "scripts" / "build_portable.py").read_text(encoding="utf-8")
    assert '"--icon"' in build
    assert '"KaraokeSesh.ico"' in build
    assert (ROOT / "assets" / "KaraokeSesh.ico").is_file()
