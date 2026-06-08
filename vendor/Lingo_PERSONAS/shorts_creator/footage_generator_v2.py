"""
Footage Generator v2 - Decoupled Architecture with Automatic Failover

Refactored to use the new provider architecture that supports
multiple free AI image providers with automatic failover.

Inherits from FootageGenerator to maintain all stock image functionality
while overriding AI generation with the new provider architecture.
"""

import os
from pathlib import Path
from typing import List, Dict, Optional

# Import the new provider architecture
from shorts_creator.image_providers import (
    ProviderManager,
    ProviderResult,
    create_default_manager,
    PollinationsProvider,
    HuggingFaceFluxProvider,
    HuggingFaceSDProvider
)

# Import original FootageGenerator for stock image methods
from .footage_generator import FootageGenerator as FootageGeneratorBase


class FootageGeneratorV2(FootageGeneratorBase):
    """
    Next-generation footage generator with automatic provider failover.
    
    Automatically switches between multiple free AI providers when rate limits
    are hit, ensuring reliable image generation without manual intervention.
    """
    
    def __init__(self, output_dir: str = 'output/shorts/footage',
                 pexels_key: str = None, 
                 pixabay_key: str = None,
                 huggingface_key: str = None,
                 siliconflow_key: str = None,
                 cloudflare_account_id: str = None,
                 cloudflare_token: str = None):
        """
        Initialize the footage generator with provider failover support.
        
        Args:
            output_dir: Directory to save generated assets
            pexels_key: Optional Pexels API key
            pixabay_key: Optional Pixabay API key  
            huggingface_key: Optional HuggingFace API key (adds more providers)
            siliconflow_key: Optional SiliconFlow API key
            cloudflare_account_id: Optional Cloudflare Account ID
            cloudflare_token: Optional Cloudflare API token
        """
        # Initialize base class for stock image functionality
        super().__init__(
            output_dir=output_dir,
            pexels_key=pexels_key,
            pixabay_key=pixabay_key,
            huggingface_key=huggingface_key
        )
        
        # Store the keys for provider manager
        self.huggingface_key = huggingface_key or os.environ.get('HUGGINGFACE_API_KEY', '')
        self.siliconflow_key = siliconflow_key or os.environ.get('SILICONFLOW_API_KEY', '')
        self.cloudflare_account_id = cloudflare_account_id or os.environ.get('CLOUDFLARE_ACCOUNT_ID', '')
        self.cloudflare_token = cloudflare_token or os.environ.get('CLOUDFLARE_API_TOKEN', '')
        
        # Create the provider manager with automatic failover for AI generation
        generated_dir = self.output_dir / 'generated'
        self.provider_manager = create_default_manager(
            huggingface_key=self.huggingface_key,
            siliconflow_key=self.siliconflow_key,
            cloudflare_account_id=self.cloudflare_account_id,
            cloudflare_token=self.cloudflare_token,
            output_dir=str(generated_dir)
        )
        
        print(f"✅ FootageGeneratorV2 initialized with provider architecture")
        print(f"   - AI Providers: {len(self.provider_manager.providers)} (Pollinations + HuggingFace + Picsum fallback)")
        print(f"   - Stock APIs: Pexels={'✅' if self.pexels_key else '❌'}, Pixabay={'✅' if self.pixabay_key else '❌'}")
        print(f"   - Architecture: Fully decoupled with automatic failover")
    
    def generate_image(self, prompt: str, style: str = 'photorealistic',
                       aspect_ratio: str = '9:16') -> str:
        """
        Generate an image using available providers with automatic failover.
        
        Args:
            prompt: Image description
            style: Style preset (photorealistic, cinematic, artistic, etc.)
            aspect_ratio: Target aspect ratio ('9:16', '16:9', '1:1')
            
        Returns:
            Path to generated image
            
        Raises:
            Exception if all providers fail
        """
        # Map aspect ratio to dimensions
        size_map = {
            '9:16': (1080, 1920),   # TikTok/Reels
            '16:9': (1920, 1080),   # YouTube
            '1:1': (1080, 1080),    # Square
        }
        width, height = size_map.get(aspect_ratio, (1080, 1920))
        
        # Generate with automatic failover
        result = self.provider_manager.generate_image(
            prompt=prompt,
            width=width,
            height=height,
            style=style
        )
        
        if result.success:
            return result.image_path
        else:
            raise Exception(f"Image generation failed: {result.error_message}")
    
    def generate_images_batch(self, prompts: List[str], style: str = 'photorealistic',
                              aspect_ratio: str = '9:16', delay: float = 1.0) -> List[str]:
        """
        Generate multiple images with automatic failover for each.
        
        Args:
            prompts: List of image descriptions
            style: Style for all images
            aspect_ratio: Target aspect ratio
            delay: Seconds between generations (for rate limiting)
            
        Returns:
            List of paths to generated images (successful ones only)
        """
        size_map = {
            '9:16': (1080, 1920),
            '16:9': (1920, 1080),
            '1:1': (1080, 1080),
        }
        width, height = size_map.get(aspect_ratio, (1080, 1920))
        
        results = self.provider_manager.generate_images_batch(
            prompts=prompts,
            width=width,
            height=height,
            style=style,
            delay_between=delay
        )
        
        # Return only successful paths
        paths = [r.image_path for r in results if r.success]
        
        if len(paths) < len(prompts):
            failed = len(prompts) - len(paths)
            print(f"⚠️  {failed} images failed to generate")
        
        return paths
    
    def get_stats(self) -> Dict:
        """Get generation statistics."""
        return self.provider_manager.get_stats()


# Backwards compatibility alias
FootageGenerator = FootageGeneratorV2


# Convenience function
def generate_image_with_failover(prompt: str, style: str = 'photorealistic',
                                  huggingface_key: str = None,
                                  siliconflow_key: str = None) -> str:
    """
    Quick function to generate an image with automatic failover.
    
    Args:
        prompt: Image description
        style: Style preset
        huggingface_key: Optional HF key for additional providers
        siliconflow_key: Optional SiliconFlow key
        
    Returns:
        Path to generated image
    """
    gen = FootageGeneratorV2(huggingface_key=huggingface_key, siliconflow_key=siliconflow_key)
    return gen.generate_image(prompt, style)


if __name__ == '__main__':
    # Test the new decoupled architecture
    print("Testing FootageGeneratorV2 with automatic failover...\n")
    
    gen = FootageGeneratorV2()
    
    test_prompts = [
        "A futuristic AI computer in a modern office",
        "A cute puppy dog playing in a garden",
        "A scenic mountain landscape at sunset"
    ]
    
    print(f"\nGenerating {len(test_prompts)} test images...\n")
    
    try:
        paths = gen.generate_images_batch(test_prompts, delay=2.0)
        print(f"\n✅ Successfully generated {len(paths)} images:")
        for p in paths:
            print(f"   - {p}")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    
    # Show stats
    stats = gen.get_stats()
    print(f"\n📊 Stats: {stats}")
