from karaokesesh.align import MIN_WORD_DURATION, align_cues
from copy import deepcopy


def test_alignment_never_emits_words_ending_before_their_start():
    cues = [
        {
            "id": "one",
            "start": 0.0,
            "end": 1.0,
            "text": "one",
            "words": [{"text": "one", "start": 0.9, "end": 1.0}],
        },
        {
            "id": "two",
            "start": 0.4,
            "end": 0.7,
            "text": "two three",
            "words": [
                {"text": "two", "start": 0.4, "end": 0.41},
                {"text": "three", "start": 0.42, "end": 0.43},
            ],
        },
    ]
    result = align_cues(cues, {"onsets": [], "duration": 2.0}, auto_offset=False)["cues"]
    assert result[1]["start"] >= result[0]["end"]
    for cue in result:
        previous = cue["start"]
        for word in cue["words"]:
            assert word["start"] >= previous
            assert word["end"] - word["start"] >= MIN_WORD_DURATION - 1e-4
            previous = word["end"]
        assert cue["end"] >= previous


def _entrance_cue():
    return {"id": "opening", "start": 0.0, "end": 2.0, "text": "Hello world",
            "words": [{"text": "Hello", "start": 0.0, "end": 1.4},
                      {"text": "world", "start": 1.5, "end": 2.0}]}


def test_silent_first_second_is_trimmed_without_moving_end_or_later_words():
    cue = _entrance_cue()
    original = deepcopy(cue)
    analysis = {"peaks": [0] * 60 + [120] * 60, "peaksPerSecond": 60}
    result = align_cues([cue], analysis, auto_offset=False, snap_words=False)
    aligned = result["cues"][0]
    assert 0.94 <= aligned["start"] <= 1.0
    assert aligned["words"][0]["start"] == aligned["start"]
    assert aligned["words"][0]["end"] == 1.4
    assert aligned["words"][1] == original["words"][1]
    assert aligned["end"] == original["end"]
    assert cue == original
    assert result["report"]["trimmedSilentEntrances"] == 1


def test_soft_sustained_opening_and_music_are_not_mistaken_for_silence():
    cue = _entrance_cue()
    for peaks in ([16] * 60 + [120] * 60, [120] * 120, [0] * 120):
        result = align_cues([cue], {"peaks": peaks, "peaksPerSecond": 60},
                            auto_offset=False, snap_words=False)
        assert result["cues"][0]["start"] == 0
        assert result["report"]["trimmedSilentEntrances"] == 0


def test_short_leading_gap_and_isolated_click_do_not_shift_entrance():
    for peaks in ([0] * 6 + [120] * 114, [0] * 60 + [120] + [0] * 59):
        result = align_cues([_entrance_cue()], {"peaks": peaks, "peaksPerSecond": 60},
                            auto_offset=False, snap_words=False)
        assert result["cues"][0]["start"] == 0


def test_silence_guard_can_be_disabled_and_requires_waveform_evidence():
    cue = _entrance_cue()
    result = align_cues([cue], {"peaks": [0] * 60 + [120] * 60, "peaksPerSecond": 60},
                        auto_offset=False, snap_words=False, trim_silence=False)
    assert result["cues"][0]["start"] == 0
    result = align_cues([cue], {"onsets": [1.0]}, auto_offset=False, snap_words=False)
    assert result["cues"][0]["start"] == 0
