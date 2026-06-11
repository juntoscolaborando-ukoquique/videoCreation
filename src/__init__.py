"""
VideoCreation — Configurable video generation pipeline.

Accepts speech text, visual assets, and styling options to produce a complete video file.
TTS runs via edge_tts; AI image generation uses Cloudflare/SiliconFlow with Picsum and Pillow fallbacks.
"""

from src.schema import VideoConfiguration, VisualAssetType, VisualAssetConfig, OutputFormat

__all__ = [
    "VideoConfiguration",
    "VisualAssetType",
    "VisualAssetConfig",
    "OutputFormat",
]
