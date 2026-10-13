# PROJECT_PLAN.md — milestones and states

| # | Milestone | State | Evidence |
|---|-----------|-------|----------|
| 1 | Clone, identity, baseline tests (168 passed) | complete | Progress record Phases 1–2; TEST_RESULTS.md historical entry |
| 2 | Architecture inspection (dual-engine parity model) | complete | Progress record Phase 3 |
| 3 | Milestone 1: credit-crawl preset, preview+export, tests, QA | complete | Progress record Phases 4–7; commit `5dc7b81`; acceptance tests 1–10 verified |
| 4 | Codex review round 1 remediation (viewport bounds, phrase-only fill, single active cue) | complete | Progress record Phase 8; commit `0827a2f`; 175 tests + QA PASS |
| 5 | Codex review round 2 remediation (monotonic anchor, strict word timing, realistic 1080p QA) | complete | Progress record Phase 9; commit `647652c`; 177 tests + QA PASS |
| 6 | Phase 2: crawl controls (lines, transition, gap, fade) in both engines + UI + parity tests | in progress | this session |
| 7 | Phase 2b: 4K + small-screen layout verification | not started | — |
| 8 | Phase 3: Enhanced LRC ingestion (line + word tags, no visible tags, word timing stored separately, parser fixtures) | not started | — |
| 9 | Phase 4: ELYSY bridge (license verified MIT; file-boundary converter; timebase diagnosis note) | not started | — |
| 10 | Final validation: full suite, browser QA, MP4 QA, syntax checks, commit, checkpoint audit | not started | — |

Gate from plan: "Do not start Enhanced LRC or ELYSY integration until Codex has reviewed this first milestone." — SATISFIED: two Codex review rounds completed and remediated (commits `0827a2f`, `647652c`); milestone 1 signed off in the progress record.
