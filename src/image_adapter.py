"""
Image Adapter — AI image generation & modification bridge.

Provider priority:
  1. Cloudflare Workers AI (native)
  2. SiliconFlow (native)
  3. Picsum (seed-based) — only when ``image_engine: picsum`` is explicitly set
  4. Pillow placeholder fallback — offline / testing, when all others fail
"""

import os
import re
import shutil
import time
import logging
import base64
import requests
from pathlib import Path
from typing import List, Optional

from src import config_loader

logger = logging.getLogger(__name__)

_env_loaded = False


def _ensure_env() -> None:
    """Load .env credentials once, lazily, on first use."""
    global _env_loaded
    if _env_loaded:
        return
    try:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)
    except ImportError:
        pass
    _env_loaded = True


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
    """Generate one image per prompt and return a list of file paths."""
    _ensure_env()
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

    # Engines declared in schema but not yet implemented
    if engine in ("huggingface", "pollinations"):
        raise NotImplementedError(
            f"image_engine='{engine}' is declared in the schema but not yet implemented. "
            "Use 'cloudflare' or 'siliconflow' (requires credentials in .env), "
            "or 'picsum' for seed-based stock photos."
        )

    # Apply the global use_picsum config flag when no explicit engine was requested.
    # This lets users set `use_picsum: true` in default_config.yaml once instead of
    # adding `image_engine: picsum` to every per-video config file.
    if engine is None and cfg.get("use_picsum", False):
        engine = "picsum"

    # 1. Picsum — only when explicitly requested
    if engine == "picsum":
        stock_dir = os.path.join(output_dir, "stock")
        os.makedirs(stock_dir, exist_ok=True)
        paths = _picsum_batch(prompts, stock_dir, width, height)
        if paths:
            return paths
        logger.warning("Picsum failed — trying next provider.")

    # 2. AI providers — Cloudflare first, then SiliconFlow
    gen_dir = os.path.join(output_dir, "generated")
    os.makedirs(gen_dir, exist_ok=True)
    ai_paths = _native_ai_generation(
        prompts, gen_dir, style, aspect_ratio, width, height, preferred_engine=engine
    )
    if ai_paths:
        return ai_paths

    # 3. Pillow placeholders
    logger.warning("AI image generation unavailable — using Pillow placeholder images.")
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
    """Apply AI modifications to images (not yet implemented)."""
    raise NotImplementedError(
        f"image_modification_instructions is set ('{instructions[:60]}') "
        "but modify_images() is not yet implemented. "
        "Remove image_modification_instructions from your config to proceed."
    )


# ---------------------------------------------------------------------------
# Picsum seeded by prompt keywords
# ---------------------------------------------------------------------------

def _prompt_to_seed(prompt: str) -> str:
    """Extract the first few meaningful words from a prompt for Picsum seed."""
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
    """Fetch one Picsum image per prompt using a keyword-derived seed."""
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
        return []

    logger.info("Picsum batch: %d/%d images fetched successfully.", len(paths), len(prompts))
    return paths


# ---------------------------------------------------------------------------
# Native AI Providers (Cloudflare & SiliconFlow)
# ---------------------------------------------------------------------------

def _native_ai_generation(
    prompts: List[str],
    output_dir: str,
    style: str,
    aspect_ratio: str,
    width: int,
    height: int,
    preferred_engine: Optional[str] = None,
) -> Optional[List[str]]:
    """Generate images using native AI providers (Cloudflare or SiliconFlow)."""
    paths: List[str] = []

    # Try preferred engine first, then fallback
    providers = []
    if preferred_engine == "cloudflare":
        providers = ["cloudflare"]
    elif preferred_engine == "siliconflow":
        providers = ["siliconflow"]
    else:
        providers = ["cloudflare", "siliconflow"]

    for provider in providers:
        if provider == "cloudflare":
            paths = _try_cloudflare(prompts, output_dir, width, height, style)
            if paths:
                return paths
        elif provider == "siliconflow":
            paths = _try_siliconflow(prompts, output_dir, width, height, style)
            if paths:
                return paths

    return None


def _try_cloudflare(
    prompts: List[str],
    output_dir: str,
    width: int,
    height: int,
    style: str,
) -> List[str]:
    """Try Cloudflare Workers AI for image generation."""
    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id or not api_token:
        logger.debug("Cloudflare credentials missing — skipping.")
        return []

    model = config_loader.cloudflare().get("model", "@cf/black-forest-labs/flux-1-schnell")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    paths: List[str] = []
    timeout = config_loader.cloudflare().get("timeout", 90)
    max_retries = 3

    for idx, prompt in enumerate(prompts):
        logger.info("[%d/%d] Cloudflare AI — %s", idx + 1, len(prompts), prompt[:60])
        full_prompt = f"{style} {prompt}"
        success = False

        for attempt in range(max_retries):
            if attempt > 0:
                wait = 5 * attempt
                logger.info("  retry %d/%d after %ds...", attempt + 1, max_retries, wait)
                time.sleep(wait)
            try:
                payload = {"prompt": full_prompt}
                response = requests.post(url, headers=headers, json=payload, timeout=timeout)
                if response.status_code == 200:
                    filename = f"cloudflare_{idx:03d}.png"
                    file_path = os.path.join(output_dir, filename)
                    if "image" in response.headers.get("Content-Type", ""):
                        with open(file_path, "wb") as f:
                            f.write(response.content)
                    else:
                        data = response.json()
                        if "result" in data and "image" in data["result"]:
                            with open(file_path, "wb") as f:
                                f.write(base64.b64decode(data["result"]["image"]))
                        else:
                            logger.warning("  Cloudflare returned unexpected response format.")
                            continue
                    paths.append(file_path)
                    logger.info("  ✓ saved → %s", file_path)
                    success = True
                    break
                elif response.status_code == 401:
                    logger.warning("  Cloudflare auth error — skipping provider.")
                    return []
                else:
                    logger.warning("  Cloudflare HTTP %d: %s", response.status_code, response.text[:200])
                    # NSFW or permanent error — no point retrying
                    if response.status_code == 400:
                        break
            except Exception as exc:
                logger.warning("  Cloudflare attempt %d failed: %s", attempt + 1, exc)

        if not success:
            logger.warning("  [%d/%d] failed after %d attempts — skipping image.", idx + 1, len(prompts), max_retries)

        if idx < len(prompts) - 1:
            time.sleep(3)

    return paths if len(paths) == len(prompts) else []


def _try_siliconflow(
    prompts: List[str],
    output_dir: str,
    width: int,
    height: int,
    style: str,
) -> List[str]:
    """Try SiliconFlow for image generation."""
    api_key = os.environ.get("SILICONFLOW_API_KEY")
    if not api_key:
        logger.debug("SiliconFlow API key missing — skipping.")
        return []

    url = "https://api.siliconflow.cn/v1/images/generations"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    paths: List[str] = []
    timeout = 90

    for idx, prompt in enumerate(prompts):
        logger.info("[%d/%d] SiliconFlow — %s", idx + 1, len(prompts), prompt[:60])
        full_prompt = f"{style} {prompt}"
        try:
            payload = {
                "model": "black-forest-labs/FLUX.1-schnell",
                "prompt": full_prompt,
                "image_size": f"{width}x{height}",
                "num_inference_steps": 4,
                "num_images": 1
            }
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 200:
                data = response.json()
                if "data" in data and len(data["data"]) > 0 and "url" in data["data"][0]:
                    img_url = data["data"][0]["url"]
                    img_response = requests.get(img_url, timeout=30)
                    if img_response.status_code == 200:
                        filename = f"siliconflow_{idx:03d}.png"
                        file_path = os.path.join(output_dir, filename)
                        with open(file_path, "wb") as f:
                            f.write(img_response.content)
                        paths.append(file_path)
                        logger.info("  ✓ saved → %s", file_path)
                else:
                    logger.warning("  SiliconFlow returned unexpected response format.")
                    continue
            else:
                logger.warning("  SiliconFlow HTTP %d: %s", response.status_code, response.text)
                break
        except Exception as exc:
            logger.warning("  SiliconFlow failed: %s", exc)
            break

        if idx < len(prompts) - 1:
            time.sleep(3)

    return paths if len(paths) == len(prompts) else []


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
