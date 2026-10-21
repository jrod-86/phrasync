from karaokesesh.subtitles import (
    cues_to_srt,
    parse_lrc,
    parse_plain,
    parse_srt,
)


def test_srt_round_trip():
    source = """1
00:00:00,000 --> 00:00:01,500
Stand your ground

2
00:00:01,500 --> 00:00:03,200
Make every word hit harder
"""
    cues = parse_srt(source)
    assert len(cues) == 2
    assert cues[0]["text"] == "Stand your ground"
    assert cues[1]["end"] == 3.2
    again = parse_srt(cues_to_srt(cues))
    assert [(cue["start"], cue["end"], cue["text"]) for cue in again] == [
        (cue["start"], cue["end"], cue["text"]) for cue in cues
    ]


def test_lrc_and_plain_timing():
    cues = parse_lrc("[00:00.00]First line\n[00:02.50]Second line")
    assert cues[0]["start"] == 0
    assert 2.4 < cues[0]["end"] < 2.5
    assert cues[1]["start"] == 2.5

    plain = parse_plain("one\ntwo\nthree", duration=9)
    assert [cue["start"] for cue in plain] == [0.0, 3.0, 6.0]
