from __future__ import annotations

import json
import time
from pathlib import Path

import karaokesesh.jobs as jobs_module
from karaokesesh.jobs import JobManager
from karaokesesh.kinetic import has_genuine_word_timing
from karaokesesh.lyric_sync import lyric_lines, sync_lyrics
from karaokesesh.subtitles import parse_lrc, parse_lyrics_file, parse_srt


def _heard(*words: tuple[str, float]) -> list[dict]:
    return [{"text": " ".join(w for w, _ in words), "words": [
        {"text": text, "start": start, "end": start + 0.3} for text, start in words
    ]}]


def test_section_labels_and_blank_lines_are_not_sung():
    text = "[Chorus]\nSo long\n\nVerse 2:\n(oh yeah)\nNever stop\n"
    assert lyric_lines(text) == ["So long", "(oh yeah)", "Never stop"]


def test_the_users_words_win_and_take_the_heard_timing():
    heard = _heard(("so", 10.0), ("long", 10.4), ("lonely", 10.8), ("night", 11.3), ("never", 20.0), ("stop", 20.5))
    result = sync_lyrics("So long, lonely light\nNever stop", heard, 30.0)
    first, second = result["cues"]
    assert first["text"] == "So long, lonely light"
    assert [w["text"] for w in first["words"]] == ["So", "long,", "lonely", "light"]
    # "light" was misheard as "night" but still takes that word's time.
    assert [w["start"] for w in first["words"]] == [10.0, 10.4, 10.8, 11.3]
    assert second["start"] == 20.0
    assert all(has_genuine_word_timing(cue) for cue in result["cues"])
    assert result["report"]["heard"] == 6


def test_split_and_joined_words_still_match():
    heard = _heard(("all", 5.0), ("right", 5.3), ("im", 6.0), ("gonna", 6.4))
    result = sync_lyrics("Alright I'm gonna", heard, 10.0)
    words = result["cues"][0]["words"]
    assert words[0]["start"] == 5.0 and words[0]["end"] == 5.6
    assert result["report"]["estimated"] == 0


def test_a_line_whisper_missed_sits_between_its_neighbours():
    heard = _heard(("first", 10.0), ("line", 10.4), ("last", 30.0), ("line", 30.4))
    result = sync_lyrics("First line\nNobody heard this\nLast line", heard, 40.0)
    middle = result["cues"][1]
    assert 10.7 <= middle["start"] and middle["end"] <= 30.0
    assert result["report"]["unheardLines"] == [1]
    assert result["report"]["estimated"] == 3
    starts = [w["start"] for cue in result["cues"] for w in cue["words"]]
    assert starts == sorted(starts)


def test_hallucinated_words_during_the_intro_are_ignored():
    heard = _heard(("thank", 1.0), ("you", 1.3), ("for", 1.6), ("watching", 1.9), ("come", 12.0), ("on", 12.4))
    result = sync_lyrics("Come on", heard, 20.0)
    assert result["cues"][0]["start"] == 12.0


def test_no_heard_words_still_gives_a_usable_timeline():
    result = sync_lyrics("One two\nThree four", [], 20.0)
    assert len(result["cues"]) == 2
    assert all(has_genuine_word_timing(cue) for cue in result["cues"])


def test_elysy_enhanced_lrc_becomes_word_timing_not_text():
    text = (
        "[ti:Song]\n"
        "[00:36.67]<00:36.672>Come <00:37.010>crawling<00:37.400>, <00:37.900>faster\n"
        "[00:40.10]<00:40.100>Obey <00:40.800>your <00:41.000>master\n"
    )
    first, second = parse_lrc(text)
    assert first["text"] == "Come crawling, faster"
    assert [(w["text"], w["start"]) for w in first["words"]] == [("Come", 36.672), ("crawling,", 37.01), ("faster", 37.9)]
    assert first["words"][0]["end"] == 37.01
    assert has_genuine_word_timing(first) and has_genuine_word_timing(second)


def test_plain_lrc_still_imports_lines_and_honours_offset():
    cues = parse_lrc("[offset:+500]\n[00:10.00]Hello there\n[00:12.00]Again")
    assert [cue["start"] for cue in cues] == [9.5, 11.5]
    assert cues[0]["words"] == []


def _srt(words: list[tuple[str, float, float]]) -> str:
    def stamp(value: float) -> str:
        return f"00:00:{value:06.3f}".replace(".", ",")
    return "\n".join(f"{i}\n{stamp(a)} --> {stamp(b)}\n{w}\n" for i, (w, a, b) in enumerate(words, 1))


def test_word_per_caption_srt_is_regrouped_into_lines(tmp_path):
    words = [("Come", 1.0, 1.3), ("crawling", 1.3, 1.8), ("faster", 1.8, 2.4), ("now.", 2.4, 2.9),
             ("Obey", 4.0, 4.4), ("your", 4.4, 4.6), ("master", 4.6, 5.2), ("now", 5.2, 5.6)]
    path = tmp_path / "song-enhanced-SRT.srt"
    path.write_text(_srt(words), encoding="utf-8")
    cues = parse_lyrics_file(path)
    assert [cue["text"] for cue in cues] == ["Come crawling faster now.", "Obey your master now"]
    assert cues[1]["words"][2] == {"text": "master", "start": 4.6, "end": 5.2}


def test_line_srt_is_left_alone():
    cues = parse_srt(_srt([("Come crawling faster", 1.0, 3.0), ("Obey your master", 4.0, 6.0)]))
    assert len(cues) == 2 and cues[0]["words"] == []


def test_elysy_json_export_imports_with_word_timing(tmp_path):
    data = [{"line": "Hi there, you", "words": [
        {"word": "Hi", "start": 1.0, "end": 1.2}, {"word": "there", "start": 1.2, "end": 1.5},
        {"word": ",", "start": 1.5, "end": 1.5}, {"word": "you", "start": 1.6, "end": 2.0}]}]
    path = tmp_path / "song-JSON.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    (cue,) = parse_lyrics_file(path)
    assert cue["text"] == "Hi there, you" and cue["start"] == 1.0
    assert has_genuine_word_timing(cue)


def test_transcription_job_swaps_in_the_users_lyrics(monkeypatch):
    manager = JobManager()
    monkeypatch.setattr(manager, "_save", lambda job: None)

    def fake_transcribe(path, model, language, vad_filter, *, progress, cancel_check, language_spans=None):
        return {"cues": _heard(("hello", 2.0), ("wurld", 2.5)), "duration": 10.0}

    monkeypatch.setattr(jobs_module, "transcribe_audio", fake_transcribe)
    job = manager.create_transcription(Path("song.wav"), "base", "en", False, False, None, "Hello world")
    deadline = time.monotonic() + 2
    while manager.get(job.id).state not in {"complete", "failed"} and time.monotonic() < deadline:
        time.sleep(0.01)
    result = manager.get(job.id).result
    assert result["cues"][0]["text"] == "Hello world"
    assert result["cues"][0]["words"][1]["start"] == 2.5
    assert result["lyricSync"]["heard"] == 2
    assert result["heardCues"][0]["words"][1]["text"] == "wurld"
    manager.executor.shutdown(wait=True)
