from __future__ import annotations

import re
from collections import Counter
from typing import Any


TEMPERATURE_FALLBACK = (0.0, 0.2, 0.4, 0.6, 0.8, 1.0)


def whisper_options(language: str, vad_filter: bool) -> dict[str, Any]:
    """Return conservative decode options for one language.

    Mixed-language tracks are handled a level up, in `karaokesesh.language_map`,
    which splits the song into spans and calls this once per span. Every decode
    therefore runs with one language locked in and full context conditioning.
    """
    requested = (language or "auto").strip().lower()
    options: dict[str, Any] = {
        "task": "transcribe",
        "beam_size": 5,
        "word_timestamps": True,
        "vad_filter": bool(vad_filter),
        "condition_on_previous_text": True,
        # Keep Whisper's quality fallback. A scalar 0.0 disables every retry
        # and allowed highly compressed loops such as 112 repeated "Uh" tokens.
        "temperature": TEMPERATURE_FALLBACK,
        "compression_ratio_threshold": 2.4,
        # Slightly stricter than Whisper's default: on the release song this
        # removes a classic low-confidence outro hallucination while preserving
        # the soft sung lines recovered by the adaptive temperature pass.
        "log_prob_threshold": -0.8,
        "no_speech_threshold": 0.6,
        "hallucination_silence_threshold": 2.0,
    }
    if requested and requested != "auto":
        options["language"] = requested
    if vad_filter:
        # Speech mode keeps a wider boundary pad than the library default. Song
        # mode leaves VAD off, preserving breathy or soft vocal entrances.
        options["vad_parameters"] = {
            "threshold": 0.45,
            "min_speech_duration_ms": 180,
            "min_silence_duration_ms": 700,
            "speech_pad_ms": 650,
        }
    return options


def _token(value: str) -> str:
    return "".join(char for char in value.casefold() if char.isalnum())


def repair_boundary_words(
    segment_text: str,
    words: list[dict[str, Any]],
    start: float,
    end: float,
) -> tuple[list[dict[str, Any]], int]:
    """Preserve prefix/suffix tokens present in text but missing timestamps."""
    text_tokens = [token for token in segment_text.split() if _token(token)]
    word_tokens = [_token(str(word.get("text", ""))) for word in words]
    if not text_tokens or not word_tokens or len(text_tokens) <= len(word_tokens):
        return words, 0

    match_at = -1
    for index in range(len(text_tokens) - len(word_tokens) + 1):
        if [_token(token) for token in text_tokens[index : index + len(word_tokens)]] == word_tokens:
            match_at = index
            break
    if match_at < 0:
        return words, 0

    prefix = text_tokens[:match_at]
    suffix = text_tokens[match_at + len(word_tokens) :]
    repaired: list[dict[str, Any]] = []
    first_start = float(words[0]["start"])
    prefix_span = max(0.03 * len(prefix), first_start - start)
    prefix_start = max(start, first_start - prefix_span)
    step = prefix_span / max(1, len(prefix))
    for index, token in enumerate(prefix):
        token_start = prefix_start + index * step
        repaired.append({"text": token, "start": token_start, "end": token_start + max(0.03, step)})

    repaired.extend(words)
    last_end = float(words[-1]["end"])
    suffix_span = max(0.0, end - last_end)
    desired_span = 0.03 * len(suffix)
    if suffix and suffix_span < desired_span:
        # Borrow a tiny tail from the last timed word instead of pushing a
        # recovered token into the following Whisper segment.
        borrowed_start = max(float(words[-1]["start"]) + 0.01, end - desired_span)
        words[-1]["end"] = max(float(words[-1]["start"]) + 0.01, borrowed_start)
        last_end = float(words[-1]["end"])
        suffix_span = max(0.0, end - last_end)
    step = suffix_span / max(1, len(suffix))
    for index, token in enumerate(suffix):
        token_start = last_end + index * step
        token_end = end if index == len(suffix) - 1 else token_start + step
        repaired.append({"text": token, "start": token_start, "end": max(token_start + 1e-4, token_end)})
    return repaired, len(prefix) + len(suffix)


def segment_diagnostic(segment: Any) -> dict[str, Any]:
    text = str(getattr(segment, "text", "")).strip()
    tokens = [_token(token) for token in re.findall(r"\S+", text)]
    counts = Counter(token for token in tokens if token)
    dominance = max(counts.values(), default=0) / max(1, len(tokens))
    compression = float(getattr(segment, "compression_ratio", 0.0) or 0.0)
    log_probability = float(getattr(segment, "avg_logprob", 0.0) or 0.0)
    repeated = len(tokens) >= 8 and dominance >= 0.65
    unstable = compression > 2.4 or log_probability < -0.8 or repeated
    return {
        "start": round(float(segment.start), 3),
        "end": round(float(segment.end), 3),
        "temperature": float(getattr(segment, "temperature", 0.0) or 0.0),
        "compressionRatio": round(compression, 3),
        "averageLogProbability": round(log_probability, 3),
        "noSpeechProbability": round(float(getattr(segment, "no_speech_prob", 0.0) or 0.0), 3),
        "repetitionDominance": round(dominance, 3),
        "unstable": unstable,
    }


def pathological_repetition(segment: Any) -> bool:
    """Catch runaway token loops, not legitimate repeated sung syllables."""
    tokens = [_token(token) for token in str(segment.text).split() if _token(token)]
    duration = max(.1, float(segment.end) - float(segment.start))
    dominance = max(Counter(tokens).values(), default=0) / max(1, len(tokens))
    return len(tokens) >= 40 and dominance >= .8 and len(tokens) / duration >= 10


def gauntlet_report(
    diagnostics: list[dict[str, Any]], repaired_words: int, language_mode: str
) -> dict[str, Any]:
    unstable = [index + 1 for index, item in enumerate(diagnostics) if item["unstable"]]
    fallback = [index + 1 for index, item in enumerate(diagnostics) if item["temperature"] > 0]
    warnings: list[str] = []
    if unstable:
        warnings.append(f"{len(unstable)} segment(s) remained unstable after adaptive decoding.")
    for item in diagnostics:
        if item.get("loopRecovery") == "unresolved":
            warnings.append(
                f"Unreliable repeated tokens at {item['start']:.1f}s–{item['end']:.1f}s were omitted; "
                "review this passage and add any missing lyrics manually."
            )
    return {
        "task": "transcribe",
        "languageMode": language_mode,
        "segmentsChecked": len(diagnostics),
        "adaptiveFallbackSegments": fallback,
        "unstableSegments": unstable,
        "repairedBoundaryWords": repaired_words,
        "warnings": warnings,
    }
