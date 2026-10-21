# KaraokeSesh: Build Notes

## Included in this package

- FastAPI local backend
- Responsive HTML/CSS/JavaScript editor
- Live audio-synchronised, word-level kinetic preview
- Shared kinetic engine: `static/kinetic.js` and `karaokesesh/kinetic.py`
- Local audio analysis: `karaokesesh/audio_analysis.py` (spectral-flux onsets, tempo, waveform)
- Lyric-to-music alignment: `karaokesesh/align.py` (latency estimation, onset snapping, scoring)
- Canvas timeline with waveform, onsets, beat grid, and draggable phrase/word lanes
- Image/video asset upload and management
- Dynamic preview visuals and matching offline render visuals
- RapidOCR integration
- Faster-Whisper integration with breath-aware phrase segmentation
- Subtitle import/export and editable cue list
- Separate Lyric Video and Subtitles workflows, including video-as-transcription-source
- Grounded WebGL typography with seven dedicated 3D presentations
- Odyssey weather, daytime, season, and deterministic automatic journey controls
- Quality critic/preflight system, including an alignment score
- Background render jobs, progress, cancellation, and MP4 download
- Windows, Linux, and macOS launch/install scripts
- Automated tests, cross-engine parity test, `scripts/qa_sync.py`, and a PyInstaller helper
- Original visual reference bundled in `assets/style_reference.png`

## Verification performed

The automated test suite was run successfully in the delivery environment: **52 tests passed**. This includes hierarchical language mapping, per-span and per-phrase decoding, restricted and fixed language modes, Japanese cue composition, the transcription gauntlet, alignment-boundary regressions, real FFmpeg and WebGL render tests, a video-source subtitle export, JavaScript/Python kinetic parity, English-copy coverage, and a Chrome 3D/environment matrix with zero captured browser exceptions. Windows is physically tested; Linux and macOS launchers remain source-level cross-platform support rather than separately signed native installers.

## Architecture notes

- The kinetic engine is duplicated on purpose, once per language, because the
  preview must run in the browser and the export must run in Python. The two are
  kept honest by `tests/test_kinetic.py`, which evaluates the JavaScript in Node
  and asserts field-by-field equality with the Python implementation across
  every preset, several cues, and a grid of timestamps and beat values. Any
  change to one file must be mirrored in the other or that test fails.
- Audio analysis caches its result per file in `~/.karaokesesh/analysis`, keyed by
  name, size, mtime, and analysis version. A four-minute song analyses in about
  1.5 seconds on CPU.
- Alignment never invents words: it only shifts existing word timings, keeps them
  monotonic, and enforces a minimum word duration.
- Auto builds a language map from ten-second windows, smooths the sequence,
  snaps switches near quiet boundaries, decodes each span with a fixed language,
  checks each phrase, and selectively re-reads disagreements. A single language
  code bypasses mapping; a comma-separated list restricts its candidates. Every
  path explicitly requests transcription rather than translation.

## Practical limitations

- Automatic transcription of singing can mishear words. Auto-align fixes the
  timing, not the wording.
- Onset detection follows sung consonants, so heavily reverbed or legato vocals
  give a weaker signal and a lower sync score.
- Tempo detection can land on double or half time; the beat grid is a snapping
  aid, not ground truth.
- OCR quality depends on image sharpness, contrast, font shape, and language.
- Browser preview and offline MP4 rendering use separate rendering implementations; their composition is designed to match closely but can differ slightly in font metrics and effects.
- Uploaded custom fonts may render differently across operating systems.
- Large-v3 Whisper can be slow or memory-heavy on CPU-only systems.
- Final export speed scales with resolution, FPS, effects, song duration, and hardware.

## Suggested next production steps

- Build and smoke-test native portable folders separately on Windows, macOS, and Linux.
- Add GPU-specific Faster-Whisper installation profiles.
- Add template save/share and batch rendering.
- Add signed installers and automatic updates for public distribution.
