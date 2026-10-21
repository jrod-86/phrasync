# PROJECT.md — KaraokeSesh Karaoke Credit Crawl

## Charter
Local development fork of Phrasync v0.4.5 (upstream https://github.com/jaydemks/phrasync, Apache-2.0) adding a "Karaoke Credit Crawl" lyric preset and the supporting timing/interchange work defined by the durable build plan.

## Durable plan and progress records (authoritative)
- Plan: `C:\AI\tools\karaoke-maker-project\00-master-index\03-active-plans-and-experiments\karaokesesh-karaoke-credit-crawl-build-plan.md`
- Progress: `C:\AI\tools\karaoke-maker-project\00-master-index\03-active-plans-and-experiments\karaokesesh-karaoke-credit-crawl-build-progress.md`

## Project boundary
- Sole write root: `C:\AI\tools\karaoke-maker-project\karaokesesh-karaoke-credit-crawl` (plus the two master-index plan/progress records and these checkpoint files).
- Branch `feature/karaoke-credit-crawl`, local only. Never push, publish, release, or install a packaged build.
- Do not modify/uninstall the Microsoft Store KaraokeSesh. Do not modify ELYSY installation code (file/API boundary only).
- No copyrighted audio or lyrics in tests or commits; synthetic fixtures only.
- Preserve Apache-2.0 LICENSE and NOTICE.

## Acceptance criteria (finished product)
1. Karaoke Credit Crawl preset behaves per plan acceptance tests 1–10 (milestone 1, verified).
2. Crawl controls (visible lines, transition duration, spacing, fade strength) work in preview AND export with parity tests (plan Phase 2).
3. 4K and small-screen layout behaviour verified (plan Phase 2).
4. Enhanced LRC `[mm:ss.xx]` line tags and `<mm:ss.xxx>` word tags import correctly without displaying tags; word timing stored separately; real word timestamps drive fills; parser tests cover malformed/missing/duplicated/offset data (plan Phase 3).
5. No song-specific hard-coded offsets anywhere; the existing global offset control remains the correction path (plan Phase 3).
6. ELYSY interchange boundary exists: a converter producing correct KaraokeSesh cue JSON from ELYSY export files (SRT / Enhanced LRC / JSON) with an explicit user-supplied offset option; license verified before any code reuse (plan Phase 4).
7. Full validation suite green: pytest, browser QA, MP4 export QA, syntax checks.

## Validation approach
- `.venv\Scripts\python.exe -m pytest` (full suite)
- `scripts\qa_credit_crawl.py` (headless Chrome browser QA vs `app.py --no-browser --port 5507`)
- `scripts\qa_credit_crawl_mp4.py` (real MP4 export + decode QA)
- `node --check` on static JS; `compileall` on Python
- Focused tests per phase before moving on.
