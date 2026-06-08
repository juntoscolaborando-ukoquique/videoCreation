"""Quick smoke test using Cloudflare Workers AI for image generation."""

import logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from src.schema import VideoConfiguration, VisualAssetConfig, VisualAssetType, ImageEngine
from src.orchestrator import VideoOrchestrator

if __name__ == "__main__":
    config = VideoConfiguration(
        title="Cloudflare AI Test",
        speech_content=(
            "This is a test of the Cloudflare Workers AI image generation. "
            "The images you see were created by FLUX, running on Cloudflare's global network. "
            "The pipeline is working perfectly."
        ),
        visual_assets=VisualAssetConfig(
            asset_type=VisualAssetType.TEXT_PROMPTS,
            prompts=[
                "A futuristic city skyline at night with neon lights, cinematic",
                "A close-up of glowing code on a dark monitor screen, cyberpunk style",
            ],
        ),
        image_engine=ImageEngine.CLOUDFLARE,
        subtitles_enabled=True,
        length_seconds=12.0,
    )

    from pathlib import Path
    project_root = Path(__file__).resolve().parent
    orchestrator = VideoOrchestrator(output_dir=str(project_root / "output"))
    result = orchestrator.create_video(config)
    print(f"\nDone: {result['output_path']}")
