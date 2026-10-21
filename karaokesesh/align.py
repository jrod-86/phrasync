"""Lyric-to-music alignment.

Whisper word timestamps are close but rarely musical: they drift by a constant
latency and land a few tens of milliseconds off the actual sung attack. These
helpers pull them onto the detected vocal onsets and the beat grid, which is
what makes a lyric video feel "on time" rather than merely correct.
"""

from __future__ import annotations

from typing import Any
import math

from .kinetic import clamp, cue_words

MIN_WORD_DURATION = 0.10
MIN_CUE_DURATION = 0.30


def trim_silent_entrances(
    cues: list[dict[str, Any]], analysis: dict[str, Any]
) -> tuple[list[dict[str, Any]], int]:
    """Trim demonstrable silence swallowed by a phrase's first timestamp.

    This is deliberately not a vocal detector: instrumental or soft audible
    material is left alone. Word ends and all subsequent word timestamps stay
    intact. Never apply a guessed fixed delay to every word.
    """
    peaks = analysis.get("peaks") or []
    rate = float(analysis.get("peaksPerSecond") or 0)
    if not peaks or not math.isfinite(rate) or rate < 20:
        return cues, 0
    result = []
    corrected = 0
    previous_end = -math.inf
    for cue in cues:
        stored = cue.get("words") or []
        updated = cue
        if stored:
            first = stored[0]
            start, end = float(first["start"]), float(first["end"])
            if start - previous_end >= 0.25 and end - start >= 0.45:
                begin = max(0, math.ceil(start * rate))
                finish = min(len(peaks), math.floor(end * rate))
                window = peaks[begin:finish]
                peak = max(window, default=0)
                # Peaks are perceptually scaled to 0..255. This low ceiling
                # protects quiet syllables and sustained notes from trimming.
                quiet = min(12.0, peak * 0.08)
                run = max(2, math.ceil(rate * 0.05))
                onset = next((i for i, value in enumerate(window) if value > quiet), None)
                if peak >= 24 and onset is not None and onset / rate >= 0.18:
                    attack = window[onset:onset + run]
                    new_start = max(start, (begin + onset) / rate - 0.04)
                    if (len(attack) == run and all(value > quiet for value in attack)
                            and new_start <= end - MIN_WORD_DURATION):
                        updated = {**cue, "start": new_start,
                                   "words": [{**first, "start": new_start},
                                             *[dict(word) for word in stored[1:]]]}
                        corrected += 1
        result.append(updated)
        previous_end = float(cue.get("end", 0))
    return result, corrected


def _word_starts(cues: list[dict[str, Any]]) -> list[float]:
    starts: list[float] = []
    for cue in cues:
        for word in cue_words(cue):
            starts.append(float(word["start"]))
    return starts


def estimate_offset(
    cues: list[dict[str, Any]],
    onsets: list[float],
    search: float = 0.45,
    step: float = 0.005,
) -> dict[str, float]:
    """Best constant shift that lines lyric words up with musical onsets.

    Scores every candidate shift by a Gaussian-weighted vote over the distance
    from each shifted word start to its nearest onset, so a systematic recording
    or model latency shows up as a clear peak.
    """
    starts = _word_starts(cues)
    if not starts or not onsets:
        return {"offset": 0.0, "confidence": 0.0, "before": 0.0, "after": 0.0}

    sorted_onsets = sorted(onsets)
    sigma = 0.07

    def score(shift: float) -> tuple[float, float]:
        total = 0.0
        error = 0.0
        for start in starts:
            distance = _nearest_distance(start + shift, sorted_onsets)
            total += pow(2.718281828459045, -((distance / sigma) ** 2))
            error += min(distance, 0.5)
        return total / len(starts), error / len(starts)

    baseline_score, baseline_error = score(0.0)
    best_shift = 0.0
    best_score = baseline_score
    best_error = baseline_error

    steps = int(search / step)
    for index in range(-steps, steps + 1):
        shift = index * step
        value, error = score(shift)
        if value > best_score:
            best_score = value
            best_shift = shift
            best_error = error

    confidence = clamp(best_score - baseline_score + best_score * 0.5)
    return {
        "offset": round(best_shift, 4),
        "confidence": round(confidence, 3),
        "before": round(baseline_error, 4),
        "after": round(best_error, 4),
    }


def _nearest_distance(value: float, sorted_targets: list[float]) -> float:
    import bisect

    if not sorted_targets:
        return 1.0
    index = bisect.bisect_left(sorted_targets, value)
    best = float("inf")
    for candidate in (index - 1, index):
        if 0 <= candidate < len(sorted_targets):
            best = min(best, abs(sorted_targets[candidate] - value))
    return best


def _nearest(value: float, sorted_targets: list[float]) -> float | None:
    import bisect

    if not sorted_targets:
        return None
    index = bisect.bisect_left(sorted_targets, value)
    best = None
    best_distance = float("inf")
    for candidate in (index - 1, index):
        if 0 <= candidate < len(sorted_targets):
            distance = abs(sorted_targets[candidate] - value)
            if distance < best_distance:
                best_distance = distance
                best = sorted_targets[candidate]
    return best


def align_cues(
    cues: list[dict[str, Any]],
    analysis: dict[str, Any],
    *,
    offset: float | None = None,
    snap_words: bool = True,
    word_window: float = 0.14,
    word_strength: float = 0.85,
    snap_phrases: bool = False,
    phrase_grid: str = "beat",
    auto_offset: bool = True,
    trim_silence: bool = True,
) -> dict[str, Any]:
    """Return re-timed cues plus a report on what changed."""
    onsets = sorted(float(value) for value in (analysis.get("onsets") or []))
    duration = float(analysis.get("duration") or 0.0)
    bpm = float(analysis.get("bpm") or 0.0)
    beat_offset = float(analysis.get("beatOffset") or 0.0)

    cues, trimmed = trim_silent_entrances(cues, analysis) if trim_silence else (cues, 0)
    report: dict[str, Any] = {"offset": 0.0, "offsetConfidence": 0.0, "snapped": 0, "words": 0,
                              "trimmedSilentEntrances": trimmed}

    if offset is None and auto_offset:
        estimate = estimate_offset(cues, onsets)
        offset = estimate["offset"]
        report["offsetConfidence"] = estimate["confidence"]
        report["errorBefore"] = estimate["before"]
    offset = float(offset or 0.0)
    report["offset"] = round(offset, 4)

    grid: list[float] = []
    if snap_phrases and bpm > 0:
        period = 60.0 / bpm
        if phrase_grid == "half":
            period /= 2
        elif phrase_grid == "bar":
            period *= 4
        count = int((duration - beat_offset) / period) + 2 if duration else 0
        grid = [beat_offset + index * period for index in range(max(0, count))]

    result: list[dict[str, Any]] = []
    previous_end = 0.0

    for cue in cues:
        words = cue_words(cue)
        shifted = [
            {"text": word["text"], "start": word["start"] + offset, "end": word["end"] + offset}
            for word in words
        ]

        if snap_words and onsets:
            for word in shifted:
                target = _nearest(word["start"], onsets)
                if target is None:
                    continue
                delta = target - word["start"]
                if abs(delta) <= word_window:
                    word["start"] += delta * clamp(word_strength)
                    report["snapped"] += 1
        report["words"] += len(shifted)

        # Keep the word chain monotonic. Consecutive starts are held a full
        # MIN_WORD_DURATION apart so no word can be squeezed down to a two-frame
        # flash, which is visible as a blink in the wipe and focus presets.
        for index, word in enumerate(shifted):
            word["start"] = max(0.0, word["start"])
            if index > 0:
                word["start"] = max(word["start"], shifted[index - 1]["start"] + MIN_WORD_DURATION)
        for index, word in enumerate(shifted):
            following = shifted[index + 1]["start"] if index + 1 < len(shifted) else None
            end = max(word["start"] + MIN_WORD_DURATION, word["end"])
            if following is not None:
                end = max(min(end, following), word["start"] + MIN_WORD_DURATION)
            word["end"] = end

        if shifted:
            start = shifted[0]["start"]
            end = max(shifted[-1]["end"], start + MIN_CUE_DURATION)
        else:
            start = max(0.0, float(cue.get("start", 0)) + offset)
            end = max(start + MIN_CUE_DURATION, float(cue.get("end", start + 1)) + offset)

        if grid:
            target = _nearest(start, grid)
            if target is not None and abs(target - start) <= 0.5 * (60.0 / max(bpm, 1)):
                delta = target - start
                start += delta
                end += delta
                for word in shifted:
                    word["start"] += delta
                    word["end"] += delta

        start = max(previous_end, max(0.0, start))
        normalized_words: list[dict[str, Any]] = []
        word_cursor = start
        for word in shifted:
            word_start = max(start, word_cursor, word["start"])
            word_end = max(word_start + MIN_WORD_DURATION, word["end"])
            normalized_words.append({"text": word["text"], "start": word_start, "end": word_end})
            word_cursor = word_end
        end = max(end, start + MIN_CUE_DURATION)
        if normalized_words:
            end = max(end, normalized_words[-1]["end"])
        previous_end = end

        result.append(
            {
                **cue,
                "start": round(start, 4),
                "end": round(end, 4),
                "words": [
                    {
                        "text": word["text"],
                        "start": round(word["start"], 4),
                        "end": round(word["end"], 4),
                    }
                    for word in normalized_words
                ],
            }
        )

    report["errorAfter"] = round(alignment_error(result, onsets), 4)
    return {"cues": result, "report": report}


def alignment_error(cues: list[dict[str, Any]], onsets: list[float]) -> float:
    """Mean distance in seconds from each word start to the nearest onset."""
    sorted_onsets = sorted(onsets)
    if not sorted_onsets:
        return 0.0
    distances = [
        min(_nearest_distance(float(word["start"]), sorted_onsets), 0.5)
        for cue in cues
        for word in cue_words(cue)
    ]
    return sum(distances) / len(distances) if distances else 0.0


def alignment_stats(cues: list[dict[str, Any]], analysis: dict[str, Any]) -> dict[str, Any]:
    """Quality metrics used by the critic and the QA loop."""
    onsets = sorted(float(value) for value in (analysis.get("onsets") or []))
    distances: list[float] = []
    for cue in cues:
        for word in cue_words(cue):
            distances.append(min(_nearest_distance(float(word["start"]), onsets), 0.5))

    if not distances:
        return {"words": 0, "meanError": 0.0, "tight": 0.0, "loose": 0.0, "score": 0}

    total = len(distances)
    tight = sum(1 for value in distances if value <= 0.06) / total
    ok = sum(1 for value in distances if value <= 0.12) / total
    loose = sum(1 for value in distances if value > 0.25) / total
    mean_error = sum(distances) / total
    score = int(round(clamp(1.0 - mean_error / 0.25) * 60 + tight * 40))

    return {
        "words": total,
        "meanError": round(mean_error, 4),
        "tight": round(tight, 3),
        "ok": round(ok, 3),
        "loose": round(loose, 3),
        "score": score,
    }
