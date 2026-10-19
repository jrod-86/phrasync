"""CapCut-style export options: codec, container, audio-only and caption files."""

from __future__ import annotations

import re
from pathlib import Path
from types import SimpleNamespace

from phrasync import jobs
from phrasync.encoding import codec_args, container, rate_control_args, video_enabled
from phrasync.export_extras import export_audio, export_captions
from phrasync.media import probe_duration, run_ffmpeg
from phrasync.renderer import render_project
from phrasync.storage import delete_asset, store_path
from tests.test_renderer import make_project, make_tone


def test_codec_and_format_settings():
    assert codec_args({}) == ["-c:v", "libx264"] and container({}) == "mp4"
    hevc = {"export": {"codec": "hevc", "format": "mov", "crf": 20}}
    assert codec_args(hevc) == ["-c:v", "libx265", "-tag:v", "hvc1"]
    assert container(hevc) == "mov"
    assert rate_control_args(hevc)[:2] == ["-crf", "20"]
    assert "-x264-params" not in rate_control_args({"export": {"codec": "hevc", "bitrateMbps": 8}})
    assert video_enabled({}) and not video_enabled({"export": {"video": False}})


def test_hevc_mov_render_is_tagged_for_quicktime(tmp_path):
    project = make_project(duration=1.0, background={"type": "dynamic", "visual": "aurora"})
    project["export"].update({"codec": "hevc", "format": "mov"})
    output = tmp_path / "clip.mov"
    render_project(project, output)
    info = run_ffmpeg(["-hide_banner", "-i", str(output)], check=False).stderr.decode()
    assert re.search(r"Video: hevc .*\(hvc1", info), info
    assert not list(tmp_path.glob("*.partial*"))


def test_audio_and_captions_follow_the_export_range(tmp_path):
    tone = tmp_path / "tone.wav"
    make_tone(tone, duration=3.0)
    asset = store_path("audio", tone, "Song.wav")
    try:
        project = {
            "audioAssetId": asset.id,
            "exportRange": {"in": 1.0, "out": 2.5},
            "timing": {"offset": 0.25},
            "cues": [
                {"id": "a", "start": 0.0, "end": 0.5, "text": "before"},
                {"id": "b", "start": 1.25, "end": 2.0, "text": "inside the range"},
            ],
        }
        mp3 = export_audio(project, tmp_path, "Song", "mp3")
        assert mp3.name == "Song.mp3"
        assert abs((probe_duration(mp3) or 0) - 1.5) < 0.1
        assert export_audio(project, tmp_path, "Song", "aac").suffix == ".m4a"
        srt = export_captions(project, tmp_path, "Song", "srt").read_text()
        assert "before" not in srt
        # 1.25 s + 0.25 s lyric offset - 1.0 s range start = 0.5 s into the clip.
        assert "00:00:00,500 --> 00:00:01,250" in srt
        assert export_captions(project, tmp_path, "Song", "srt").name == "Song (2).srt"
    finally:
        delete_asset(asset.id)


def test_audio_only_export_skips_the_video(tmp_path, monkeypatch):
    tone = tmp_path / "tone.wav"
    make_tone(tone, duration=1.0)
    asset = store_path("audio", tone, "Song.wav")
    manager = jobs.JobManager()
    monkeypatch.setattr(manager, "_save", lambda job: None)
    rendered = []
    monkeypatch.setattr(jobs, "render_project", lambda *a, **k: rendered.append(1))
    try:
        project = {"audioAssetId": asset.id, "cues": [{"id": "a", "start": 0, "end": 1, "text": "hi"}],
                   "export": {"video": False, "audio": {"enabled": True, "format": "wav"},
                              "captions": {"enabled": True, "format": "lrc"}}}
        manager.jobs["one"] = jobs.Job(id="one", kind="render")
        out = tmp_path / "out"
        out.mkdir()
        manager._run_render("one", project, "My song", out)
        job = manager.jobs["one"]
        assert job.state == "complete", job.error
        assert not rendered
        assert [Path(p).name for p in job.result["files"]] == ["My_song.wav", "My_song.lrc"]
        assert job.result["path"].endswith("My_song.wav")

        manager.jobs["two"] = jobs.Job(id="two", kind="render")
        manager._run_render("two", {"export": {"video": False}}, "x", out)
        assert manager.jobs["two"].state == "failed"
    finally:
        delete_asset(asset.id)
        manager.executor.shutdown()
