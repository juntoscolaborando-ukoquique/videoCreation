"""
Cloudflare Workers AI Image Provider

High quality image generation via Cloudflare Workers AI.
Uses the FLUX.1-schnell model by default.
Requires Cloudflare Account ID and API Token.
"""

import time
import base64
import requests
from pathlib import Path

from .base import ImageProvider, ProviderResult, ProviderStatus


class CloudflareProvider(ImageProvider):
    """
    Cloudflare Workers AI provider.

    Features:
    - Fast generation via FLUX.1-schnell
    - Reliable on VPS/datacenter IPs (no IP blocks)
    - Works globally, including from South America

    Requires:
    - Cloudflare Account ID
    - Cloudflare API Token with Workers AI permissions
    """

    MODEL = "@cf/black-forest-labs/flux-1-schnell"

    def __init__(self, account_id: str = None, api_token: str = None, config: dict = None):
        super().__init__("cloudflare", config)
        self.account_id = account_id or (config.get('account_id') if config else None)
        self.api_token = api_token or (config.get('api_token') if config else None)
        self.timeout = config.get('timeout', 90) if config else 90
        self.max_retries = config.get('max_retries', 2) if config else 2
        self.retry_delay = config.get('retry_delay', 2) if config else 2
        self.model = config.get('model', self.MODEL) if config else self.MODEL

    @property
    def _api_url(self) -> str:
        return (
            f"https://api.cloudflare.com/client/v4/accounts/"
            f"{self.account_id}/ai/run/{self.model}"
        )

    def is_available(self) -> bool:
        """Check if provider has credentials and is not rate limited."""
        if not self.account_id or not self.api_token:
            return False
        return self.check_rate_limit_status()

    def generate(self, prompt: str, width: int = 1080, height: int = 1920,
                 output_dir: str = "output/shorts/footage/generated",
                 **kwargs) -> ProviderResult:
        """Generate image using Cloudflare Workers AI (FLUX.1-schnell)."""
        if not self.is_available():
            return ProviderResult(
                success=False,
                error_message="No Cloudflare credentials or rate limited",
                provider_name=self.name
            )

        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)

        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }

        payload = {
            "prompt": prompt,
        }

        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self._api_url,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )

                if response.status_code == 200:
                    content_type = response.headers.get("content-type", "")

                    if "application/json" in content_type:
                        data = response.json()
                        if data.get("success") and "result" in data:
                            image_b64 = data["result"].get("image")
                            if image_b64:
                                filename = f"cloudflare_{int(time.time())}.png"
                                file_path = output_path / filename
                                with open(file_path, "wb") as f:
                                    f.write(base64.b64decode(image_b64))
                                self.mark_success()
                                return ProviderResult(
                                    success=True,
                                    image_path=str(file_path),
                                    provider_name=self.name
                                )
                        return ProviderResult(
                            success=False,
                            error_message=f"Unexpected JSON response: {data}",
                            provider_name=self.name
                        )
                    else:
                        # Raw binary response
                        filename = f"cloudflare_{int(time.time())}.png"
                        file_path = output_path / filename
                        with open(file_path, "wb") as f:
                            f.write(response.content)
                        self.mark_success()
                        return ProviderResult(
                            success=True,
                            image_path=str(file_path),
                            provider_name=self.name
                        )

                elif response.status_code == 429:
                    self.mark_rate_limited(reset_time=time.time() + 60)
                    if attempt < self.max_retries - 1:
                        time.sleep(self.retry_delay * 2)
                        continue
                    return ProviderResult(
                        success=False,
                        error_message="Rate limited (429)",
                        status_code=429,
                        provider_name=self.name
                    )

                else:
                    self.mark_error()
                    return ProviderResult(
                        success=False,
                        error_message=f"HTTP {response.status_code}: {response.text[:200]}",
                        status_code=response.status_code,
                        provider_name=self.name
                    )

            except requests.exceptions.Timeout:
                self.mark_error()
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                return ProviderResult(
                    success=False,
                    error_message="Request timeout",
                    provider_name=self.name
                )

            except Exception as e:
                self.mark_error()
                if attempt < self.max_retries - 1:
                    time.sleep(self.retry_delay)
                    continue
                return ProviderResult(
                    success=False,
                    error_message=str(e),
                    provider_name=self.name
                )

        return ProviderResult(
            success=False,
            error_message="All retries failed",
            provider_name=self.name
        )
