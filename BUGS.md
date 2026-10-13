# BUGS.md

## Open defects
| ID | Defect | Evidence | Status |
|----|--------|----------|--------|
| B1 | Enhanced LRC `<mm:ss.xxx>` word tags import as visible lyric text in Phrasync | Recorded in `00-master-index/04-decisions-and-reference/decisions-and-known-issues.md` ("Phrasync 0.4.5 imports the tested Enhanced LRC word-timestamp tags as visible text"); `phrasync/subtitles.py` `parse_lrc` only matches `[mm:ss.xx]` line tags and keeps the rest as text | open — Phase 3 |
| B2 | ELYSY Standard/Enhanced LRC exports start 29.868 s later than the Premiere SRT for the same lyric | Recorded in decisions-and-known-issues.md. Code inspection of `C:/AI/ELYSY/ELYSY-1.1.0/backend/lrc_generator.py`: all four export formats derive from the same `words[0]["start"]`, so the formatters are consistent; ELYSY's frontend defaults its offset input to 0.5 s and `/api/offset` mutates session aligned data. Leading hypothesis: the tested LRC files were exported after an offset shift or from a different alignment session. Needs controlled reproduction | open — Phase 4 (diagnosis) |

## Closed defects
- Codex review round 1 findings (viewport bounds, phrase-only word fill, single active cue) — closed in `0827a2f`.
- Codex review round 2 issues (nested-overlap anchor regression, word-count-only timing validation, realistic 1080p QA gap) — closed in `647652c`.

## No-known-defect areas
- Crawl state parity Python vs Node-JS: pinned by `tests/test_kinetic.py` grid.
- Existing presets: untouched by all feature commits.
