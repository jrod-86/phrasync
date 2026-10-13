# DECISIONS.md

| Decision | Reason | Date |
|---|---|---|
| Continue the existing fork; do not restart or reset Git | Verified clean tree at expected commit `647652c`; 177/177 tests; progress record matches source | 2026-10-12 |
| Treat plan "Later phases" (2, 3, 4) as the remaining scope | Milestone 1 + both Codex remediation rounds are complete and signed off in the progress record; the plan's gate ("no Enhanced LRC/ELYSY until Codex reviews milestone 1") is satisfied | 2026-10-12 |
| Crawl controls live in `style.crawl` (per-project dict), merged over the preset defaults at resolve time | Keeps preset definitions immutable (existing presets unchanged), serializes with the project, and both engines resolve through the same `resolved_preset`/`resolvedPreset` path so parity is automatic | 2026-10-12 |
| UI wiring goes in `app.js`/`app-ui.js`/`app-modes.js`, not `app-lyrics.js` | `app-lyrics.js` is at its 400-line guard limit in `tests/test_frontend.py` | 2026-10-12 |
| ELYSY bridge = file-boundary converter script in `scripts/`, no ELYSY code copied | ELYSY is MIT-licensed (verified) but the plan prefers a file/API boundary; a converter keeps the fork independent of ELYSY internals | 2026-10-12 |
| No song-specific offset workarounds anywhere in the fork | Explicit plan rule (Phase 3); the existing global offset control is the correction path | 2026-10-12 |
| Checkpoint files committed with the feature work | They are the durable recovery mechanism for this fork and contain no copyrighted material | 2026-10-12 |
