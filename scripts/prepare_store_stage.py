"""Populate an already staged portable build with the Store manifest and tiles.

The stage must contain KaraokeSesh.exe and _internal. It is not signed or installed;
Partner Center signs and distributes the package after certification.
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from PIL import Image, ImageOps


ROOT = Path(__file__).resolve().parent.parent
TILES = {
    "StoreLogo.png": (50, 50),
    "Square44x44Logo.png": (44, 44),
    "Square44x44Logo.targetsize-24_altform-unplated.png": (24, 24),
    "Square71x71Logo.png": (71, 71),
    "Square150x150Logo.png": (150, 150),
    "Square310x310Logo.png": (310, 310),
    "Wide310x150Logo.png": (310, 150),
}


def prepare(stage: Path) -> None:
    if not (stage / "KaraokeSesh.exe").is_file() or not (stage / "_internal").is_dir():
        raise ValueError("The stage must already contain the portable KaraokeSesh build")
    assets = stage / "Assets"
    assets.mkdir(exist_ok=True)
    with Image.open(ROOT / "assets" / "KaraokeSesh.png") as source:
        source = source.convert("RGBA")
        for name, (width, height) in TILES.items():
            tile = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            side = min(width, height)
            icon = ImageOps.fit(source, (side, side), method=Image.Resampling.LANCZOS)
            tile.alpha_composite(icon, ((width - side) // 2, (height - side) // 2))
            tile.save(assets / name, optimize=True)
    shutil.copyfile(ROOT / "packaging" / "AppxManifest.xml", stage / "AppxManifest.xml")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("stage", type=Path)
    args = parser.parse_args()
    prepare(args.stage.resolve())
