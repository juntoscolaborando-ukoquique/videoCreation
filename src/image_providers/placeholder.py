"""
Placeholder image provider — Pillow-based fallback for offline/testing.
"""

import logging
import os
from typing import List, Optional

logger = logging.getLogger(__name__)


def _generate_placeholder_images(
    prompts: List[str],
    output_dir: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
    config_loader=None,
) -> List[str]:
    """Create gradient placeholder images with prompt text overlay."""
    from PIL import Image, ImageDraw, ImageFont
    from src import config_loader as _default_config_loader

    _cfg = config_loader or _default_config_loader
    vcfg = _cfg.video()
    if width is None:
        width = vcfg.get("width", 1080)
    if height is None:
        height = vcfg.get("height", 1920)

    paths: List[str] = []
    for idx, prompt in enumerate(prompts):
        img = Image.new("RGB", (width, height), color=(30, 30, 50))
        draw = ImageDraw.Draw(img)

        for y in range(height):
            r = int(30 + (y / height) * 50)
            g = int(30 + (y / height) * 30)
            b = int(50 + (y / height) * 60)
            draw.line([(0, y), (width, y)], fill=(r, g, b))

        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        except OSError:
            font = ImageFont.load_default()

        label = f"Scene {idx + 1}"
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text(((width - tw) // 2, (height - th) // 2 - 40), label, fill=(220, 220, 220), font=font)

        snippet = prompt[:80] + ("…" if len(prompt) > 80 else "")
        try:
            small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 28)
        except OSError:
            small = ImageFont.load_default()
        draw.text((60, (height // 2) + 40), snippet, fill=(160, 160, 180), font=small)

        path = os.path.join(output_dir, f"gen_img_{idx:03d}.png")
        img.save(path)
        paths.append(path)
        logger.info("Placeholder image → %s", path)

    return paths
