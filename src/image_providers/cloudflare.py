"""
Cloudflare Workers AI image provider.
"""

import base64
import logging
import os
import time
from typing import List

import requests

from src.image_providers._http import ProviderAuthError, _http_post_with_retry

logger = logging.getLogger(__name__)


def _try_cloudflare(
    prompts: List[str],
    output_dir: str,
    width: int,
    height: int,
    style: str,
    config_loader=None,
) -> List[str]:
    """Try Cloudflare Workers AI for image generation."""
    from src import config_loader as _default_config_loader
    _cfg = config_loader or _default_config_loader

    account_id = os.environ.get("CLOUDFLARE_ACCOUNT_ID")
    api_token = os.environ.get("CLOUDFLARE_API_TOKEN")

    if not account_id or not api_token:
        logger.debug("Cloudflare credentials missing — skipping.")
        return []

    model = _cfg.cloudflare().get("model", "@cf/black-forest-labs/flux-1-schnell")
    url = f"https://api.cloudflare.com/client/v4/accounts/{account_id}/ai/run/{model}"
    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json",
    }
    timeout = _cfg.cloudflare().get("timeout", 90)

    paths: List[str] = []
    for idx, prompt in enumerate(prompts):
        logger.info("[%d/%d] Cloudflare AI — %s", idx + 1, len(prompts), prompt[:60])
        full_prompt = f"{style} {prompt}"

        try:
            response = _http_post_with_retry(
                url=url,
                headers=headers,
                payload={"prompt": full_prompt},
                timeout=timeout,
            )
        except ProviderAuthError:
            logger.warning("  Cloudflare auth error — skipping provider.")
            return []

        if response is not None and response.status_code == 200:
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
        else:
            logger.warning("  [%d/%d] failed after retries — skipping image.", idx + 1, len(prompts))

        if idx < len(prompts) - 1:
            time.sleep(3)

    return paths if len(paths) == len(prompts) else []
