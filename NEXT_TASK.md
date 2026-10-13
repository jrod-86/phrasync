# NEXT_TASK.md

## Task: Phase 2 sign-off review (Codex round 3)

**Status:** Phase 2 (crawl controls) implementation is complete and all acceptance checks are green (see TEST_RESULTS.md, 2026-10-13). Next action is the review gate before any later phase.

**Objective:** Have Codex review the crawl-controls diff (override merge, clamps, UI wiring, parity tests, qa_crawl_controls.py) the same way rounds 1–2 reviewed milestone 1. Remediate findings, then sign off milestone #6.

**Relevant files:**
- `phrasync/kinetic.py` (`CRAWL_LIMITS`, `CRAWL_NUMERIC_RE`, `merge_crawl_overrides`, `resolved_preset`)
- `static/kinetic.js` (mirror: `CRAWL_LIMITS`, `CRAWL_NUMERIC_RE`, `mergeCrawlOverrides`, `resolvedPreset`)
- `static/app-modes.js`, `static/index.html`, `static/app.js` (crawl controls UI)
- `tests/test_kinetic.py` (override + parity grid)
- `scripts/qa_crawl_controls.py` (browser QA)

**Acceptance checks:**
1. Review round returns no open defects (or defects get remediated with tests).
2. Full pytest green; `node --check` clean; all three crawl QA scripts PASS.

**Non-goals:** Phase 2b preset packs (TV/YouTube), Phase 3 Enhanced LRC, Phase 4 ELYSY bridge — all remain out of scope until Phase 2 sign-off.
