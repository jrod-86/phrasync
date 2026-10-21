# Third-party notices

KaraokeSesh is licensed under Apache-2.0. Its dependencies and tools remain under their respective licenses; the KaraokeSesh license does not replace those terms. See `NOTICE` for the project's attribution notice.

## FFmpeg

KaraokeSesh uses FFmpeg for media probing, decoding, audio conversion, and H.264 export. It prefers a system FFmpeg executable and otherwise uses the binary supplied by `imageio-ffmpeg`.

The Windows development environment used for version 0.1.0 had `imageio-ffmpeg` 0.6.0 and an FFmpeg 7.1 binary configured with GPL/version-3 options and libx264. That exact binary is therefore GPL-covered. Other operating systems or future package versions may supply a different build; inspect the actual binary with `ffmpeg -version` before distributing it.

- FFmpeg license and compliance information: <https://ffmpeg.org/legal.html>
- FFmpeg source: <https://ffmpeg.org/download.html#get-sources>
- imageio-ffmpeg: <https://github.com/imageio/imageio-ffmpeg>
- x264: <https://www.videolan.org/developers/x264.html>

When shipping a portable build, preserve applicable copyright and license notices, document the exact FFmpeg build, and provide the corresponding source or written/source-access mechanism required by that build's license. Do not describe the whole bundle as if every component were licensed only under Apache-2.0.

## Python and browser-side dependencies

The Python requirements include FastAPI, Uvicorn, NumPy, Pillow, Faster-Whisper/CTranslate2, Hugging Face Hub, audio-analysis packages, OCR packages, and their transitive dependencies. Browser-side code in this repository is project code unless a file says otherwise. Consult the installed package metadata and upstream projects for the exact versions and license texts included in a release.

Before publishing a binary release, generate a version-pinned dependency inventory and include the required notices with the artifact. This file is a release checklist and attribution summary, not legal advice.

## three.js

Bundled at `static/vendor/three.module.min.js` (version 0.169.0), used by the
Odyssey 3D background. Copyright 2010-2024 three.js authors, MIT License.
Upstream: https://github.com/mrdoob/three.js
Full license: `static/vendor/THREE-LICENSE.txt` (upstream tag r169).

Lost in the Ocean uses locally implemented procedural shaders and the bundled
Three.js engine. No reference photograph, external shader pack, paid texture,
or remotely hosted asset is included by this feature.

## Noto Sans JP

The Japanese MP4-export fallback font at `assets/NotoSansJP-VF.ttf` is Noto Sans JP
from the [Google Fonts repository](https://github.com/google/fonts/tree/main/ofl/notosansjp),
licensed under the SIL Open Font License 1.1. Its copyright notice and complete
license are included in `assets/NotoSansJP-OFL.txt` and bundled with the app.
