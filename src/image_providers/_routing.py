"""
Image provider routing — shared helpers re-exported by image_adapter.py.

generate_from_prompts and _native_ai_generation live in image_adapter.py
(not here) so that patch.object(image_adapter, ...) works correctly in tests.
"""

import logging
import os
import shutil
from typing import List

logger = logging.getLogger(__name__)

_env_loaded = False


def _ensure_env() -> None:
    """Load .env credentials once, lazily, on first use."""
    global _env_loaded
    if _env_loaded:
        return
    try:
        from pathlib import Path
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=False)
    except ImportError:
        pass
    _env_loaded = True


def _dimensions_for_aspect(aspect_ratio: str, base_w: int, base_h: int) -> tuple:
    """Return (width, height) for the given aspect ratio string."""
    mapping = {
        "9:16": (min(base_w, base_h), max(base_w, base_h)),
        "16:9": (max(base_w, base_h), min(base_w, base_h)),
        "1:1":  (min(base_w, base_h), min(base_w, base_h)),
    }
    return mapping.get(aspect_ratio, (base_w, base_h))


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
