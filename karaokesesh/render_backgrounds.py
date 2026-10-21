from __future__ import annotations

import math
from typing import Any

import numpy as np
from PIL import Image, ImageDraw

from .render_utils import clamp, hex_color


ODYSSEY_THEMES = {
    "japan": {
        "sky": ((18, 10, 30), (58, 17, 64), (125, 31, 77)),
        "ground": (10, 6, 17), "accent": (255, 61, 110), "light": (255, 233, 201),
    },
    "italy": {
        "sky": ((15, 18, 36), (61, 36, 64), (197, 106, 62)),
        "ground": (11, 10, 18), "accent": (255, 183, 101), "light": (255, 234, 203),
    },
    "china": {
        "sky": ((18, 6, 26), (74, 15, 44), (184, 33, 60)),
        "ground": (10, 5, 16), "accent": (255, 45, 79), "light": (255, 240, 212),
    },
    "usa": {
        "sky": ((6, 10, 24), (19, 42, 74), (47, 111, 143)),
        "ground": (7, 9, 16), "accent": (77, 226, 255), "light": (232, 251, 255),
    },
}


class DynamicBackground:
    def __init__(self, width: int, height: int, style: dict[str, Any], visual: str):
        max_side = 640
        ratio = min(1.0, max_side / max(width, height))
        self.low_width = max(240, int(round(width * ratio)))
        self.low_height = max(240, int(round(height * ratio)))
        self.width = width
        self.height = height
        self.style = style
        self.visual = visual
        self.primary = np.array(hex_color(style.get("backgroundColor"), (8, 8, 18)), dtype=np.float32)
        self.accent = np.array(hex_color(style.get("accentColor"), (223, 92, 255)), dtype=np.float32)
        self.secondary = np.array(hex_color(style.get("secondaryColor"), (92, 215, 255)), dtype=np.float32)
        y, x = np.mgrid[0 : self.low_height, 0 : self.low_width]
        self.x = x.astype(np.float32) / max(1, self.low_width - 1)
        self.y = y.astype(np.float32) / max(1, self.low_height - 1)
        rng = np.random.default_rng(6127)
        count = max(40, int((self.low_width * self.low_height) / 9000))
        self.particles = np.column_stack(
            (
                rng.random(count),
                rng.random(count),
                rng.uniform(0.15, 0.65, count),
                rng.uniform(0.5, 2.2, count),
            )
        )

    @staticmethod
    def _mix_color(a: tuple[int, int, int], b: tuple[int, int, int], amount: float) -> tuple[int, int, int]:
        amount = clamp(amount)
        return tuple(int(a[i] * (1 - amount) + b[i] * amount) for i in range(3))

    def _odyssey_frame(self, t: float, pulse: float) -> Image.Image:
        """CPU export counterpart for the browser's Odyssey scene.

        The browser uses WebGL for its richest preview. Export deliberately uses
        simple deterministic perspective geometry so the same project remains
        renderable on machines where headless WebGL is unavailable.
        """
        theme = ODYSSEY_THEMES.get(str(self.style.get("sceneKit", "japan")), ODYSSEY_THEMES["japan"])
        sky_top, sky_mid, sky_horizon = theme["sky"]
        daytime = str(self.style.get("daytime", "sunset"))
        season = str(self.style.get("season", "summer"))
        if daytime == "night":
            sky_top = self._mix_color(sky_top, (2, 4, 14), 0.58)
            sky_mid = self._mix_color(sky_mid, (8, 12, 30), 0.48)
        elif daytime == "day":
            sky_top = self._mix_color(sky_top, (64, 130, 188), 0.58)
            sky_mid = self._mix_color(sky_mid, (120, 174, 214), 0.42)
        elif daytime == "dawn":
            sky_horizon = self._mix_color(sky_horizon, (255, 151, 128), 0.45)
        if season == "winter":
            sky_mid = self._mix_color(sky_mid, (145, 176, 205), 0.22)
        elif season == "autumn":
            sky_horizon = self._mix_color(sky_horizon, (218, 89, 40), 0.25)

        w, h = self.low_width, self.low_height
        horizon = int(h * 0.50)
        arr = np.empty((h, w, 3), dtype=np.uint8)
        for y in range(horizon):
            p = y / max(1, horizon - 1)
            if p < 0.62:
                q = p / 0.62
                color = self._mix_color(sky_top, sky_mid, q)
            else:
                q = (p - 0.62) / 0.38
                color = self._mix_color(sky_mid, sky_horizon, q)
            arr[y, :, :] = color
        for y in range(horizon, h):
            p = (y - horizon) / max(1, h - horizon - 1)
            arr[y, :, :] = self._mix_color(theme["ground"], theme["accent"], 0.05 + p * 0.22)
        image = Image.fromarray(arr, "RGB")
        draw = ImageDraw.Draw(image, "RGBA")

        accent = theme["accent"]
        light = theme["light"]
        # Stable stars and a celestial body.
        if daytime in {"night", "sunset"}:
            rng = np.random.default_rng(9001)
            for x, y, radius, alpha in zip(rng.random(70), rng.random(70), rng.random(70), rng.random(70)):
                r = 1 + int(radius * 1.4)
                draw.ellipse((x * w, y * horizon * 0.9, x * w + r, y * horizon * 0.9 + r), fill=(*light, int(45 + alpha * 130)))
        body_x = 0.74 if self.style.get("sceneKit", "japan") in {"japan", "usa"} else 0.25
        body_r = max(8, int(h * 0.055))
        body_y = int(horizon * 0.30)
        draw.ellipse((body_x * w - body_r, body_y - body_r, body_x * w + body_r, body_y + body_r), fill=(*light, 225))

        # Moving perspective floor. The quadratic spacing is the same visual
        # cue used by the browser corridor and remains continuous at loop points.
        speed = 9 * float(self.style.get("sceneSpeed", 1) or 1)
        direction = str(self.style.get("sceneDirection", "forward"))
        sway = math.sin(t * 0.24) * (0.06 if direction == "drift" else 0.1 if direction == "bank" else 0)
        vanishing_x = w * (0.5 - sway)
        phase = (t * speed * 0.018) % 1
        for lane in range(-7, 8):
            bottom_x = vanishing_x + lane * w / 7
            draw.line((vanishing_x, horizon, bottom_x, h), fill=(*accent, 75), width=max(1, w // 700))
        for row in range(22):
            z = (row + phase) / 22
            y = horizon + int((z * z) * (h - horizon))
            draw.line((0, y, w, y), fill=(*accent, int(30 + z * 120)), width=max(1, h // 700))

        density = max(0.25, float(self.style.get("sceneDensity", 1) or 1))
        seed = int(self.style.get("sceneSeed", 1337) or 1337)
        travel = t * speed
        # Silhouetted roadside structures, deterministic by world slot.
        first_slot = int(math.floor(travel / 7))
        for slot in range(first_slot + 18, first_slot - 1, -1):
            local_z = slot * 7 - travel + 2
            if local_z <= 1 or local_z > 132:
                continue
            rng = np.random.default_rng((slot * 2654435761 + seed) & 0xFFFFFFFF)
            if rng.random() > min(0.95, 0.42 + density * 0.34):
                continue
            side = -1 if rng.random() < 0.5 else 1
            depth = clamp(1 - local_z / 132)
            scale = (h * 0.72) / local_z * (0.65 + rng.random() * 1.25)
            x = vanishing_x + side * (w * 0.06 + w * 0.46 * depth)
            base_y = horizon + (depth ** 1.8) * (h - horizon)
            prop_w = max(1, scale * (0.9 + rng.random() * 1.4))
            prop_h = max(2, scale * (2.0 + rng.random() * 2.8))
            fog = 0.25 + depth * 0.75
            structure = self._mix_color(sky_mid, accent, 0.18 + 0.45 * depth)
            alpha = int(210 * fog)
            if rng.random() < 0.45:
                draw.rectangle((x - prop_w / 2, base_y - prop_h, x + prop_w / 2, base_y), fill=(*structure, alpha))
                draw.rectangle((x - prop_w * 0.7, base_y - prop_h, x + prop_w * 0.7, base_y - prop_h * 0.88), fill=(*accent, alpha))
            else:
                draw.polygon(((x, base_y - prop_h), (x - prop_w, base_y), (x + prop_w, base_y)), fill=(*structure, alpha))
            if rng.random() < 0.55:
                r = max(1, prop_w * (0.12 + pulse * 0.05))
                draw.ellipse((x - r, base_y - prop_h * 0.65 - r, x + r, base_y - prop_h * 0.65 + r), fill=(*light, alpha))

        weather = str(self.style.get("weather", "clear"))
        rng = np.random.default_rng(int(t * 30) + seed)
        if weather in {"rain", "storm"}:
            for _ in range(100 if weather == "storm" else 65):
                x, y = rng.random() * w, rng.random() * h
                draw.line((x, y, x - w * 0.009, y + h * 0.035), fill=(180, 220, 255, 80), width=1)
        elif weather == "snow":
            for _ in range(75):
                x, y = rng.random() * w, rng.random() * h
                r = 1 + rng.random() * 2
                draw.ellipse((x - r, y - r, x + r, y + r), fill=(245, 250, 255, 135))
        elif weather == "fog":
            fog = Image.new("RGBA", (w, h), (185, 195, 215, 0))
            fog.putalpha(Image.new("L", (w, h), 54))
            image = Image.alpha_composite(image.convert("RGBA"), fog).convert("RGB")

        # Edge vignette for lyric readability.
        vignette = np.ones((h, w), dtype=np.float32)
        yy, xx = np.mgrid[0:h, 0:w]
        radial = ((xx / max(1, w) - 0.5) ** 2 + (yy / max(1, h) - 0.5) ** 2)
        vignette = np.clip(1 - radial * 1.25, 0.48, 1.0)
        pixels = np.asarray(image, dtype=np.float32) * vignette[..., None]
        return Image.fromarray(np.clip(pixels, 0, 255).astype(np.uint8), "RGB")

    def _aurora_array(self, t: float, intensity: float, pulse: float = 0.0) -> np.ndarray:
        base = np.zeros((self.low_height, self.low_width, 3), dtype=np.float32)
        base[:] = self.primary
        # The beat swells the blobs, which is what makes the field feel scored
        # to the track rather than idly drifting.
        swell = 1.0 + 0.26 * pulse
        centers = [
            (0.18 + 0.13 * math.sin(t * 0.31), 0.24 + 0.19 * math.cos(t * 0.23), self.accent, 0.26, 0.95),
            (0.79 + 0.14 * math.cos(t * 0.27), 0.40 + 0.17 * math.sin(t * 0.19), self.secondary, 0.32, 0.82),
            (0.48 + 0.21 * math.sin(t * 0.17), 0.82 + 0.11 * math.cos(t * 0.29), self.accent, 0.36, 0.72),
            (0.62 + 0.17 * math.cos(t * 0.21), 0.16 + 0.12 * math.sin(t * 0.25), self.secondary, 0.24, 0.58),
        ]
        for cx, cy, color, sigma, strength in centers:
            distance = ((self.x - cx) ** 2 + (self.y - cy) ** 2) / max(0.01, sigma * swell)
            glow = np.exp(-distance * 3.2)[..., None]
            # Blend toward the colour rather than adding to it: additive light
            # washes overlapping blobs out to pastel and kills lyric contrast.
            weight = np.clip(glow * strength * (0.34 + intensity * 0.42) * (1.0 + 0.18 * pulse), 0, 1)
            base = base * (1.0 - weight) + color * weight
            base += (glow**3) * color * 0.18 * intensity
        vignette = 1.0 - 0.46 * ((self.x - 0.5) ** 2 + (self.y - 0.5) ** 2)
        base *= np.clip(vignette[..., None], 0.58, 1.0)
        return np.clip(base, 0, 255).astype(np.uint8)

    def render(
        self, t: float, amplitude: float, frame_index: int, pulse: float = 0.0
    ) -> Image.Image:
        intensity = float(self.style.get("visualIntensity", 0.9))
        pulse = max(pulse, amplitude * 0.8)
        if self.visual in {"scene", "scene3d"}:
            image = self._odyssey_frame(t, pulse)
        elif self.visual == "particles":
            arr = self._aurora_array(t * 0.4, intensity * 0.6, pulse)
            image = Image.fromarray(arr, "RGB")
            draw = ImageDraw.Draw(image, "RGBA")
            for px, py, speed, radius in self.particles:
                x = int(((px + t * speed * 0.018) % 1.05) * self.low_width)
                y = int(((py - t * speed * 0.012) % 1.05) * self.low_height)
                r = radius * (0.9 + amplitude * 1.8 + pulse * 0.7)
                color = tuple(int(v) for v in self.accent) + (int(120 + amplitude * 120),)
                draw.ellipse((x - r, y - r, x + r, y + r), fill=color)
        elif self.visual == "grid":
            arr = self._aurora_array(t * 0.18, intensity * 0.45, pulse)
            image = Image.fromarray(arr, "RGB")
            draw = ImageDraw.Draw(image, "RGBA")
            horizon = int(self.low_height * 0.58)
            color = tuple(int(v) for v in self.accent) + (int(min(255, 150 + pulse * 80)),)
            center = self.low_width / 2
            for i in range(-12, 13):
                bottom_x = center + i * self.low_width / 12
                draw.line((center, horizon, bottom_x, self.low_height), fill=color, width=1)
            phase = (t * 0.55) % 1.0
            for row in range(18):
                z = (row + phase) / 18
                y = horizon + int((z**2) * (self.low_height - horizon))
                alpha = int(50 + z * 150)
                draw.line((0, y, self.low_width, y), fill=(*color[:3], alpha), width=1)
        else:
            arr = self._aurora_array(t, intensity, pulse)
            image = Image.fromarray(arr, "RGB")
            if self.visual == "equalizer":
                draw = ImageDraw.Draw(image, "RGBA")
                bars = 36
                gap = max(2, self.low_width // 240)
                bar_width = max(2, (self.low_width - gap * (bars - 1)) // bars)
                total_width = bars * bar_width + (bars - 1) * gap
                x0 = (self.low_width - total_width) // 2
                base_y = int(self.low_height * 0.90)
                for index in range(bars):
                    wave = 0.32 + 0.68 * abs(math.sin(index * 0.63 + t * 3.1))
                    value = clamp((amplitude * 1.1 + wave * 0.26) * (1 + pulse * 0.22))
                    height = int((self.low_height * 0.32) * value)
                    alpha = int(110 + value * 145)
                    color = tuple(int(v) for v in (self.accent * (0.6 + 0.4 * index / bars))) + (alpha,)
                    x = x0 + index * (bar_width + gap)
                    draw.rounded_rectangle((x, base_y - height, x + bar_width, base_y), radius=bar_width // 2, fill=color)

        # Low-cost film grain at the generator resolution.
        grain_amount = float(self.style.get("grain", 0.14))
        if grain_amount > 0:
            rng = np.random.default_rng(frame_index + 113)
            noise = rng.normal(128, 26, (self.low_height, self.low_width)).clip(0, 255).astype(np.uint8)
            noise_image = Image.fromarray(noise, "L").convert("RGB")
            image = Image.blend(image, noise_image, clamp(grain_amount * 0.18, 0, 0.12))
        if image.size != (self.width, self.height):
            image = image.resize((self.width, self.height), Image.Resampling.BILINEAR)
        return image
