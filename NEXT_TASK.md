# NEXT_TASK.md

## Task: Phase 2 final sign-off review (Codex round 4)

**Status:** Codex round 3 returned two findings (hidden crawl controls on real dropdown selection; UI hydration disagreeing with renderer resolution). Both are remediated with regression tests and all acceptance checks are green (see TEST_RESULTS.md, 2026-10-13 round-3 section). Next action is the final review gate before any later phase.

**Objective:** Have Codex sign off the round-3 remediation commit (dropdown visibility via `updatePresetPresentation()`, UI hydration via `VFKinetic.resolvedPreset()`, extended `qa_crawl_controls.py`, new frontend regression test). Then Phase 2 is signed off.

**Relevant files:**
- `static/app.js` (`stylePreset` change handler → `updatePresetPresentation()`)
- `static/app-modes.js` (`crawlStyleFromControls` effective-value resolution, `applyCrawlControlsUI` hydration)
- `tests/test_frontend.py` (`test_style_preset_change_refreshes_crawl_controls`)
- `scripts/qa_crawl_controls.py` (real dropdown interaction + malformed reload hydration)
- `karaokesesh/kinetic.py` / `static/kinetic.js` (unchanged this round — renderer resolution and parity grid)

**Acceptance checks:**
1. Review round returns no open defects → Phase 2 signed off.
2. Full pytest green; `node --check` clean; all three crawl QA scripts PASS.

**Non-goals:** Phase 2b preset packs (TV/YouTube), Phase 3 Enhanced LRC, Phase 4 ELYSY bridge — all remain out of scope until Phase 2 sign-off.
