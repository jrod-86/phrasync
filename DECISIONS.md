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
| Preserve the previous agent's uncommitted round-3 remediation instead of re-implementing it | Working tree at required starting commit `eed85c3` already contained reviewed, coherent fixes for both Codex findings; re-implementing would risk divergence and wasted work | 2026-10-13 |
| Preset-change UI refresh routes through `updatePresetPresentation()`; crawl UI hydration routes through `VFKinetic.resolvedPreset()` | One UI-refresh path and one crawl-resolution path — no duplicated state or third parser (Codex round-3 findings 1 and 2) | 2026-10-13 |
