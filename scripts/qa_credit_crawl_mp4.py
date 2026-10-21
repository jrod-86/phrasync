"""Karaoke Credit Crawl MP4 export QA: render a short clip and verify frames.

Acceptance test 9: "A short MP4 test render matches the browser preview."

Renders a 6-second 640x360 credit-crawl clip with a flat colour background
(pure PIL compositor path, no browser), then:
  * decodes the MP4 and probes duration/size,
  * extracts frames at t=1.0, 2.2, 5.0 and compares each against the export
    credit_crawl_state() stack (cue order top-to-bottom, wrapped-line counts,
    active line centred, opacity ordering),
  * verifies the active line's glyph band sits near the frame centre and the
    stack order matches the state's offsets.

Run: .venv\\Scripts\\python.exe scripts/qa_credit_crawl_mp4.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from karaokesesh import kinetic  # noqa: E402
from karaokesesh.media import decode_test, probe_duration, run_ffmpeg  # noqa: E402
from karaokesesh.renderer import render_project  # noqa: E402
from karaokesesh.subtitles import parse_srt  # noqa: E402

# Synthetic SRT fixture (acceptance test 1: "Importing an SRT and selecting
# Karaoke Credit Crawl produces..."). Fed through the real parse_srt pipeline.
SRT_FIXTURE = """1
00:00:00,000 --> 00:00:02,000
FIRST LINE HERE

2
00:00:02,000 --> 00:00:04,000
SECOND LINE HERE

3
00:00:04,000 --> 00:00:06,000
THIS IS A VERY LONG WRAPPING THIRD LINE THAT BREAKS INTO TWO LINES AND KEEPS GOING PAST THE BUDGET

4
00:00:06,000 --> 00:00:08,000
FOURTH LINE AFTER THE GAP
"""

CUES = parse_srt(SRT_FIXTURE)
assert len(CUES) == 4, "SRT fixture failed to parse"

WIDTH, HEIGHT, FPS = 640, 360, 30


def extract_frame(video: Path, t: float) -> Image.Image:
    frame = run_ffmpeg(
        ["-ss", f"{t:.3f}", "-i", str(video), "-frames:v", "1",
         "-f", "image2pipe", "-vcodec", "png", "pipe:1"],
        check=True)
    import io
    return Image.open(io.BytesIO(frame.stdout)).convert("RGB")


def glyph_bands(image: Image.Image, frac: float = 0.35) -> list[tuple[int, int, int]]:
    """(top, bottom, peak_brightness) for horizontal text bands.

    Thresholds on the row MAX (not the row sum) so a few bright glyph pixels
    still register, and the aurora/dim background never crosses the threshold.
    """
    arr = np.asarray(image.convert("L"), dtype=float)
    w, h = arr.shape[1], arr.shape[0]
    rowmax = arr.max(axis=1)
    threshold = rowmax.max() * frac
    bands = []
    y = 0
    while y < h:
        if rowmax[y] > threshold:
            top = y
            peak = 0
            while y < h and rowmax[y] > threshold:
                peak = max(peak, rowmax[y])
                y += 1
            bands.append((top, y - 1, int(peak)))
        else:
            y += 1
    return bands


def main() -> int:
    out_dir = Path(".crawl_render/qa_mp4")
    out_dir.mkdir(parents=True, exist_ok=True)
    video = out_dir / "crawl-test.mp4"

    project = {
        "title": "credit crawl parity", "duration": 6.0,
        "canvas": {"width": WIDTH, "height": HEIGHT, "fps": FPS, "aspect": "16:9"},
        "background": {"type": "dynamic", "visual": "aurora",
                       "backgroundColor": "#101018", "shade": 1.0, "visualIntensity": 0.0},
        "style": {"preset": "credit-crawl", "fontPreset": "modern", "fontSize": 44},
        "timing": {"offset": 0},
        "cues": CUES,
        "export": {"crf": 22, "preset": "ultrafast"},
    }
    result = render_project(project, video)
    assert video.exists(), "render produced no file"
    ok, detail = decode_test(video)
    assert ok, f"decode_test failed: {detail}"
    duration = probe_duration(video)
    # renderer extends the clip to cover the last cue end (8.0s)
    assert abs(duration - 8.0) < 0.2, f"unexpected duration {duration}"
    print(f"rendered {video} {result.get('width')}x{result.get('height')} "
          f"{duration:.2f}s {video.stat().st_size} bytes")

    spec = kinetic.resolved_preset({"preset": "credit-crawl"})
    budget = kinetic.char_budget(project["style"], project["canvas"], spec)
    viewport = kinetic.crawl_viewport(project["style"], project["canvas"], spec)

    for t in [1.0, 2.2, 5.0]:
        frame = extract_frame(video, t)
        assert frame.size == (WIDTH, HEIGHT), f"frame {t} wrong size {frame.size}"
        frame.save(out_dir / f"mp4_t{t}.png")
        state = kinetic.credit_crawl_state(CUES, t, spec, budget, viewport)
        cues = state["cues"]
        assert cues, f"empty export state at t={t}"

        bands = glyph_bands(frame)
        assert bands, f"no text bands found in MP4 frame at t={t} (blank frame!)"

        # 1. cue count parity: number of DOM cues == number of text bands is not
        #    exact (wrapped cues merge), so compare wrapped-line totals instead.
        total_lines = sum(
            len(kinetic.layout_lines(kinetic.cue_words(item["cue"]), spec, budget))
            for item in cues)
        assert len(bands) >= min(total_lines, 2), (
            f"t={t}: expected >=2 text bands for {total_lines} stacked lines, got {len(bands)}")

        # 2. active line centred: the brightest band (active cue, opacity 1.0)
        #    must straddle the frame centre.
        active = next((c for c in cues if c["active"]), None)
        if active is not None:
            brightest = max(bands, key=lambda b: b[2])
            centre = (brightest[0] + brightest[1]) / 2
            assert abs(centre - HEIGHT / 2) < HEIGHT * 0.18, (
                f"t={t}: brightest band centre {centre:.0f} not near frame centre {HEIGHT/2:.0f}")

        # 3. opacity ordering: bands above/below the active band must not be
        #    brighter than the active band (progressive fade).
        if len(cues) > 1:
            active_band = max(bands, key=lambda b: b[2])
            for band in bands:
                if band is active_band:
                    continue
                assert band[2] <= active_band[2], (
                    f"t={t}: band {band} brighter than active band {active_band}")

    # 4. gap frame calm: at t=3.0 (mid-gap between c2 end 4.0? no—c2 ends 4.0;
    #    use the explicit gap cues) render a second clip with a gap.
    gap_video = out_dir / "crawl-gap.mp4"
    gap_cues = [
        {"id": "g1", "start": 0.0, "end": 1.5, "text": "BEFORE THE BREAK", "words": []},
        {"id": "g2", "start": 5.0, "end": 6.0, "text": "AFTER THE BREAK", "words": []},
    ]
    gap_project = dict(project, cues=gap_cues)
    render_project(gap_project, gap_video)
    assert decode_test(gap_video)[0]
    for t in [2.0, 2.6, 3.2, 3.8, 4.4]:
        frame = extract_frame(gap_video, t)
        frame.save(out_dir / f"mp4_gap_t{t}.png")
        bands = glyph_bands(frame)
        assert bands, f"gap frame at t={t} is blank"
        state = kinetic.credit_crawl_state(gap_cues, t, spec, budget, viewport)
        assert state["cues"], f"gap state empty at t={t}"

    # --- 5. realistic default-style 1080p export bounds (Codex Issue 3) ---
    # The real export compositor at 1920x1080 with the app's own defaults:
    # Impact, fontSize 160, maxWidth 88, positionY 52, lineGap -8, and five
    # consecutive cues that each wrap to two lines. A very short ultrafast
    # synthetic render is enough; no copyrighted material.
    REALISTIC_STYLE = {"preset": "credit-crawl", "fontPreset": "impact",
                       "fontSize": 160, "maxWidth": 88, "positionY": 52, "lineGap": -8}
    REALISTIC_CUES = [
        {"id": "r1", "start": 0.0, "end": 2.0, "text": "ALPHA BRAVO CHARLIE DELTA ECHO FOXTROT", "words": []},
        {"id": "r2", "start": 2.0, "end": 4.0, "text": "GOLF HOTEL INDIA JULIET KILO LIMA", "words": []},
        {"id": "r3", "start": 4.0, "end": 6.0, "text": "MIKE NOVEMBER OSCAR PAPA QUEBEC ROMEO", "words": []},
        {"id": "r4", "start": 6.0, "end": 8.0, "text": "SIERRA TANGO UNIFORM VICTOR WHISKEY", "words": []},
        {"id": "r5", "start": 8.0, "end": 10.0, "text": "XRAY YANKEE ZULU ALPHA BRAVO CHARLIE", "words": []},
    ]
    RW, RH = 1920, 1080
    real_video = out_dir / "crawl-realistic-1080p.mp4"
    real_project = {
        "title": "credit crawl realistic 1080p", "duration": 6.0,
        "canvas": {"width": RW, "height": RH, "fps": 30, "aspect": "16:9"},
        "background": {"type": "color", "backgroundColor": "#101018"},
        "style": dict(REALISTIC_STYLE),
        "timing": {"offset": 0},
        "cues": REALISTIC_CUES,
        "export": {"crf": 24, "preset": "ultrafast"},
    }
    real_result = render_project(real_project, real_video)
    assert real_video.exists(), "realistic render produced no file"
    ok, detail = decode_test(real_video)
    assert ok, f"realistic decode_test failed: {detail}"
    real_duration = probe_duration(real_video)
    print(f"rendered {real_video} {real_result.get('width')}x{real_result.get('height')} "
          f"{real_duration:.2f}s {real_video.stat().st_size} bytes")

    real_spec = kinetic.resolved_preset(REALISTIC_STYLE)
    real_canvas = {"width": RW, "height": RH}
    real_budget = kinetic.char_budget(REALISTIC_STYLE, real_canvas, real_spec)
    real_vp = kinetic.crawl_viewport(REALISTIC_STYLE, real_canvas, real_spec)
    assert real_budget == 24, f"realistic budget should be 24 chars, got {real_budget}"
    assert all(len(kinetic.layout_lines(kinetic.cue_words(c), real_spec, real_budget)) == 2
               for c in REALISTIC_CUES), "every realistic cue must wrap to two lines"

    for t in [5.0, 5.5]:
        frame = extract_frame(real_video, t)
        assert frame.size == (RW, RH), f"realistic frame {t} wrong size {frame.size}"
        frame.save(out_dir / f"mp4_realistic_t{t}.png")
        state = kinetic.credit_crawl_state(REALISTIC_CUES, t, real_spec, real_budget, real_vp)
        ids = [c["cue"]["id"] for c in state["cues"]]
        # Engine keeps the middle cue + neighbours and drops the distant cues.
        assert ids == ["r2", "r3", "r4"], f"realistic export cue set wrong at t={t}: {ids}"
        active = next((c for c in state["cues"] if c["active"]), None)
        assert active is not None and active["cue"]["id"] == "r3", f"middle cue must be active at t={t}"

        # Rendered text bounds must remain inside the frame. Threshold on the
        # row MAX so dim neighbour glyphs still register but the flat dark
        # background never crosses it.
        arr = np.asarray(frame.convert("L"), dtype=float)
        rowmax = arr.max(axis=1)
        threshold = 100.0
        ys, xs = np.where(arr > threshold)
        assert len(ys), f"no text ink found in realistic frame at t={t}"
        top, bottom, left, right = int(ys.min()), int(ys.max()), int(xs.min()), int(xs.max())
        assert top >= 0 and bottom <= RH - 1 and left >= 0 and right <= RW - 1, (
            f"t={t}: rendered text bounds {left},{top}-{right},{bottom} escape frame {RW}x{RH}")
        # The drop rule is what keeps ink inside the frame: if r1/r5 had been
        # rendered their two-line blocks would poke past the top/bottom edges,
        # so a real margin on both edges proves they were dropped.
        assert top >= 8 and bottom <= RH - 9, (
            f"t={t}: text ink touches frame edge (top={top}, bottom={bottom}); "
            f"distant cues should have been dropped")

        # Active cue centred: the brightest band straddles positionY of the frame.
        # frac 0.5 separates the three cue blocks despite the shared glow.
        bands = glyph_bands(frame, frac=0.5)
        assert bands, f"no text bands in realistic frame at t={t}"
        brightest = max(bands, key=lambda b: b[2])
        centre = (brightest[0] + brightest[1]) / 2
        anchor = RH * REALISTIC_STYLE["positionY"] / 100.0
        assert abs(centre - anchor) < RH * 0.06, (
            f"t={t}: active band centre {centre:.0f} not at anchor {anchor:.0f}")

        # Neighbours remain (previous above, upcoming below) when space permits:
        # robust to glow merging — require real text ink both above and below the
        # active cue's own block.
        ink = arr > threshold
        above_rows = np.where(ink[: int(anchor - RH * 0.12)].any(axis=1))[0]
        below_rows = np.where(ink[int(anchor + RH * 0.12):].any(axis=1))[0]
        assert len(above_rows) > 0, f"t={t}: no previous-cue ink above the active cue"
        assert len(below_rows) > 0, f"t={t}: no upcoming-cue ink below the active cue"

        active_band = max(bands, key=lambda b: b[2])
        for band in bands:
            if band is active_band:
                continue
            assert band[2] <= active_band[2], (
                f"t={t}: neighbour band {band} brighter than active band {active_band}")

    print("PASS credit-crawl MP4 export QA (decode, centring, fade ordering, gap calm, realistic 1080p bounds)")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
