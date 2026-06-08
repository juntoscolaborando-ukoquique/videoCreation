"""
SiliconFlow API Image Provider

High quality image generation via SiliconFlow API.
Supports models like FLUX.1-schnell.
Requires API key.
"""

import time
import requests
from pathlib import Path
from typing import Optional

from .base import ImageProvider, ProviderResult, ProviderStatus


class SiliconFlowProvider(ImageProvider):
    """
    SiliconFlow Image Provider.
    
    Features:
    - Fast generation
    - Multiple models supported (default: FLUX.1-schnell)
    
    Requires:
    - SiliconFlow API token
    """
    
    API_URL = "https://api.siliconflow.cn/v1/images/generations"
    
    def __init__(self, api_key: str = None, config: dict = None):
        super().__init__("siliconflow", config)
        self.api_key = api_key or (config.get('api_key') if config else None)
        self.timeout = config.get('timeout', 60) if config else 60
        self.max_retries = config.get('max_retries', 2) if config else 2
        self.retry_delay = config.get('retry_delay', 2) if config else 2
        self.model = config.get('model', 'black-forest-labs/FLUX.1-schnell') if config else 'black-forest-labs/FLUX.1-schnell'
    
    def is_available(self) -> bool:
        """Check if provider has API key and is not rate limited."""
        if not self.api_key:
            return False
        return self.check_rate_limit_status()
    
    def generate(self, prompt: str, width: int = 1080, height: int = 1920,
                 output_dir: str = "output/shorts/footage/generated",
                 **kwargs) -> ProviderResult:
        """Generate image using SiliconFlow."""
        if not self.is_available():
            return ProviderResult(
                success=False,
                error_message="No API key or rate limited",
                provider_name=self.name
            )
        
        # Create output directory
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # Determine image_size format expected by SiliconFlow (e.g. 1024x1024, 768x1024)
        # FLUX.1-schnell generally expects standard dimensions or multiples of 32
        # Let's map standard shorts sizes to nearest supported sizes if necessary,
        # but 1024x1024 is safe. For 9:16, 576x1024 or 768x1024 might be supported.
        # According to standard SiliconFlow API docs:
        image_size_str = f"{width}x{height}"
        # Some models only support specific resolutions. FLUX is quite flexible.
        
        payload = {
            "model": self.model,
            "prompt": prompt,
            "image_size": image_size_str,
            "batch_size": 1,
            "num_inference_steps": 4, # FLUX.1-schnell uses 4 steps
            "guidance_scale": 0
        }
        
        for attempt in range(self.max_retries):
            try:
                response = requests.post(
                    self.API_URL,
                    headers=headers,
                    json=payload,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    data = response.json()
                    
                    if "images" in data and len(data["images"]) > 0:
                        image_url = data["images"][0].get("url")
                        
                        if image_url:
                            # Download the image
                            img_response = requests.get(image_url, timeout=30)
                            if img_response.status_code == 200:
                                filename = f"siliconflow_{int(time.time())}.png"
                                file_path = output_path / filename
                                
                                with open(file_path, 'wb') as f:
                                    f.write(img_response.content)
                                
                                self.mark_success()
                                
                                return ProviderResult(
                                    success=True,
                                    image_path=str(file_path),
                                    provider_name=self.name
                                )
                    
                    return ProviderResult(
                        success=False,
                        error_message="API returned success but no image URL found",
                        provider_name=self.name
                    )
                
                elif response.status_code == 429:
                    # Rate limited
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
                    err_text = response.text
                    return ProviderResult(
                        success=False,
                        error_message=f"HTTP {response.status_code}: {err_text[:100]}",
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
