"""
Image Adapter — AI image generation & modification bridge.

Routing logic (generate_from_prompts, _native_ai_generation) lives here so
that patch.object(image_adapter, "...") works correctly in tests.

Provider implementations live in src/image_providers/:
  cloudflare.py, siliconflow.py, picsum.py, placeholder.py, _http.py
"""

import logging
import os
import requests  # noqa: F401 — kept here so patch("src.image_adapter.requests.*") works
from typing import List, Optional

from src import config_loader as _default_config_loader

# Provider helpers — imported as module-level names so patch.object(image_adapter, ...) works
from src.image_providers.cloudflare import _try_cloudflare
from src.image_providers.siliconflow import _try_siliconflow
from src.image_providers.picsum import _picsum_batch, _prompt_to_seed
from src.image_providers.placeholder import _generate_placeholder_images
from src.image_providers._http import _http_post_with_retry, ProviderAuthError
from src.image_providers._routing import (
    copy_provided_images,
    modify_images,
    _dimensions_for_aspect,
    _ensure_env,
)

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
    config_loader=None,
) -> List[str]:
    """Generate one image per prompt and return a list of file paths."""
    _cfg = config_loader or _default_config_loader
    _ensure_env()
    cfg = _cfg.image()
    if style is None:
        style = cfg.get("style", "photorealistic")
    if aspect_ratio is None:
        aspect_ratio = cfg.get("aspect_ratio", "9:16")

    if engine is None:
        engine = cfg.get("engine")

    if width is None or height is None:
        vcfg = _cfg.video()
        base_w = vcfg.get("width", 1080)
        base_h = vcfg.get("height", 1920)
        _w, _h = _dimensions_for_aspect(aspect_ratio, base_w, base_h)
        if width is None:
            width = _w
        if height is None:
            height = _h

    os.makedirs(output_dir, exist_ok=True)

    if engine in ("huggingface", "pollinations"):
        raise NotImplementedError(
            f"image_engine='{engine}' is declared in the schema but not yet implemented. "
            "Use 'cloudflare' or 'siliconflow' (requires credentials in .env), "
            "or 'picsum' for seed-based stock photos."
        )

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
        prompts, gen_dir, style, aspect_ratio, width, height,
        preferred_engine=engine, config_loader=_cfg,
    )
    if ai_paths:
        return ai_paths

    # 3. Pillow placeholders
    logger.warning("AI image generation unavailable — using Pillow placeholder images.")
    return _generate_placeholder_images(prompts, gen_dir, width=width, height=height, config_loader=_cfg)


# ---------------------------------------------------------------------------
# Internal routing — lives here so patch.object(image_adapter, ...) works
# ---------------------------------------------------------------------------

def _native_ai_generation(
    prompts: List[str],
    output_dir: str,
    style: str,
    aspect_ratio: str,
    width: int,
    height: int,
    preferred_engine: Optional[str] = None,
    config_loader=None,
) -> Optional[List[str]]:
    """Route to Cloudflare or SiliconFlow based on preferred_engine."""
    if preferred_engine == "cloudflare":
        providers = ["cloudflare"]
    elif preferred_engine == "siliconflow":
        providers = ["siliconflow"]
    else:
        providers = ["cloudflare", "siliconflow"]

    for provider in providers:
        if provider == "cloudflare":
            paths = _try_cloudflare(prompts, output_dir, width, height, style, config_loader=config_loader)
            if paths:
                return paths
        elif provider == "siliconflow":
            paths = _try_siliconflow(prompts, output_dir, width, height, style)
            if paths:
                return paths

    return None
