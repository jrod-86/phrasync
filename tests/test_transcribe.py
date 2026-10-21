from types import SimpleNamespace

import numpy as np

import karaokesesh.transcribe as transcribe_module
from karaokesesh.language_map import (
    language_spans,
    parse_language_request,
    span_clip_timestamps,
    spans_from_phrases,
)
from karaokesesh.transcription_guard import (
    TEMPERATURE_FALLBACK,
    gauntlet_report,
    segment_diagnostic,
    whisper_options,
)


def _window(start: float, probabilities: dict[str, float], silent: bool = False) -> dict:
    return {"start": start, "end": start + 10.0, "probabilities": probabilities, "silent": silent}


def _windows(pattern: list[dict[str, float]]) -> list[dict]:
    return [_window(index * 10.0, probabilities) for index, probabilities in enumerate(pattern)]


def _segment(text: str, start: float, end: float, words: list[tuple[str, float, float]]):
    return SimpleNamespace(
        start=start,
        end=end,
        text=text,
        words=[SimpleNamespace(word=f" {token}", start=begin, end=finish) for token, begin, finish in words],
        temperature=0.0,
        compression_ratio=1.1,
        avg_logprob=-0.3,
        no_speech_prob=0.02,
    )


def test_language_request_modes():
    assert parse_language_request("auto") == {"mode": "map", "codes": [], "forced": False}
    assert parse_language_request("multilingual")["forced"] is True
    assert parse_language_request("it") == {"mode": "fixed", "codes": ["it"], "forced": False}
    assert parse_language_request("it, en, ja") == {"mode": "map", "codes": ["it", "en", "ja"], "forced": True}
    assert parse_language_request("single")["mode"] == "single"


def test_short_foreign_blip_does_not_split_the_track():
    strong_it = {"it": 0.9, "en": 0.02}
    blip_en = {"en": 0.5, "it": 0.05}
    spans = language_spans(_windows([strong_it] * 3 + [blip_en] * 2 + [strong_it] * 3), 80.0)
    assert [span["language"] for span in spans] == ["it"]


def test_sustained_switch_becomes_its_own_span():
    spans = language_spans(
        _windows([{"it": 0.9, "en": 0.02}] * 4 + [{"en": 0.92, "it": 0.02}] * 4), 80.0
    )
    assert [span["language"] for span in spans] == ["it", "en"]
    assert spans[0]["start"] == 0.0
    assert spans[0]["end"] == spans[1]["start"] == 40.0
    assert spans[1]["end"] == 80.0


def test_instrumental_windows_carry_a_language_instead_of_a_gap():
    quiet = {"en": 0.09, "it": 0.08}
    spans = language_spans(
        _windows([{"it": 0.9, "en": 0.02}] * 3 + [quiet] * 2 + [{"en": 0.93, "it": 0.02}] * 3), 80.0
    )
    assert [span["language"] for span in spans] == ["it", "en"]
    # Every second of the track belongs to exactly one span.
    assert spans[0]["start"] == 0.0 and spans[-1]["end"] == 80.0
    assert all(spans[index]["end"] == spans[index + 1]["start"] for index in range(len(spans) - 1))
    assert 30.0 <= spans[1]["start"] <= 60.0


def test_span_clips_are_local_and_follow_speech_ranges():
    span = {"language": "en", "start": 30.0, "end": 60.0, "probability": 0.9}
    assert span_clip_timestamps(span, None) == [0.0, 30.0]
    assert span_clip_timestamps(span, [(10.0, 35.0), (40.0, 52.0), (70.0, 80.0)]) == [0.0, 5.0, 10.0, 22.0]


def test_phrase_decisions_become_a_timeline_cut_in_the_pauses():
    phrases = [
        {"start": 10.0, "end": 14.0},
        {"start": 15.0, "end": 19.0},
        {"start": 25.0, "end": 29.0},
    ]
    decisions = [
        {"language": "it", "probability": 0.9},
        {"language": "it", "probability": 0.8},
        {"language": "fr", "probability": 0.95},
    ]
    spans = spans_from_phrases(phrases, decisions, 40.0)
    assert [span["language"] for span in spans] == ["it", "fr"]
    # The whole track is covered and the change lands mid-pause, not mid-line.
    assert spans[0]["start"] == 0.0
    assert spans[0]["end"] == spans[1]["start"] == 22.0
    assert spans[1]["end"] == 40.0


def test_a_line_in_another_language_is_re_read_automatically(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            if "clip_timestamps" not in kwargs:  # the first, whole-track pass
                return (
                    iter(
                        [
                            _segment("Prima riga", 1.0, 3.0, [("Prima", 1.0, 2.0), ("riga", 2.0, 3.0)]),
                            _segment("Prima riga", 31.0, 33.0, [("Prima", 31.0, 32.0), ("riga", 32.0, 33.0)]),
                        ]
                    ),
                    SimpleNamespace(language="it", language_probability=0.9),
                )
            return (
                iter([_segment("Second line", 0.5, 2.0, [("Second", 0.5, 1.2), ("line", 1.2, 2.0)])]),
                SimpleNamespace(language=kwargs["language"], language_probability=0.9),
            )

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 60.0)
    monkeypatch.setattr(transcribe_module, "load_audio", lambda path: np.zeros(60 * 16000, dtype=np.float32))
    monkeypatch.setattr(
        transcribe_module,
        "build_language_map",
        lambda *args, **kwargs: [{"language": "it", "start": 0.0, "end": 60.0, "probability": 0.9}],
    )
    # The window pass heard one language; listening line by line disagrees.
    monkeypatch.setattr(
        transcribe_module,
        "detect_phrase_languages",
        lambda *args, **kwargs: [
            {"language": "it", "probability": 0.88},
            {"language": "en", "probability": 0.95},
        ],
    )

    result = transcribe_module.transcribe_audio(tmp_path / "mixed.wav", language="auto")

    # One whole-track pass, then one re-read per span of the corrected map.
    assert [call.get("language") for call in calls] == ["it", "it", "en"]
    assert "clip_timestamps" not in calls[0]
    assert all("clip_timestamps" in call for call in calls[1:])
    assert [span["language"] for span in result["languageSpans"]] == ["it", "en"]
    assert result["languages"] == ["it", "en"]
    assert [cue["language"] for cue in result["cues"]] == ["it", "en"]


def test_agreeing_phrases_skip_the_second_pass(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return (
                iter([_segment("Solo italiano", 0.5, 2.0, [("Solo", 0.5, 1.2), ("italiano", 1.2, 2.0)])]),
                SimpleNamespace(language="it", language_probability=0.97),
            )

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 30.0)
    monkeypatch.setattr(transcribe_module, "load_audio", lambda path: np.zeros(30 * 16000, dtype=np.float32))
    monkeypatch.setattr(
        transcribe_module,
        "build_language_map",
        lambda *args, **kwargs: [{"language": "it", "start": 0.0, "end": 30.0, "probability": 0.95}],
    )
    monkeypatch.setattr(
        transcribe_module, "detect_phrase_languages", lambda *args, **kwargs: [{"language": "it", "probability": 0.9}]
    )

    transcribe_module.transcribe_audio(tmp_path / "song.wav", language="auto")

    assert len(calls) == 1


def test_multi_language_track_decodes_every_span_in_its_own_language(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append({"source": source, **kwargs})
            language = kwargs["language"]
            return (
                iter([_segment("Prima riga qui", 1.0, 3.0, [("riga", 1.4, 2.0), ("qui", 2.0, 3.0)])]),
                SimpleNamespace(language=language, language_probability=0.9),
            )

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 60.0)
    monkeypatch.setattr(transcribe_module, "load_audio", lambda path: np.zeros(60 * 16000, dtype=np.float32))
    monkeypatch.setattr(
        transcribe_module,
        "build_language_map",
        lambda *args, **kwargs: [
            {"language": "it", "start": 0.0, "end": 30.0, "probability": 0.94},
            {"language": "en", "start": 30.0, "end": 60.0, "probability": 0.8},
        ],
    )
    monkeypatch.setattr(
        transcribe_module,
        "detect_phrase_languages",
        lambda model, audio, phrases, *args, **kwargs: [
            {"language": phrase.get("language"), "probability": 0.9} for phrase in phrases
        ],
    )

    result = transcribe_module.transcribe_audio(tmp_path / "mixed.wav", language="auto")

    assert [call["language"] for call in calls] == ["it", "en"]
    assert [call["clip_timestamps"] for call in calls] == [[0.0, 30.0], [0.0, 30.0]]
    assert all(call["vad_filter"] is False for call in calls)
    assert all(call["condition_on_previous_text"] is True for call in calls)
    assert all(call["temperature"] == TEMPERATURE_FALLBACK for call in calls)
    assert len(calls[0]["source"]) == 30 * 16000

    assert result["languages"] == ["it", "en"]
    assert result["languageMode"] == "multi-language (it, en)"
    assert [span["language"] for span in result["languageSpans"]] == ["it", "en"]
    # The second span is decoded from its own slice, so its timings are shifted
    # back onto the track before the cues are built.
    assert [round(segment["start"], 2) for segment in result["rawSegments"]] == [1.0, 31.0]
    assert [cue["language"] for cue in result["cues"]] == ["it", "en"]
    # "Prima" has no word timestamp of its own and is recovered from the text.
    assert result["cues"][0]["text"] == "Prima riga qui"
    assert result["transcriptionGauntlet"]["repairedBoundaryWords"] == 2


def test_supplied_language_map_overrides_detection(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return (
                iter([_segment("Ma stanotte", 0.5, 2.0, [("Ma", 0.5, 1.0), ("stanotte", 1.0, 2.0)])]),
                SimpleNamespace(language=kwargs["language"], language_probability=1.0),
            )

    def refuse(*args, **kwargs):
        raise AssertionError("an edited map must not be re-detected")

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 60.0)
    monkeypatch.setattr(transcribe_module, "load_audio", lambda path: np.zeros(60 * 16000, dtype=np.float32))
    monkeypatch.setattr(transcribe_module, "build_language_map", refuse)

    result = transcribe_module.transcribe_audio(
        tmp_path / "mixed.wav",
        language="auto",
        language_spans=[
            {"language": "EN", "start": 30.0, "end": 60.0},
            {"language": "it", "start": 4.0, "end": 30.0},
        ],
    )

    # Out of order, upper case and starting late: the map is repaired first.
    assert [call["language"] for call in calls] == ["it", "en"]
    assert result["languageSpans"][0] == {"language": "it", "start": 0.0, "end": 30.0, "probability": 0.0}
    assert result["languageMode"] == "your language map (it, en)"


def test_unknown_language_code_is_refused(monkeypatch, tmp_path):
    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "known_language_codes", lambda: {"it", "en"})
    try:
        transcribe_module.transcribe_audio(tmp_path / "song.wav", language="klingon")
    except ValueError as error:
        assert "klingon" in str(error)
    else:  # pragma: no cover - the call must not succeed
        raise AssertionError("an unknown language code must be refused")


def test_single_language_track_stays_on_one_conditioned_pass(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return (
                iter([_segment("Solo italiano", 0.5, 2.0, [("Solo", 0.5, 1.2), ("italiano", 1.2, 2.0)])]),
                SimpleNamespace(language="it", language_probability=0.97),
            )

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 30.0)
    monkeypatch.setattr(transcribe_module, "load_audio", lambda path: np.zeros(30 * 16000, dtype=np.float32))
    monkeypatch.setattr(
        transcribe_module,
        "build_language_map",
        lambda *args, **kwargs: [{"language": "it", "start": 0.0, "end": 30.0, "probability": 0.95}],
    )
    monkeypatch.setattr(
        transcribe_module,
        "detect_phrase_languages",
        lambda model, audio, phrases, *args, **kwargs: [
            {"language": phrase.get("language"), "probability": 0.9} for phrase in phrases
        ],
    )

    result = transcribe_module.transcribe_audio(tmp_path / "song.wav", language="auto")

    assert len(calls) == 1
    assert calls[0]["language"] == "it"
    assert "clip_timestamps" not in calls[0]
    assert result["languageMode"] == "automatic single language (it)"
    assert result["language"] == "it"


def test_fixed_language_skips_detection_entirely(monkeypatch, tmp_path):
    calls: list[dict] = []

    class FakeModel:
        def transcribe(self, source, **kwargs):
            calls.append(kwargs)
            return (
                iter([_segment("Bonjour toi", 0.0, 1.5, [("Bonjour", 0.0, 0.8), ("toi", 0.8, 1.5)])]),
                SimpleNamespace(language="fr", language_probability=1.0),
            )

    def refuse(*args, **kwargs):
        raise AssertionError("a locked language must not run language detection")

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 4.0)
    monkeypatch.setattr(transcribe_module, "build_language_map", refuse)
    monkeypatch.setattr(transcribe_module, "load_audio", refuse)

    result = transcribe_module.transcribe_audio(tmp_path / "song.wav", language="fr")

    assert calls[0]["language"] == "fr"
    assert result["languageMode"] == "fixed language (fr)"


def test_fixed_language_preserves_context_and_speech_vad_boundaries():
    options = whisper_options("fr", True)
    assert options["task"] == "transcribe"
    assert options["language"] == "fr"
    assert options["condition_on_previous_text"] is True
    assert options["vad_parameters"]["speech_pad_ms"] == 650


def test_auto_leaves_the_language_token_to_the_caller():
    options = whisper_options("auto", False)
    assert "language" not in options
    assert options["condition_on_previous_text"] is True
    assert options["temperature"] == TEMPERATURE_FALLBACK


def test_japanese_lines_keep_their_writing(monkeypatch, tmp_path):
    class FakeModel:
        def transcribe(self, source, **kwargs):
            return (
                iter(
                    [
                        _segment(
                            "夜に溶けてゆく",
                            0.5,
                            3.0,
                            [("夜", 0.5, 1.0), ("に", 1.0, 1.4), ("溶", 1.4, 2.0), ("けてゆく", 2.0, 3.0)],
                        )
                    ]
                ),
                SimpleNamespace(language="ja", language_probability=0.95),
            )

    monkeypatch.setattr(transcribe_module, "capability_status", lambda: {"available": True})
    monkeypatch.setattr(transcribe_module, "_device_config", lambda: ("cpu", "int8"))
    monkeypatch.setattr(transcribe_module, "_load_model", lambda *args: FakeModel())
    monkeypatch.setattr(transcribe_module, "probe_duration", lambda path: 4.0)

    result = transcribe_module.transcribe_audio(tmp_path / "song.wav", language="ja")

    # Word timings survive for karaoke, but the line is not sprayed with spaces.
    assert result["cues"][0]["text"] == "夜に溶けてゆく"
    assert len(result["cues"][0]["words"]) == 4


def test_gauntlet_flags_repetition_that_survives_fallback():
    segment = SimpleNamespace(
        start=0.0,
        end=30.0,
        text=" ".join(["Uh"] * 20),
        temperature=1.0,
        compression_ratio=12.0,
        avg_logprob=-0.1,
        no_speech_prob=0.01,
    )
    diagnostic = segment_diagnostic(segment)
    report = gauntlet_report([diagnostic], repaired_words=0, language_mode="multi-language (it, en)")
    assert diagnostic["unstable"] is True
    assert diagnostic["repetitionDominance"] == 1.0
    assert report["unstableSegments"] == [1]
    assert report["warnings"]
