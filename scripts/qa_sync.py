"""Sync and visual QA for a KaraokeSesh project.

Renders a contact sheet using the same engine as the MP4 export and scores how
closely the lyrics sit on the detected vocal attacks.

    python scripts/qa_sync.py project.karaokesesh.json --out qa/ --preset kinetic-slam

With no project path it uses the newest file in the KaraokeSesh projects folder.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from PIL import Image  # noqa: E402

from karaokesesh.align import alignment_stats  # noqa: E402
from karaokesesh.audio_analysis import analyze_audio  # noqa: E402
from karaokesesh.config import PROJECTS_DIR  # noqa: E402
from karaokesesh.kinetic import cue_words  # noqa: E402
from karaokesesh.renderer import FrameComposer, _build_context  # noqa: E402
from karaokesesh.storage import get_asset  # noqa: E402


def newest_project() -> Path:
    candidates = sorted(PROJECTS_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not candidates:
        raise SystemExit(f"No project found in {PROJECTS_DIR}. Save one from the editor first.")
    return candidates[0]


def sample_times(project: dict, count: int) -> list[float]:
    """Pick moments that show the animation mid-flight, not just resting states."""
    cues = project.get("cues") or []
    if not cues:
        return []
    stamps: list[float] = []
    step = max(1, len(cues) // max(1, count // 2))
    for cue in cues[::step]:
        words = cue_words(cue)
        if not words:
            continue
        middle = words[len(words) // 2]
        stamps.append(middle["start"] + 0.05)
        stamps.append(middle["start"] + (middle["end"] - middle["start"]) * 0.6)
    return sorted(stamps)[:count]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("project", nargs="?", help="Project JSON (defaults to the newest saved project)")
    parser.add_argument("--out", default="qa_out", help="Output directory")
    parser.add_argument("--preset", help="Override the style preset for this run")
    parser.add_argument("--frames", type=int, default=12, help="How many frames to sample")
    parser.add_argument("--width", type=int, default=960, help="Contact-sheet tile width")
    parser.add_argument("--json", action="store_true", help="Print the report as JSON only")
    args = parser.parse_args()

    path = Path(args.project) if args.project else newest_project()
    project = json.loads(path.read_text(encoding="utf-8"))
    project = project.get("project", project)
    if args.preset:
        project.setdefault("style", {})["preset"] = args.preset

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    report: dict = {"project": str(path), "preset": project.get("style", {}).get("preset")}

    audio = get_asset(project.get("audioAssetId"), "audio") if project.get("audioAssetId") else None
    if audio:
        analysis = analyze_audio(Path(audio.path))
        report["bpm"] = analysis["bpm"]
        report["tempoConfidence"] = analysis["tempoConfidence"]
        report["alignment"] = alignment_stats(project.get("cues") or [], analysis)
    else:
        report["alignment"] = None

    stamps = sample_times(project, args.frames)
    report["frames"] = [round(value, 3) for value in stamps]

    ctx = _build_context(project)
    composer = FrameComposer(ctx)
    tile_w = args.width
    tile_h = round(tile_w * ctx.height / ctx.width)
    columns = 2
    rows = (len(stamps) + columns - 1) // columns
    sheet = Image.new("RGB", (tile_w * columns, tile_h * max(1, rows)), (8, 8, 14))

    for index, stamp in enumerate(stamps):
        # Same composite the exporter writes, so the sheet shows the real frame.
        frame = composer.frame(stamp, int(stamp * ctx.fps))
        tile = frame.resize((tile_w, tile_h), Image.Resampling.LANCZOS)
        sheet.paste(tile, ((index % columns) * tile_w, (index // columns) * tile_h))

    sheet_path = out / f"sheet_{report['preset']}.png"
    sheet.save(sheet_path)
    report["sheet"] = str(sheet_path)

    composer.close()
    (out / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        stats = report.get("alignment")
        print(f"project : {path.name}")
        print(f"preset  : {report['preset']}")
        if stats:
            print(f"bpm     : {report['bpm']} (confidence {report['tempoConfidence']})")
            print(f"sync    : {stats['score']}/100 · mean {round(stats['meanError'] * 1000)} ms · "
                  f"{round(stats['tight'] * 100)}% within 60 ms · {round(stats['loose'] * 100)}% beyond 250 ms")
        else:
            print("sync    : no audio attached")
        print(f"sheet   : {sheet_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
