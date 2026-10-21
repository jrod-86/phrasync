# TEST_RESULTS.md

## 2026-10-12 — this session (continuation run)
| Check | Command | Result |
|---|---|---|
| Full suite | `.venv\Scripts\python.exe -m pytest` | **177 passed, 0 failed** (16.38s; 2 pre-existing warnings: StarletteDeprecationWarning, SyntaxWarning `\k` in test_background_processes.py) |
| Git state | `git status` / `git log` | clean tree, `feature/karaoke-credit-crawl`, HEAD `647652c` = expected |

## Historical (from durable progress record, verified against source this session)
| Phase | Check | Result |
|---|---|---|
| 2 | baseline suite after installing `requirements-ai.txt` | 168 passed |
| 8 | full suite after Codex round 1 | 175 passed |
| 8 | `scripts\qa_credit_crawl.py` (headless Chrome vs port 5507) | PASS |
| 8 | `scripts\qa_credit_crawl_mp4.py` | PASS |
| 9 | full suite after Codex round 2 | 177 passed |
| 9 | browser QA incl. realistic 1080p bounds section | PASS |
| 9 | MP4 QA incl. realistic 1920×1080 export bounds section | PASS |
| 9 | `node --check` all static JS; `compileall` karaokesesh/scripts/tests/app.py | clean |

## Phase 2 (crawl controls) — this session
| Check | Command | Result |
|---|---|---|
| Full suite | `.venv\Scripts\python.exe -m pytest` | **180 passed, 0 failed** (19.27s; same 2 pre-existing warnings) |
| Kinetic parity incl. new override tests | `.venv\Scripts\python.exe -m pytest tests/test_kinetic.py` | 12 passed |
| Crawl-controls browser QA | `.venv\Scripts\python.exe scripts\qa_crawl_controls.py --origin http://127.0.0.1:5507` | **PASS** (visibility toggle, live slider tuning, preview/export override parity, save/reload persistence, malformed fallback) |
| Credit-crawl browser QA (regression) | `.venv\Scripts\python.exe scripts\qa_credit_crawl.py --origin http://127.0.0.1:5507` | **PASS** (preview stack, roll, seek, wrap, gap, save/reload, export parity, realistic 1080p bounds) |
| Credit-crawl MP4 export QA (regression) | `.venv\Scripts\python.exe scripts\qa_credit_crawl_mp4.py` | **PASS** (640×360 + realistic 1920×1080 renders) |
| Static JS syntax | `node --check` on every `static/*.js` (absolute paths) | clean |
| Python syntax | `.venv\Scripts\python.exe -m compileall -q karaokesesh scripts tests app.py` | clean |

## Codex round-3 remediation — this session
| Check | Command | Result |
|---|---|---|
| Full suite | `.venv\Scripts\python.exe -m pytest` | **181 passed, 0 failed** (16.38s; same 2 pre-existing warnings) |
| Finding 1 regression test | `tests/test_frontend.py::test_style_preset_change_refreshes_crawl_controls` | passed |
| Crawl-controls browser QA | `.venv\Scripts\python.exe scripts\qa_crawl_controls.py --origin http://127.0.0.1:5507` | **PASS** (real dropdown select/change visibility + saved-value restore, live tuning, preview/export parity, save/reload, malformed reload hydration) |
| Credit-crawl browser QA (regression) | `.venv\Scripts\python.exe scripts\qa_credit_crawl.py --origin http://127.0.0.1:5507` | **PASS** (preview stack, roll, seek, wrap, gap, save/reload, export parity, realistic 1080p bounds) |
| Credit-crawl MP4 export QA (regression) | `.venv\Scripts\python.exe scripts\qa_credit_crawl_mp4.py` | **PASS** (640×360 + realistic 1920×1080 renders) |
| Static JS syntax | `node --check` on `static/app.js`, `static/app-modes.js`, `static/kinetic.js` | clean |
| Python syntax | `py_compile` on `tests/test_frontend.py`, `scripts/qa_crawl_controls.py`; `compileall` karaokesesh/scripts/tests/app.py | clean |
| Whitespace | `git diff --check` | clean |
