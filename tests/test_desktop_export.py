from pathlib import Path
from unittest.mock import Mock
import pytest

import webview

from karaokesesh.desktop_export import DesktopExportBridge


def test_author_links_open_only_https_allowlisted_sites(monkeypatch):
    opened = Mock(return_value=True)
    monkeypatch.setattr("karaokesesh.desktop_export.webbrowser.open", opened)
    bridge = DesktopExportBridge()
    assert bridge.open_external_url("https://buymeacoffee.com/jaydemks")
    assert bridge.open_external_url("https://www.giovannidemiccoli.com")
    for url in ["file:///C:/Windows", "javascript:alert(1)", "https://github.com.evil.test", "https://github.com@evil.test", "http://github.com/jaydemks"]:
        with pytest.raises(ValueError):
            bridge.open_external_url(url)
    assert opened.call_count == 2


@pytest.mark.parametrize("extension", ["json", "srt", "vtt", "ass", "lrc"])
def test_native_text_save_uses_chosen_destination_and_preserves_unicode(tmp_path, extension):
    bridge = DesktopExportBridge()
    bridge._window = Mock()
    target = tmp_path / f"chosen.{extension}"
    bridge._window.create_file_dialog.return_value = (str(target),)
    assert bridge.save_text_file("日本語 · lyrics", f"suggested.{extension}", extension) == str(target)
    assert target.read_text(encoding="utf-8") == "日本語 · lyrics"
    assert bridge._window.create_file_dialog.call_args.args[0] == webview.FileDialog.SAVE


def test_native_project_load_and_dialog_cancellation(tmp_path):
    bridge = DesktopExportBridge()
    bridge._window = Mock()
    target = tmp_path / "project.karaokesesh.json"
    target.write_text('{"title":"日本語"}', encoding="utf-8-sig")
    bridge._window.create_file_dialog.return_value = (str(target),)
    assert bridge.load_project_file() == {"path": str(target), "content": '{"title":"日本語"}'}
    assert bridge._window.create_file_dialog.call_args.args[0] == webview.FileDialog.OPEN
    bridge._window.create_file_dialog.return_value = None
    assert bridge.load_project_file() is None
    assert bridge.save_text_file("do not overwrite", target.name, "json") is None
    assert target.read_text(encoding="utf-8-sig") == '{"title":"日本語"}'


def test_native_save_adds_extension_and_rejects_unsupported_format(tmp_path):
    bridge = DesktopExportBridge()
    bridge._window = Mock()
    bridge._window.create_file_dialog.return_value = (str(tmp_path / "subtitles"),)
    assert bridge.save_text_file("lyrics", "suggested.srt", "srt") == str(tmp_path / "subtitles.srt")
    with pytest.raises(ValueError):
        bridge.save_text_file("unsafe", "bad.exe", "exe")


def test_choose_directory_and_save_completed_mp4(tmp_path, monkeypatch):
    bridge = DesktopExportBridge()
    export_dir = tmp_path / "my exports"
    export_dir.mkdir()
    source = export_dir / "song_123.mp4"
    source.write_bytes(b"mp4 data")
    copy_path = tmp_path / "copy.mp4"
    bridge._window = Mock()
    bridge._window.create_file_dialog.side_effect = [(str(export_dir),), (str(copy_path),)]
    monkeypatch.setattr("karaokesesh.desktop_export.manager.output_path", lambda job_id: source if job_id == "done" else None)

    assert bridge.choose_render_directory() == str(export_dir.resolve())
    assert bridge.get_render_directory() == str(export_dir.resolve())
    assert bridge.save_render_as("done") == str(copy_path.resolve())
    assert copy_path.read_bytes() == b"mp4 data"
    assert bridge._window.create_file_dialog.call_args_list[0].args[0] == webview.FileDialog.FOLDER
    assert bridge._window.create_file_dialog.call_args_list[1].args[0] == webview.FileDialog.SAVE


def test_cancelled_dialog_does_not_change_destination(tmp_path):
    bridge = DesktopExportBridge()
    bridge._window = Mock()
    bridge._window.create_file_dialog.return_value = None
    original = bridge.get_render_directory()
    assert bridge.choose_render_directory() is None
    assert bridge.get_render_directory() == original


def test_open_render_folder_uses_completed_job_location(tmp_path, monkeypatch):
    bridge = DesktopExportBridge()
    source = tmp_path / "render.mp4"
    source.write_bytes(b"video")
    monkeypatch.setattr("karaokesesh.desktop_export.manager.output_path", lambda _: source)
    launched = []
    monkeypatch.setattr("karaokesesh.desktop_export.subprocess.Popen", lambda args, **kwargs: launched.append(args))
    assert bridge.open_render_directory("done") == str(tmp_path)
    assert launched == [["explorer.exe", str(tmp_path)]]


def test_open_default_folder_ignores_selected_export_folder(tmp_path, monkeypatch):
    bridge = DesktopExportBridge()
    bridge._directory = tmp_path / "chosen"
    default = tmp_path / ".karaokesesh" / "renders"
    monkeypatch.setattr("karaokesesh.desktop_export.RENDERS_DIR", default)
    launched = []
    monkeypatch.setattr("karaokesesh.desktop_export.subprocess.Popen", lambda args, **kwargs: launched.append(args))
    assert bridge.open_default_render_directory() == str(default)
    assert default.is_dir()
    assert launched == [["explorer.exe", str(default)]]
