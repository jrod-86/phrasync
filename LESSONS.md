# LESSONS.md

| Lesson | Scope | Evidence | Verified | Date |
|---|---|---|---|---|
| Any kinetic preset change must land in BOTH `karaokesesh/kinetic.py` and `static/kinetic.js`; `tests/test_kinetic.py` diffs Python vs Node-JS field-by-field | this fork | progress record Phase 3; parity test grid | yes | 2026-10-12 |
| `tests/test_frontend.py` enforces a 400-line limit per static JS fragment (450 for i18n.js) and single ordered script tags in index.html — new UI code must go where there is headroom | this fork | guard test source; app-lyrics.js at 400 lines | yes | 2026-10-12 |
| Browser QA needs 1920×1080 window + fontSize 100 so DOM wrap == engine char budget; `--lyric-size` floors at 18px on small stages | QA scripts | progress record Phase 7 pitfall | yes | 2026-10-12 |
| At 1080p the shared glow bridges cue gaps; glyph band separation needs frac 0.5 and neighbour checks must be glow-robust (ink above/below anchor), not band-count-based | MP4 QA | progress record Phase 9 pitfall | yes | 2026-10-12 |
| `node --check` on this Windows shell needs absolute paths (relative paths hit a stdin quirk) | tooling | progress record Phase 9 | yes | 2026-10-12 |
| ELYSY's four export formats (standard LRC, enhanced LRC, SRT, enhanced SRT) all derive from the same aligned `words[0]["start"]`; its frontend offset control defaults to 0.5 s and `/api/offset` mutates session data — export formatters are not the source of the 29.868 s discrepancy | ELYSY bridge | direct read of `C:/AI/ELYSY/ELYSY-1.1.0/backend/lrc_generator.py` + `frontend/index.html` | yes (code read); root cause still unproven | 2026-10-12 |
| Cue elements in the preview DOM carry no id; correlate DOM cues to engine cues by normalized `.lw-base` text | QA scripts | progress record Phase 9 | yes | 2026-10-12 |
| Python `float()` and JS `Number()` disagree on numeric strings (`"1_000"` ok in Python, `"0x10"` ok in JS, `Number([])`==0); shared override code must pin both to one grammar (decimal regex) or parity silently diverges | this fork | CRAWL_NUMERIC_RE in kinetic.py/kinetic.js + `tricky` parity test case | yes | 2026-10-13 |
| `qa_scene.DevTools` exposes `dev.call`/`dev.eval` only (no context manager, no `send`/`last_response`); Chrome must launch with `--remote-allow-origins=*` for the websocket connect, and crawl QA must pump `renderLyric(true)` after setting `virtualTime` | QA scripts | qa_crawl_controls.py rewrite, PASS | yes | 2026-10-13 |
