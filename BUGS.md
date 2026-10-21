# BUGS.md

## Open defects
| ID | Defect | Evidence | Status |
|----|--------|----------|--------|
| B1 | Enhanced LRC `<mm:ss.xxx>` word tags import as visible lyric text in KaraokeSesh | Recorded in `00-master-index/04-decisions-and-reference/decisions-and-known-issues.md` ("KaraokeSesh 0.4.5 imports the tested Enhanced LRC word-timestamp tags as visible text"); `karaokesesh/subtitles.py` `parse_lrc` only matches `[mm:ss.xx]` line tags and keeps the rest as text | open — Phase 3 |
| B2 | ELYSY Standard/Enhanced LRC exports start 29.868 s later than the Premiere SRT for the same lyric | Recorded in decisions-and-known-issues.md. Code inspection of `C:/AI/ELYSY/ELYSY-1.1.0/backend/lrc_generator.py`: all four export formats derive from the same `words[0]["start"]`, so the formatters are consistent; ELYSY's frontend defaults its offset input to 0.5 s and `/api/offset` mutates session aligned data. Leading hypothesis: the tested LRC files were exported after an offset shift or from a different alignment session. Needs controlled reproduction | open — Phase 4 (diagnosis) |

## Closed defects
- Codex review round 1 findings (viewport bounds, phrase-only word fill, single active cue) — closed in `0827a2f`.
- Codex review round 2 issues (nested-overlap anchor regression, word-count-only timing validation, realistic 1080p QA gap) — closed in `647652c`.
- Codex review round 3 Finding 1 (P1): `#crawlControls` stayed hidden when credit-crawl was selected through the real preset dropdown; controls appeared only after reload or an artificial `applyProjectToControls()` call. Closed: the `stylePreset` change handler in `static/app.js` now calls `updatePresetPresentation()` (existing UI-refresh path); pinned by `tests/test_frontend.py::test_style_preset_change_refreshes_crawl_controls` and the real-dropdown section of `scripts/qa_crawl_controls.py`.
- Codex review round 3 Finding 2 (P2): `applyCrawlControlsUI()` hydrated controls with unrestricted `Number()`, so the UI could display/clamp malformed saved values (`transition: null` → 150 ms, `nextLines: "0x10"` → 4) that both renderers correctly reject, and moving one slider rewrote all six fields with the wrong displayed values. Closed: `crawlStyleFromControls()` derives effective values via `VFKinetic.resolvedPreset()`/`mergeCrawlOverrides()` and `applyCrawlControlsUI()` displays them; pinned by the malformed-reload section of `scripts/qa_crawl_controls.py` (displayed == JS resolved == Python resolved, one-slider-move isolation).

## No-known-defect areas
- Crawl state parity Python vs Node-JS: pinned by `tests/test_kinetic.py` grid.
- Existing presets: untouched by all feature commits.
