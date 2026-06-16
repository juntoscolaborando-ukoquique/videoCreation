"""
Shared HTTP utilities for image providers.
"""

import logging
import time
from typing import Dict, Optional

import requests

logger = logging.getLogger(__name__)


class ProviderAuthError(Exception):
    """Raised when a provider returns 401 Unauthorized."""


def _http_post_with_retry(
    url: str,
    headers: Dict,
    payload: Dict,
    timeout: int,
    max_retries: int = 3,
) -> Optional[requests.Response]:
    """POST with exponential backoff.

    Returns Response on 200, None on exhausted retries.
    Raises ProviderAuthError on 401.
    """
    for attempt in range(max_retries):
        if attempt > 0:
            wait = 5 * attempt
            logger.info("  retry %d/%d after %ds...", attempt + 1, max_retries, wait)
            time.sleep(wait)
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=timeout)
            if response.status_code == 200:
                return response
            elif response.status_code == 401:
                raise ProviderAuthError(f"Auth error from {url}")
            elif response.status_code == 400:
                logger.warning("  HTTP 400 (permanent) — aborting retries.")
                return None
            else:
                logger.warning("  HTTP %d — will retry if attempts remain.", response.status_code)
        except ProviderAuthError:
            raise
        except Exception as exc:
            logger.warning("  attempt %d failed: %s", attempt + 1, exc)

    return None
