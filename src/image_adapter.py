"""
Image Adapter — AI image generation & modification bridge.

Provider priority:
  1. FootageGeneratorV2 (Lingo_PERSONAS, default) — Cloudflare Workers AI →
     SiliconFlow → HuggingFace → Pollinations (blocked on VPS, skipped)
  2. Picsum (seed-based) — only when ``image_engine: picsum`` is explicitly set;
     free, no auth, deterministic per prompt keyword seed
  3. Pillow placeholder fallback — offline / testing, when all others fail
"""

import os
import re
import shutil
import time
import logging
from pathlib import Path
from typing import List, Optional
from urllib.parse import quote

try:
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
except ImportError:
    pass  # python-dotenv not installed — credentials must come from the environment directly

from src.lingo_utils import ensure_lingo_on_path
from src import config_loader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def generate_from_prompts(
    prompts: List[str],
    output_dir: str,
    style: Optional[str] = None,
    aspect_ratio: Optional[str] = None,
    engine: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> List[str]:
    """Generate one image per prompt and return a list of file paths.

    Provider priority: Picsum (seeded) → FootageGeneratorV2 → Pillow placeholders.
    """
    cfg = config_loader.image()
    if style is None:
        style = cfg.get("style", "photorealistic")
    if aspect_ratio is None:
        aspect_ratio = cfg.get("aspect_ratio", "9:16")

    if width is None or height is None:
        vcfg = config_loader.video()
        base_w = vcfg.get("width", 1080)
        base_h = vcfg.get("height", 1920)
        _w, _h = _dimensions_for_aspect(aspect_ratio, base_w, base_h)
        if width is None:
            width = _w
        if height is None:
            height = _h

    os.makedirs(output_dir, exist_ok=True)

    # 1. Picsum — only when explicitly requested via image_engine: picsum
    if engine == "picsum":
        stock_dir = os.path.join(output_dir, "stock")
        os.makedirs(stock_dir, exist_ok=True)
        paths = _picsum_batch(prompts, stock_dir, width, height)
        if paths:
            return paths
        logger.warning("Picsum failed or returned partial results — trying next provider.")

    # 2. FootageGeneratorV2 (Lingo) — default for all other engines
    #    The engine hint is forwarded so FootageGeneratorV2 can prioritise
    #    a specific provider if it supports it (e.g. "siliconflow").
    #    Unknown engine values are logged and ignored gracefully.
    if engine is not None and engine != "picsum":
        logger.info("Requested image engine: '%s' — forwarding to FootageGeneratorV2.", engine)
    gen_dir = os.path.join(output_dir, "generated")
    os.makedirs(gen_dir, exist_ok=True)
    lingo_paths = _try_footage_generator(
        prompts, gen_dir, style, aspect_ratio,
        preferred_engine=engine if engine != "picsum" else None,
    )
    if lingo_paths:
        return lingo_paths

    # 3. Pillow placeholders
    logger.warning("FootageGeneratorV2 unavailable — using Pillow placeholder images.")
    return _generate_placeholder_images(prompts, gen_dir, width=width, height=height)


def copy_provided_images(image_paths: List[str], output_dir: str) -> List[str]:
    """Validate and copy user-provided images into the workspace."""
    cached_dir = os.path.join(output_dir, "cached")
    os.makedirs(cached_dir, exist_ok=True)
    copied: List[str] = []
    for src in image_paths:
        if not os.path.isfile(src):
            logger.warning("Image not found, skipping: %s", src)
            continue
        dst = os.path.join(cached_dir, os.path.basename(src))
        shutil.copy2(src, dst)
        copied.append(dst)
    return copied


def modify_images(image_paths: List[str], instructions: str) -> List[str]:
    """Apply AI modifications to images.

    .. note::
        Not yet implemented. Raises ``NotImplementedError`` explicitly so
        the caller gets a clear failure instead of silently getting
        unmodified images back.
        Remove ``image_modification_instructions`` from your config to proceed.
    """
    raise NotImplementedError(
        f"image_modification_instructions is set ('{instructions[:60]}') "
        "but modify_images() is not yet implemented. "
        "Remove image_modification_instructions from your config to proceed."
    )


# ---------------------------------------------------------------------------
# Picsum seeded by prompt keywords
# ---------------------------------------------------------------------------

def _prompt_to_seed(prompt: str) -> str:
    """Extract the first few meaningful words from a prompt to use as a Picsum seed.

    Picsum's seed endpoint returns a consistent image for the same seed string,
    so different prompts get different images and reruns are deterministic.
    Example: 'A futuristic city skyline at night' → 'futuristic-city-skyline'
    """
    stopwords = {"a", "an", "the", "at", "in", "on", "of", "and", "with", "for", "to", "is"}
    words = re.sub(r"[^a-z0-9 ]", "", prompt.lower()).split()
    keywords = [w for w in words if w not in stopwords][:4]
    return "-".join(keywords) if keywords else "photo"


def _picsum_batch(
    prompts: List[str],
    output_dir: str,
    width: int,
    height: int,
) -> List[str]:
    """Fetch one Picsum image per prompt using a keyword-derived seed.

    URL format: https://picsum.photos/seed/{seed}/{width}/{height}.jpg
    Picsum returns a 302 redirect — must follow with allow_redirects=True.
    Same seed → same image every run. Different prompts → different seeds → different images.
    """
    import requests

    paths: List[str] = []
    timeout = 30

    for idx, prompt in enumerate(prompts):
        seed = _prompt_to_seed(prompt)
        url  = f"https://picsum.photos/seed/{seed}/{width}/{height}.jpg"
        logger.info("[%d/%d] Picsum seed='%s' — %s", idx + 1, len(prompts), seed, prompt[:60])

        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                filename  = f"picsum_{idx:03d}_{seed}.jpg"
                file_path = os.path.join(output_dir, filename)
                with open(file_path, "wb") as f:
                    f.write(response.content)
                paths.append(file_path)
                logger.info("  ✓ saved → %s", file_path)
            else:
                logger.warning("  HTTP %d for seed '%s'", response.status_code, seed)
        except Exception as exc:
            logger.warning("  failed for seed '%s': %s", seed, exc)

        if idx < len(prompts) - 1:
            time.sleep(0.5)

    if len(paths) < len(prompts):
        logger.warning(
            "Picsum batch incomplete: %d/%d images fetched — "
            "discarding partial results to maintain video synchronization.",
            len(paths), len(prompts),
        )
        return []  # Caller will fall through to next provider (e.g. AI generation)

    logger.info("Picsum batch: %d/%d images fetched successfully.", len(paths), len(prompts))
    return paths


# ---------------------------------------------------------------------------
# Lingo_PERSONAS FootageGeneratorV2 (secondary)
# ---------------------------------------------------------------------------

def _try_footage_generator(
    prompts: List[str],
    output_dir: str,
    style: str,
    aspect_ratio: str,
    preferred_engine: Optional[str] = None,
) -> Optional[List[str]]:
    """Attempt to use FootageGeneratorV2 from Lingo_PERSONAS.

    Returns None if Lingo is not installed. Re-raises runtime errors.
    Credentials for Cloudflare, SiliconFlow, and HuggingFace are read
    from environment variables automatically by FootageGeneratorV2.

    preferred_engine: optional hint forwarded to FootageGeneratorV2 if it
        supports provider selection (e.g. ``"siliconflow"``). Ignored if
        FootageGeneratorV2 does not accept the parameter.
    """
    try:
        ensure_lingo_on_path()
        from shorts_creator.footage_generator_v2 import FootageGeneratorV2  # type: ignore[import-untyped]
    except (ImportError, Exception) as exc:
        logger.warning("FootageGeneratorV2 not available (%s).", exc)
        return None

    try:
        gen = FootageGeneratorV2(
            output_dir=output_dir,
            cloudflare_account_id=os.environ.get('CLOUDFLARE_ACCOUNT_ID') or None,
            cloudflare_token=os.environ.get('CLOUDFLARE_API_TOKEN') or None,
            siliconflow_key=os.environ.get('SILICONFLOW_API_KEY') or None,
            huggingface_key=os.environ.get('HUGGINGFACE_API_KEY') or None,
        )
        # Explanation: `or None` converts both a missing key (returns None from get)
        # and an explicitly empty string (e.g. KEY="" in .env) to None, so
        # FootageGeneratorV2 correctly skips that provider instead of attempting
        # authentication with an empty credential string.
        batch_kwargs = dict(style=style, aspect_ratio=aspect_ratio, delay=3.0)
        if preferred_engine is not None:
            try:
                paths = gen.generate_images_batch(
                    prompts, provider=preferred_engine, **batch_kwargs
                )
            except TypeError:
                # FootageGeneratorV2 doesn't accept provider= — fall back to default call
                logger.debug("FootageGeneratorV2 does not support provider= kwarg — ignoring engine hint.")
                paths = gen.generate_images_batch(prompts, **batch_kwargs)
        else:
            paths = gen.generate_images_batch(prompts, **batch_kwargs)
        return paths if paths else None
    except Exception as exc:
        logger.error("FootageGeneratorV2 raised an unexpected error: %s", exc)
        raise


# ---------------------------------------------------------------------------
# Pillow placeholder fallback
# ---------------------------------------------------------------------------

def _generate_placeholder_images(
    prompts: List[str],
    output_dir: str,
    width: Optional[int] = None,
    height: Optional[int] = None,
) -> List[str]:
    """Create gradient placeholder images with prompt text overlay."""
    from PIL import Image, ImageDraw, ImageFont

    vcfg = config_loader.video()
    if width is None:
        width = vcfg.get("width", 1080)
    if height is None:
        height = vcfg.get("height", 1920)

    paths: List[str] = []
    for idx, prompt in enumerate(prompts):
        img  = Image.new("RGB", (width, height), color=(30, 30, 50))
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
        bbox  = draw.textbbox((0, 0), label, font=font)
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


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _dimensions_for_aspect(aspect_ratio: str, base_w: int, base_h: int) -> tuple:
    """Return (width, height) for the given aspect ratio string."""
    mapping = {
        "9:16":  (min(base_w, base_h), max(base_w, base_h)),
        "16:9":  (max(base_w, base_h), min(base_w, base_h)),
        "1:1":   (min(base_w, base_h), min(base_w, base_h)),
    }
    return mapping.get(aspect_ratio, (base_w, base_h))
