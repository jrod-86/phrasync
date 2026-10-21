from __future__ import annotations

import os
import argparse
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
separator = ";" if os.name == "nt" else ":"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, help="Build a separate local candidate without replacing the previous release")
    args = parser.parse_args()
    command = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name",
        "KaraokeSesh",
        "--windowed",
        "--icon",
        str(ROOT / "assets" / "KaraokeSesh.ico"),
        "--add-data",
        f"{ROOT / 'static'}{separator}static",
        "--add-data",
        f"{ROOT / 'assets'}{separator}assets",
        "--add-data",
        f"{ROOT / 'LICENSE'}{separator}.",
        "--add-data",
        f"{ROOT / 'NOTICE'}{separator}.",
        "--add-data",
        f"{ROOT / 'THIRD_PARTY_NOTICES.md'}{separator}.",
        "--collect-all",
        "imageio_ffmpeg",
        "--collect-all",
        "faster_whisper",
        "--collect-all",
        "rapidocr_onnxruntime",
        "--collect-all",
        "webview",
        "--collect-all",
        "winrt",
        "--collect-binaries",
        "nvidia.cublas",
        "--collect-binaries",
        "nvidia.cudnn",
        "--hidden-import",
        "uvicorn.logging",
        "--hidden-import",
        "uvicorn.loops.auto",
        "--hidden-import",
        "uvicorn.protocols.http.auto",
        "--hidden-import",
        "uvicorn.protocols.websockets.auto",
        "--hidden-import",
        "webview.platforms.edgechromium",
        "--hidden-import",
        "webview.platforms.winforms",
        str(ROOT / "app.py"),
    ]
    if args.out:
        output = args.out.resolve()
        command.extend(["--distpath", str(output / "dist"), "--workpath", str(output / "build"),
                        "--specpath", str(output / "spec")])
    print("Building a portable folder for the current operating system…")
    subprocess.run(command, cwd=ROOT, check=True)
    print(f"Done: {(args.out.resolve() / 'dist' if args.out else ROOT / 'dist') / 'KaraokeSesh'}")
    print("Build separately on Windows, macOS and Linux for native binaries on each platform.")


if __name__ == "__main__":
    main()
