"""Sync the user's own lyrics to the words Whisper heard.

Whisper's word timestamps are good; its spelling of sung words is not. When
the user supplies the real lyrics, the lyrics decide every word and every line
break, and Whisper only lends its timing: the two word sequences are aligned
(fuzzy, order-preserving), each lyric word takes the time of the heard word it
matched, and words Whisper missed are placed between their matched neighbours.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache
from typing import Any

from .kinetic import syllable_weight
from .subtitles import normalize_cues

NOMINAL_WORD = 0.35  # seconds a word gets when nothing heard pins it down
MIN_WORD = 0.06
MATCH_SIMILARITY = 0.6
MERGE_SIMILARITY = 0.75
SKIP_LYRIC = -0.45
SKIP_HEARD = -0.3
SUBSTITUTE = -0.25

_SECTION_LABEL = re.compile(
    r"^\s*[\[(]?\s*(intro|outro|verse|chorus|pre[- ]?chorus|post[- ]?chorus|bridge|hook|refrain|"
    r"interlude|instrumental|solo|breakdown)\b[\w\s#.-]{0,12}[\])]?\s*:?\s*$",
    re.IGNORECASE,
)


def lyric_lines(text: str) -> list[str]:
    """One sung line per non-empty line; section labels such as [Chorus] are dropped."""
    lines = []
    for raw in str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        line = " ".join(raw.split())
        if not line or _SECTION_LABEL.match(line):
            continue
        if line.startswith("[") and line.endswith("]"):
            continue
        lines.append(line)
    return lines


def word_key(token: str) -> str:
    """Spelling-insensitive key: lowercase letters and digits only."""
    decomposed = unicodedata.normalize("NFKD", str(token).lower())
    return "".join(ch for ch in decomposed if ch.isalnum())


@lru_cache(maxsize=200_000)
def similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _heard_words(cues: list[dict[str, Any]]) -> list[dict[str, Any]]:
    heard = []
    for cue in cues or []:
        for word in cue.get("words") or []:
            text = str(word.get("text", word.get("word", ""))).strip()
            key = word_key(text)
            try:
                start, end = float(word["start"]), float(word["end"])
            except (KeyError, TypeError, ValueError):
                continue
            if key and end >= start:
                heard.append({"key": key, "start": start, "end": max(end, start + MIN_WORD)})
    heard.sort(key=lambda word: word["start"])
    return heard


def _align(lyric: list[str], heard: list[str]) -> list[tuple[str, list[int], list[int]]]:
    """Needleman-Wunsch over word keys with 1:1, 1:2 and 2:1 steps.

    Returns steps of (kind, lyric indices, heard indices), kind being "match",
    "sub", "skip-lyric" or "skip-heard".
    """
    n, m = len(lyric), len(heard)
    neg = float("-inf")
    score = [[neg] * (m + 1) for _ in range(n + 1)]
    back: list[list[tuple[str, int, int] | None]] = [[None] * (m + 1) for _ in range(n + 1)]
    score[0][0] = 0.0
    for i in range(n + 1):
        row, prev_row = score[i], score[i - 1] if i else None
        for j in range(m + 1):
            if i == 0 and j == 0:
                continue
            best, step = neg, None
            if i and j:
                s = similarity(lyric[i - 1], heard[j - 1])
                value = prev_row[j - 1] + (1.0 + s if s >= MATCH_SIMILARITY else SUBSTITUTE)
                if value > best:
                    best, step = value, ("match" if s >= MATCH_SIMILARITY else "sub", 1, 1)
                if j >= 2:
                    s = similarity(lyric[i - 1], heard[j - 2] + heard[j - 1])
                    if s >= MERGE_SIMILARITY and prev_row[j - 2] + 0.8 + s > best:
                        best, step = prev_row[j - 2] + 0.8 + s, ("match", 1, 2)
                if i >= 2:
                    s = similarity(lyric[i - 2] + lyric[i - 1], heard[j - 1])
                    if s >= MERGE_SIMILARITY and score[i - 2][j - 1] + 0.8 + s > best:
                        best, step = score[i - 2][j - 1] + 0.8 + s, ("match", 2, 1)
            if i and prev_row[j] + SKIP_LYRIC > best:
                best, step = prev_row[j] + SKIP_LYRIC, ("skip-lyric", 1, 0)
            if j and row[j - 1] + SKIP_HEARD > best:
                best, step = row[j - 1] + SKIP_HEARD, ("skip-heard", 0, 1)
            row[j], back[i][j] = best, step

    steps = []
    i, j = n, m
    while i or j:
        kind, di, dj = back[i][j]
        steps.append((kind, list(range(i - di, i)), list(range(j - dj, j))))
        i, j = i - di, j - dj
    steps.reverse()
    return steps


def _weights(tokens: list[str]) -> list[float]:
    return [syllable_weight(token) for token in tokens]


def _spread(times: list[list[float] | None], tokens: list[str], indices: list[int], begin: float, finish: float) -> None:
    """Share [begin, finish] between the words at indices, by syllable weight."""
    if not indices:
        return
    weights = _weights([tokens[index] for index in indices])
    total = sum(weights) or 1.0
    cursor = begin
    span = max(0.0, finish - begin)
    for index, weight in zip(indices, weights):
        length = span * weight / total
        times[index] = [cursor, cursor + max(MIN_WORD, length)]
        cursor += length


def _packed(tokens: list[str], indices: list[int]) -> float:
    return sum(NOMINAL_WORD * min(2.0, weight) for weight in _weights([tokens[index] for index in indices]))


def _fill_gaps(times: list[list[float] | None], tokens: list[str], line_of: list[int], duration: float) -> None:
    """Place lyric words Whisper never heard between the nearest heard ones."""
    count = len(tokens)
    index = 0
    while index < count:
        if times[index] is not None:
            index += 1
            continue
        run_end = index
        while run_end < count and times[run_end] is None:
            run_end += 1
        run = list(range(index, run_end))
        before = times[index - 1][1] if index > 0 else 0.0
        if run_end < count:
            after = times[run_end][0]
        else:
            after = max(before + _packed(tokens, run), duration or 0.0)
        after = max(after, before)

        prev_line = line_of[index - 1] if index > 0 else None
        next_line = line_of[run_end] if run_end < count else None
        head = [k for k in run if line_of[k] == prev_line]
        tail = [k for k in run if line_of[k] == next_line and line_of[k] != prev_line]
        middle = [k for k in run if k not in head and k not in tail]

        if _packed(tokens, run) >= (after - before) * 0.8 or (not middle and prev_line == next_line):
            # Tight gap, or words missed mid-line: share the gap evenly.
            _spread(times, tokens, run, before, after)
        else:
            # The end of the previous line follows it closely, the start of the
            # next line leads straight into it, and whole lines nobody heard
            # share whatever time is left between them.
            head_end = min(after, before + _packed(tokens, head))
            _spread(times, tokens, head, before, head_end)
            tail_start = max(head_end, after - _packed(tokens, tail))
            _spread(times, tokens, tail, tail_start, after)
            groups: dict[int, list[int]] = {}
            for k in middle:
                groups.setdefault(line_of[k], []).append(k)
            if groups:
                slot = (tail_start - head_end) / len(groups)
                for position, words in enumerate(groups.values()):
                    slot_start = head_end + position * slot
                    _spread(times, tokens, words, slot_start, slot_start + min(slot, _packed(tokens, words)))
        index = run_end


def sync_lyrics(lyrics: str, heard_cues: list[dict[str, Any]], duration: float | None = None) -> dict[str, Any]:
    """Time the user's lyrics with the words Whisper heard.

    Returns {"cues": [...], "report": {...}}; every cue carries one timed word
    per lyric token, so presets treat the result as word-accurate.
    """
    lines = lyric_lines(lyrics)
    if not lines:
        raise ValueError("Paste the lyrics first, one sung line per line.")
    tokens: list[str] = []
    line_of: list[int] = []
    for number, line in enumerate(lines):
        for token in line.split():
            tokens.append(token)
            line_of.append(number)

    heard = _heard_words(heard_cues)
    duration = float(duration or 0.0) or max((word["end"] for word in heard), default=0.0)
    times: list[list[float] | None] = [None] * len(tokens)
    status = ["estimated"] * len(tokens)

    if heard:
        keys = [word_key(token) for token in tokens]
        for kind, lyric_ids, heard_ids in _align(keys, [word["key"] for word in heard]):
            if kind not in {"match", "sub"}:
                continue
            begin, finish = heard[heard_ids[0]]["start"], heard[heard_ids[-1]]["end"]
            _spread(times, tokens, lyric_ids, begin, finish)
            for k in lyric_ids:
                status[k] = "heard" if kind == "match" else "guessed"
    if not heard and duration <= 0:
        duration = NOMINAL_WORD * 2 * len(tokens)
    _fill_gaps(times, tokens, line_of, duration)

    # Keep the chain monotonic and stop each word where the next one starts.
    previous = 0.0
    for k in range(len(tokens)):
        start = max(previous, times[k][0])
        end = max(start + MIN_WORD, times[k][1])
        times[k] = [start, end]
        previous = start + MIN_WORD
    for k in range(len(tokens) - 1):
        if line_of[k + 1] == line_of[k]:
            times[k][1] = max(times[k][0] + MIN_WORD * 0.5, min(times[k][1], times[k + 1][0]))

    cues = []
    for number, line in enumerate(lines):
        ids = [k for k in range(len(tokens)) if line_of[k] == number]
        words = [{"text": tokens[k], "start": round(times[k][0], 4), "end": round(times[k][1], 4)} for k in ids]
        cues.append({
            "id": f"cue-{number + 1}",
            "start": words[0]["start"],
            "end": max(words[-1]["end"], words[0]["start"] + 0.3),
            "text": line,
            "words": words,
        })
    for current, following in zip(cues, cues[1:]):
        current["end"] = max(current["words"][-1]["end"], min(current["end"], following["start"]))

    unheard = [number for number in range(len(lines))
               if not any(status[k] == "heard" for k in range(len(tokens)) if line_of[k] == number)]
    report = {
        "lines": len(lines),
        "words": len(tokens),
        "heard": status.count("heard"),
        "guessed": status.count("guessed"),
        "estimated": status.count("estimated"),
        "unheardLines": unheard,
    }
    return {"cues": normalize_cues(cues), "report": report}


def apply_lyric_sync(result: dict[str, Any], lyrics: str) -> dict[str, Any]:
    """Swap a transcription result's cues for the user's lyrics, timed by what was heard."""
    synced = sync_lyrics(lyrics, result.get("cues") or [], result.get("duration"))
    result["heardCues"] = result.get("cues") or []
    result["cues"] = synced["cues"]
    result["lyricSync"] = synced["report"]
    return result
