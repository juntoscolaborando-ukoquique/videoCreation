import warnings
from dataclasses import dataclass

from pydantic import BaseModel, Field, field_serializer, model_validator, ConfigDict
from typing import Dict, List, Optional
from enum import Enum
import base64


@dataclass
class PipelineResult:
    output_path: str
    title: str
    format: str
    subtitles_enabled: bool


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

    @field_serializer("uploaded_images")
    def serialize_uploaded_images(self, value: Optional[Dict[str, bytes]]) -> Optional[Dict[str, str]]:
        """Base64-encode bytes values so model_dump(mode='json') doesn't raise."""
        if value is None:
            return None
        return {k: base64.b64encode(v).decode("ascii") for k, v in value.items()}


class VideoConfiguration(BaseModel):
    model_config = ConfigDict(extra="forbid")

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
    tts_voice: Optional[str] = Field(
        default=None,
        description="Explicit TTS voice for this video, e.g. 'es-AR-ElenaNeural'. "
                    "Overrides language default and config default.",
    )

    @model_validator(mode="after")
    def warn_unimplemented_image_modification(self) -> "VideoConfiguration":
        if self.image_modification_instructions is not None:
            warnings.warn(
                "image_modification_instructions is set but modify_images() is not yet "
                "implemented. The pipeline will raise NotImplementedError at step 4. "
                "Remove image_modification_instructions from your config to proceed.",
                UserWarning,
                stacklevel=2,
            )
        return self
