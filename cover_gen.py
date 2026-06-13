from __future__ import annotations

import colorsys
import hashlib
import logging
import os
import uuid
from pathlib import Path

logger = logging.getLogger("cover_gen")

try:
    from PIL import Image, ImageDraw, ImageFilter
except ImportError:
    Image = None
    logger.warning("Pillow not installed — AI cover generation disabled")


def _hash_to_hue(text: str) -> float:
    h = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    return (h % 360) / 360.0


def _hash_range(text: str, low: float, high: float) -> float:
    h = int(hashlib.md5(text.encode()).hexdigest()[:8], 16)
    return low + (h % 10000) / 10000.0 * (high - low)


def generate_cover_from_features(
    tempo: float = 120.0,
    energy: float = 0.5,
    danceability: float = 0.5,
    valence: float = 0.5,
    key: int = 0,
    mode: int = 1,
    prompt: str = "",
    output_path: str = "",
    size: int = 512,
) -> str:
    if Image is None:
        return ""

    if prompt:
        hue = _hash_to_hue(prompt)
        saturation = _hash_range(prompt, 0.4, 0.9)
        lightness = _hash_range(prompt, 0.15, 0.5)
    else:
        hue = (valence * 0.6 + energy * 0.4) % 1.0
        saturation = 0.4 + danceability * 0.5
        lightness = 0.15 + energy * 0.35

    r, g, b = colorsys.hls_to_rgb(hue, lightness, saturation)
    bg_color = tuple(int(c * 255) for c in (r, g, b))

    accent_hue = (hue + _hash_range(prompt or str(key), 0.1, 0.25)) % 1.0
    r2, g2, b2 = colorsys.hls_to_rgb(accent_hue, lightness + 0.12, saturation)
    accent_color = tuple(int(c * 255) for c in (r2, g2, b2))

    img = Image.new("RGB", (size, size), bg_color)
    draw = ImageDraw.Draw(img, "RGBA")

    cx = cy = size // 2
    num_circles = int(5 + energy * 12)
    for i in range(num_circles):
        radius = int((i + 1) / num_circles * size * 0.8)
        alpha = max(30, int(80 - i * (60 / num_circles)))
        offset_x = int((tempo / 200 - 0.5) * size * 0.15)
        offset_y = int((danceability - 0.5) * size * 0.15)
        circle_color = tuple(
            int(c * (1 - i / num_circles) + ac * (i / num_circles))
            for c, ac in zip(bg_color, accent_color)
        )
        draw.ellipse(
            [
                cx - radius + offset_x,
                cy - radius + offset_y,
                cx + radius + offset_x,
                cy + radius + offset_y,
            ],
            outline=(*circle_color, alpha),
            width=max(1, int(3 - (i / num_circles) * 2)),
        )

    num_lines = int(4 + valence * 8)
    for i in range(num_lines):
        import math
        angle = (i / num_lines) * 360 + key * 15
        rad = math.radians(angle)
        length = int((0.3 + danceability * 0.5) * size * 0.35)
        x1 = cx + int(math.cos(rad) * size * 0.2)
        y1 = cy + int(math.sin(rad) * size * 0.2)
        x2 = cx + int(math.cos(rad) * (size * 0.2 + length))
        y2 = cy + int(math.sin(rad) * (size * 0.2 + length))
        line_alpha = int(50 + energy * 100)
        draw.line(
            [x1, y1, x2, y2],
            fill=(*accent_color, line_alpha),
            width=max(1, int(2 + mode * 2)),
        )

    tempo_factor = max(0.3, min(1.0, tempo / 200))
    num_sparks = int(10 + tempo_factor * 30)
    for _ in range(num_sparks):
        spark_x = __import__("random").randint(0, size)
        spark_y = __import__("random").randint(0, size)
        spark_r = __import__("random").randint(1, 3)
        spark_alpha = __import__("random").randint(60, 160)
        draw.ellipse(
            [spark_x - spark_r, spark_y - spark_r, spark_x + spark_r, spark_y + spark_r],
            fill=(255, 255, 255, spark_alpha),
        )

    img = img.filter(ImageFilter.GaussianBlur(radius=max(0, int(3 - energy * 3))))
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    img = img.convert("RGB")
    img.save(output_path, "JPEG", quality=92)
    logger.info("Generated AI cover art at %s", output_path)
    return output_path


def generate_cover_from_prompt(
    prompt: str,
    output_path: str,
    tempo: float = 120.0,
    energy: float = 0.5,
    danceability: float = 0.5,
    valence: float = 0.5,
    key: int = 0,
    mode: int = 1,
    size: int = 512,
) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if api_key:
        try:
            from google import genai
            client = genai.Client(api_key=api_key)
            enhanced_prompt = f"{prompt}. Music album cover art, abstract, 1:1 aspect ratio."

            result = client.models.generate_images(
                model="imagen-4.0-generate-001",
                prompt=enhanced_prompt,
                config=genai.types.GenerateImagesConfig(
                    number_of_images=1,
                    aspect_ratio="1:1",
                ),
            )
            if result and result.generated_images:
                img_data = result.generated_images[0].image
                if hasattr(img_data, "save"):
                    os.makedirs(os.path.dirname(output_path), exist_ok=True)
                    img_data.save(output_path, "JPEG", quality=92)
                    logger.info("Generated AI cover via Imagen at %s", output_path)
                    return output_path
        except Exception as e:
            logger.warning("Imagen generation failed (%s) — using algorithmic", e)

    return generate_cover_from_features(
        tempo, energy, danceability, valence, key, mode, prompt, output_path, size
    )
