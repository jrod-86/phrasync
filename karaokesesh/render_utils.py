from __future__ import annotations

from PIL import Image, ImageOps


def clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def hex_color(value: str | None, fallback: tuple[int, int, int]) -> tuple[int, int, int]:
    raw = str(value or "").strip().lstrip("#")
    if len(raw) == 3:
        raw = "".join(char * 2 for char in raw)
    if len(raw) != 6:
        return fallback
    try:
        return tuple(int(raw[index : index + 2], 16) for index in (0, 2, 4))  # type: ignore[return-value]
    except ValueError:
        return fallback


def cover(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def apply_dim(image: Image.Image, amount: float) -> Image.Image:
    amount = clamp(amount)
    if amount <= 0:
        return image
    overlay = Image.new("RGB", image.size, (0, 0, 0))
    return Image.blend(image, overlay, amount)


def scale_for_canvas(value: float, height: int, width: int | None = None) -> float:
    """Scale a design value expressed at 1080p onto this canvas.

    The reference is the SHORT edge, not the height. Keying type size to height
    made a 9:16 frame inflate 160px to about 285px across a 1080-wide canvas, so
    a portrait export fitted roughly seven characters per line.
    """
    reference = min(height, width) if width else height
    return value * reference / 1080.0
