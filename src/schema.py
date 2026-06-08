from pydantic import BaseModel, Field
from typing import Dict, List, Optional
from enum import Enum


class OutputFormat(str, Enum):
    MP4 = "mp4"
    MOV = "mov"
    AVI = "avi"
    WEBM = "webm"


class VisualAssetType(str, Enum):
    IMAGE_SEQUENCE = "image_sequence"
    TEXT_PROMPTS = "text_prompts"


class TTSBackend(str, Enum):
    EDGE_TTS = "edge_tts"
    AZURE = "azure"
    OPENAI = "openai"
    FISH_TTS = "fish_tts"


class Language(str, Enum):
    ENGLISH = "en"
    SPANISH = "es"
    CHINESE = "zh"
    FRENCH = "fr"
    GERMAN = "de"
    PORTUGUESE = "pt"


class Orientation(str, Enum):
    VERTICAL = "vertical"
    HORIZONTAL = "horizontal"


class ImageEngine(str, Enum):
    POLLINATIONS = "pollinations"
    HUGGINGFACE  = "huggingface"
    CLOUDFLARE   = "cloudflare"
    SILICONFLOW  = "siliconflow"
    PICSUM       = "picsum"
    UNSPLASH     = "unsplash"
    PEXELS       = "pexels"


class VisualAssetConfig(BaseModel):
    asset_type: VisualAssetType
    images: Optional[List[str]] = Field(
        default=None,
        description="Paths to local image files if using IMAGE_SEQUENCE",
    )
    prompts: Optional[List[str]] = Field(
        default=None,
        description="Text prompts for AI image generation if using TEXT_PROMPTS",
    )
    uploaded_images: Optional[Dict[str, bytes]] = Field(
        default=None,
        description="In-memory image uploads keyed by filename (used by the UI)",
    )


class VideoConfiguration(BaseModel):
    title: str = Field(..., description="The title of the video")
    length_seconds: Optional[float] = Field(
        default=None, description="Desired video length in seconds"
    )
    speech_content: str = Field(..., description="Plain text to be converted to audio")
    background_music: Optional[str] = Field(
        default=None, description="Path to background music audio file"
    )
    visual_assets: VisualAssetConfig = Field(..., description="Visual assets configuration")
    image_modification_instructions: Optional[str] = Field(
        default=None, description="Optional AI instructions to modify images"
    )
    subtitles_enabled: bool = Field(
        default=False, description="Toggle to burn subtitles onto the video"
    )
    output_format: OutputFormat = Field(
        default=OutputFormat.MP4, description="Output video format"
    )
    orientation: Orientation = Field(
        default=Orientation.VERTICAL, description="Video orientation (vertical or horizontal)"
    )
    # Per-video provider overrides — take precedence over default_config.yaml
    language: Language = Field(
        default=Language.ENGLISH,
        description="Language for TTS voice selection",
    )
    tts_backend: Optional[TTSBackend] = Field(
        default=None,
        description="TTS backend to use for this video (overrides config default)",
    )
    image_engine: Optional[ImageEngine] = Field(
        default=None,
        description="Image generation engine for this video (overrides config default)",
    )
    image_style: Optional[str] = Field(
        default=None,
        description="Image style preset for this video, e.g. 'cinematic' (overrides config default)",
    )
    tts_rate: Optional[str] = Field(
        default=None,
        description="Speaking rate for this video, e.g. '-10%' (overrides config default)",
    )
