"""
Picsum image provider — seed-based stock photos.
"""

import logging
import os
import re
import time
from typing import List

import requests

logger = logging.getLogger(__name__)


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
        url = f"https://picsum.photos/seed/{seed}/{width}/{height}.jpg"
        logger.info("[%d/%d] Picsum seed='%s' — %s", idx + 1, len(prompts), seed, prompt[:60])

        try:
            response = requests.get(url, timeout=timeout, allow_redirects=True)
            if response.status_code == 200:
                filename = f"picsum_{idx:03d}_{seed}.jpg"
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
