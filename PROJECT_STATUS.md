# PROJECT_STATUS.md

## Current verified state
- Updated: 2026-10-13 (session: autonomous-coder-lcm, Phase 2 completion run)
- Milestone: #6 — Phase 2 crawl controls **complete, all acceptance checks green**
- Task: NEXT_TASK.md

## Completed since prior checkpoint
- Phase 2 implementation verified complete across both engines + UI + tests:
  `style.crawl` overrides merged via `merge_crawl_overrides` (Python) /
  `mergeCrawlOverrides` (JS) with identical `CRAWL_LIMITS` clamps; six sliders
  in `#crawlControls` (index.html) wired in `app-modes.js`; parity + override
  tests in `tests/test_kinetic.py`.
- Parity divergence found and fixed: Python `float()` accepts `"1_000"`
  (underscore) and JS `Number()` accepts `"0x10"`/arrays-as-0 — both engines
  now pin to one decimal-string grammar (`CRAWL_NUMERIC_RE`) and pinned by a
  new test case (`tricky`) in the parity grid.
- `scripts/qa_crawl_controls.py` repaired: the draft used a non-existent
  `DevTools` context-manager/`send`/`last_response` API, a non-existent
  `/api/project` endpoint, `seekTo` without the `renderLyric` pump, and a
  Chrome launch missing `--remote-allow-origins=*`. Rewritten against the
  proven `qa_credit_crawl.py` harness; now PASS.
- Full test suite re-run this session: **180 passed, 0 failed** (was 177;
  +3 from the crawl-controls override/parity tests).
- ELYSY license verified: MIT (`C:\AI\ELYSY\ELYSY-1.1.0\LICENSE`) — Phase 4 gate satisfied.
- ELYSY export code inspected (`backend/lrc_generator.py`): all four export formats derive timestamps from the same `words[0]["start"]`; the 29.868 s LRC-vs-SRT discrepancy is NOT in the formatters. ELYSY's frontend has a default `0.5 s` offset input and `/api/offset` shifts aligned data.

## Files created/changed this session
- `phrasync/kinetic.py` — `CRAWL_LIMITS`, `CRAWL_NUMERIC_RE`, `merge_crawl_overrides`, `resolved_preset` merge.
- `static/kinetic.js` — mirrored `CRAWL_LIMITS`, `CRAWL_NUMERIC_RE`, `mergeCrawlOverrides`; `resolvedPreset` merges `style.crawl`.
- `static/app-modes.js` — crawl controls UI wiring (`crawlInputs`, `crawlStyleFromControls`, `applyCrawlControlsUI`).
- `static/index.html` — `#crawlControls` panel with six range inputs.
- `static/app.js` — crawl slider bindings + range outputs.
- `tests/test_kinetic.py` — override/clamp/immutability tests + Python↔JS parity grid incl. malformed and tricky-string cases.
- `scripts/qa_crawl_controls.py` — new browser QA (rewritten this session).
- Checkpoint files (PROJECT.md, PROJECT_PLAN.md, PROJECT_STATUS.md, NEXT_TASK.md, DECISIONS.md, BUGS.md, TEST_RESULTS.md, LESSONS.md).

## Last known-good commit
`647652c` — "Remediate second Codex review: monotonic crawl anchor, strict word timing, realistic 1080p QA" (clean tree at that commit).

## Tests run
- `.venv\Scripts\python.exe -m pytest` → **180 passed, 0 failed** (19.27s, this session).

## Browser/UI verification this session
- `scripts\qa_crawl_controls.py` PASS (crawl controls visibility, live tuning, preview/export parity, save/reload, malformed fallback).
- `scripts\qa_credit_crawl.py` PASS (regression, incl. realistic 1080p bounds).
- `scripts\qa_credit_crawl_mp4.py` PASS (regression, incl. 1920×1080 export bounds).

## Unverified assumptions
- The 29.868 s ELYSY timebase discrepancy cause is not yet proven; hypothesis: the tested LRC exports were produced after an `/api/offset` shift or from a different alignment session than the Premiere SRT. Needs a controlled reproduction before Phase 4 claims a fix.

## Immediate next action
- Phase 2 sign-off review (Codex round 3). Phase 2b preset packs, Phase 3 (Enhanced LRC) and Phase 4 (ELYSY bridge) remain out of scope until sign-off.

## Approaches not to repeat
- Do not rewrite cue timestamps in the preset (plan rule).
- Do not add song-specific hard-coded offsets (plan rule).
- `app-lyrics.js` is at its 400-line guard limit — new UI wiring must go in `app.js`/`app-ui.js`/`app-modes.js` (all under 400) or the guard test fails.
- QA scripts must use the `qa_scene.DevTools` API (`dev.call`/`dev.eval`) and the `qa_credit_crawl.py` Chrome-launch pattern (`--remote-allow-origins=*`, `?desktop=1`, `renderLyric` pump) — the earlier draft invented APIs and endpoints.

## Blockers
- None.
