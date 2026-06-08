"""
Provider Manager with Automatic Failover

Manages multiple image generation providers and automatically
switches to the next available provider when one fails or is rate-limited.
"""

import time
from typing import List, Optional, Dict, Any
from pathlib import Path

from .base import ImageProvider, ProviderResult, ProviderStatus
from .pollinations_provider import PollinationsProvider
from .huggingface_provider import HuggingFaceFluxProvider, HuggingFaceSDProvider
from .picsum_provider import PicsumProvider
from .siliconflow_provider import SiliconFlowProvider
from .cloudflare_provider import CloudflareProvider


class ProviderManager:
    """
    Manages multiple AI image providers with automatic failover.
    
    Usage:
        manager = ProviderManager()
        manager.add_pollinations()  # No API key needed
        manager.add_huggingface_flux(api_key="your_hf_key")  # Optional
        
        result = manager.generate_image("A scenic landscape")
        if result.success:
            print(f"Image generated: {result.image_path}")
    """
    
    def __init__(self, output_dir: str = "output/shorts/footage/generated"):
        self.providers: List[ImageProvider] = []
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        
        # Track usage statistics
        self.generation_count = 0
        self.success_count = 0
        self.failover_count = 0
    
    def add_pollinations(self, config: Dict[str, Any] = None):
        """Add Pollinations.ai provider (free, no API key)."""
        self.providers.append(PollinationsProvider(config))
        print(f"✅ Added Pollinations provider")
    
    def add_cloudflare(self, account_id: str = None, api_token: str = None, config: Dict[str, Any] = None):
        """Add Cloudflare Workers AI provider (requires Account ID and API token)."""
        if account_id and api_token:
            self.providers.append(CloudflareProvider(account_id, api_token, config))
            print(f"✅ Added Cloudflare Workers AI provider")
        else:
            print("⚠️  Skipped Cloudflare (missing account_id or api_token)")
    
    def add_siliconflow(self, api_key: str = None, config: Dict[str, Any] = None):
        """Add SiliconFlow provider (requires API key)."""
        if api_key:
            self.providers.append(SiliconFlowProvider(api_key, config))
            print(f"✅ Added SiliconFlow provider")
        else:
            print("⚠️  Skipped SiliconFlow (no API key)")
    
    def add_huggingface_flux(self, api_key: str = None, config: Dict[str, Any] = None):
        """Add HuggingFace FLUX provider (requires API key)."""
        if api_key:
            self.providers.append(HuggingFaceFluxProvider(api_key, config))
            print(f"✅ Added HuggingFace FLUX provider")
        else:
            print("⚠️  Skipped HuggingFace FLUX (no API key)")
    
    def add_huggingface_sd(self, api_key: str = None, config: Dict[str, Any] = None):
        """Add HuggingFace SDXL provider (requires API key)."""
        if api_key:
            self.providers.append(HuggingFaceSDProvider(api_key, config))
            print(f"✅ Added HuggingFace SDXL provider")
        else:
            print("⚠️  Skipped HuggingFace SDXL (no API key)")
    
    def add_provider(self, provider: ImageProvider):
        """Add a custom provider instance."""
        self.providers.append(provider)
        print(f"✅ Added custom provider: {provider.name}")
    
    def get_available_providers(self) -> List[ImageProvider]:
        """Get list of currently available providers."""
        available = []
        for provider in self.providers:
            if provider.is_available():
                available.append(provider)
        return available
    
    def generate_image(self, prompt: str, width: int = 1080, height: int = 1920,
                       style: str = "photorealistic", **kwargs) -> ProviderResult:
        """
        Generate an image using available providers with automatic failover.
        
        Args:
            prompt: Image description
            width: Image width
            height: Image height
            style: Style modifier
            **kwargs: Additional provider-specific options
            
        Returns:
            ProviderResult with success status and path or error
        """
        self.generation_count += 1
        
        # Enhance prompt with style
        enhanced_prompt = self._enhance_prompt(prompt, style)
        
        # Get available providers
        available = self.get_available_providers()
        
        if not available:
            # Try to reset rate-limited providers
            for provider in self.providers:
                provider.check_rate_limit_status()
            available = self.get_available_providers()
            
            if not available:
                return ProviderResult(
                    success=False,
                    error_message="No providers available (all rate limited or no API keys)",
                    provider_name="manager"
                )
        
        # Try each available provider
        last_error = None
        for i, provider in enumerate(available):
            print(f"🎨 Trying provider {i+1}/{len(available)}: {provider.name}...")
            
            # Add small delay between providers to avoid overwhelming services
            if i > 0:
                time.sleep(0.5)
                self.failover_count += 1
            
            result = provider.generate(
                enhanced_prompt, 
                width=width, 
                height=height,
                output_dir=str(self.output_dir),
                **kwargs
            )
            
            if result.success:
                self.success_count += 1
                print(f"✅ Success with {provider.name}: {result.image_path}")
                return result
            else:
                print(f"❌ Failed with {provider.name}: {result.error_message}")
                last_error = result
                
                # If rate limited, continue to next provider immediately
                if result.status_code == 429:
                    continue
        
        # All providers failed
        return ProviderResult(
            success=False,
            error_message=f"All providers failed. Last error: {last_error.error_message if last_error else 'Unknown'}",
            provider_name="manager",
            status_code=last_error.status_code if last_error else None
        )
    
    def generate_images_batch(self, prompts: List[str], width: int = 1080, 
                              height: int = 1920, style: str = "photorealistic",
                              delay_between: float = 1.0) -> List[ProviderResult]:
        """
        Generate multiple images with automatic failover for each.
        
        Args:
            prompts: List of image descriptions
            width: Image width
            height: Image height
            style: Style modifier
            delay_between: Seconds to wait between generations (for rate limiting)
            
        Returns:
            List of ProviderResult objects
        """
        results = []
        
        for i, prompt in enumerate(prompts):
            print(f"\n[{i+1}/{len(prompts)}] Generating: {prompt[:50]}...")
            
            result = self.generate_image(prompt, width, height, style)
            results.append(result)
            
            # Delay between generations to respect rate limits
            if i < len(prompts) - 1 and delay_between > 0:
                time.sleep(delay_between)
        
        # Summary
        success_count = sum(1 for r in results if r.success)
        print(f"\n📊 Batch complete: {success_count}/{len(prompts)} successful")
        
        return results
    
    def get_stats(self) -> Dict[str, Any]:
        """Get generation statistics."""
        return {
            'total_generations': self.generation_count,
            'successful': self.success_count,
            'failed': self.generation_count - self.success_count,
            'failover_count': self.failover_count,
            'success_rate': self.success_count / self.generation_count if self.generation_count > 0 else 0,
            'providers_count': len(self.providers),
            'available_providers': len(self.get_available_providers()),
            'provider_status': {
                p.name: p.status.value for p in self.providers
            }
        }
    
    def _enhance_prompt(self, prompt: str, style: str) -> str:
        """Enhance prompt with style modifiers."""
        style_modifiers = {
            'photorealistic': 'photorealistic, high quality photography, professional lighting, sharp focus, 8k',
            'cinematic': 'cinematic, dramatic lighting, movie still, color graded, atmospheric',
            'artistic': 'artistic, stylized, beautiful composition, creative',
            'cartoon': 'cartoon style, animated, vibrant colors, clean lines',
            'minimal': 'minimalist, clean, simple, modern, elegant',
            'dramatic': 'dramatic, high contrast, intense, powerful',
            'corporate': 'professional, business, clean, modern office setting',
            'ai_tech': 'futuristic AI technology, neural networks, digital art, glowing circuits'
        }
        
        modifier = style_modifiers.get(style, style_modifiers['photorealistic'])
        return f"{prompt}, {modifier}"


# Convenience function for quick usage
def create_default_manager(huggingface_key: str = None,
                          siliconflow_key: str = None,
                          cloudflare_account_id: str = None,
                          cloudflare_token: str = None,
                          output_dir: str = "output/shorts/footage/generated") -> ProviderManager:
    """
    Create a provider manager with sensible defaults.
    
    Args:
        cloudflare_account_id: Optional Cloudflare Account ID
        cloudflare_token: Optional Cloudflare API Token
        huggingface_key: Optional HuggingFace API key for additional providers
        siliconflow_key: Optional SiliconFlow API key
        output_dir: Output directory for generated images
        
    Returns:
        Configured ProviderManager
    """
    manager = ProviderManager(output_dir)
    
    # Add Cloudflare if credentials available (top priority — works on all IPs)
    if cloudflare_account_id and cloudflare_token:
        manager.add_cloudflare(
            cloudflare_account_id,
            cloudflare_token,
            config={'timeout': 90, 'max_retries': 2}
        )
    
    # Add SiliconFlow if key available
    if siliconflow_key:
        manager.add_siliconflow(siliconflow_key, config={'timeout': 60, 'max_retries': 2})
        
    # Always add Pollinations (free, no key needed)
    manager.add_pollinations(config={'timeout': 60, 'max_retries': 2})
    
    # Add HuggingFace providers if key available
    if huggingface_key:
        manager.add_huggingface_flux(huggingface_key, config={'timeout': 60})
        manager.add_huggingface_sd(huggingface_key, config={'timeout': 90})
        
    # Always add Picsum as a fallback
    manager.add_provider(PicsumProvider(config={'timeout': 30}))
    
    return manager
