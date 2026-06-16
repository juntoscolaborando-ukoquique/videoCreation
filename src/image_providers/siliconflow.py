"""
SiliconFlow image provider.
"""

import logging
import os
import time
from typing import List

import requests

from src.image_providers._http import ProviderAuthError

logger = logging.getLogger(__name__)


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
        "Content-Type": "application/json",
    }
    timeout = 90
    max_retries = 3

    paths: List[str] = []
    for idx, prompt in enumerate(prompts):
        logger.info("[%d/%d] SiliconFlow — %s", idx + 1, len(prompts), prompt[:60])
        full_prompt = f"{style} {prompt}"
        success = False

        for attempt in range(max_retries):
            if attempt > 0:
                wait = 5 * attempt
                logger.info("  retry %d/%d after %ds...", attempt + 1, max_retries, wait)
                time.sleep(wait)
            try:
                payload = {
                    "model": "black-forest-labs/FLUX.1-schnell",
                    "prompt": full_prompt,
                    "image_size": f"{width}x{height}",
                    "num_inference_steps": 4,
                    "num_images": 1,
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
                            success = True
                            break
                    else:
                        logger.warning("  SiliconFlow returned unexpected response format.")
                elif response.status_code == 401:
                    logger.warning("  SiliconFlow auth error — skipping provider.")
                    return []
                else:
                    logger.warning("  SiliconFlow HTTP %d: %s", response.status_code, response.text[:200])
            except Exception as exc:
                logger.warning("  SiliconFlow attempt %d failed: %s", attempt + 1, exc)

        if not success:
            logger.warning("  [%d/%d] failed after %d attempts — skipping image.", idx + 1, len(prompts), max_retries)

        if idx < len(prompts) - 1:
            time.sleep(3)

    return paths if len(paths) == len(prompts) else []
