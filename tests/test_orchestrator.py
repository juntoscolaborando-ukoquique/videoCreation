"""
Tests for VideoOrchestrator via VideoGateway injection.

No module-level patching. Each test builds a VideoGateway from plain
callables and passes it directly to VideoOrchestrator.
"""

import os
import pytest
from pathlib import Path
from unittest.mock import MagicMock, call

from src.schema import (
    VideoConfiguration,
    VisualAssetConfig,
    VisualAssetType,
    OutputFormat,
)
from src.gateway import VideoGateway
from src.orchestrator import VideoOrchestrator
from src.utils import sanitize_filename


# --------------------------------------------------------------------------- #
# Callable stubs
# --------------------------------------------------------------------------- #

def _stub_generate_speech(text, output_path, **kwargs):
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    Path(output_path).write_text("fake-audio")
    return output_path


def _stub_generate_images(prompts, output_dir, **kwargs):
    from PIL import Image
    os.makedirs(output_dir, exist_ok=True)
    paths = []
    for i, _ in enumerate(prompts):
        p = os.path.join(output_dir, f"gen_{i}.png")
        Image.new("RGB", (64, 64), (100, 100, 100)).save(p)
        paths.append(p)
    return paths


def _stub_copy_images(image_paths, output_dir):
    import shutil
    os.makedirs(output_dir, exist_ok=True)
    copied = []
    for src in image_paths:
        if os.path.isfile(src):
            dst = os.path.join(output_dir, os.path.basename(src))
            shutil.copy2(src, dst)
            copied.append(dst)
    return copied


def _stub_assemble_video(audio_path, visual_files, **kwargs):
    output_dir = kwargs.get("output_dir", "/tmp")
    fmt = kwargs.get("output_format", "mp4")
    title = kwargs.get("title", "test")
    os.makedirs(output_dir, exist_ok=True)
    out = os.path.join(output_dir, f"{sanitize_filename(title)}.{fmt}")
    Path(out).write_text("fake-video")
    return out


def _stub_generate_subtitles(text, **kwargs):
    return [{"text": "Hello", "start": 0.0, "end": 1.0}]


def _stub_burn_subtitles(video_path, segments, **kwargs):
    return video_path


def _stub_modify_images(image_paths, instructions):
    return image_paths


def _stub_video_dimensions():
    return 1080, 1920


# --------------------------------------------------------------------------- #
# Gateway factory
# --------------------------------------------------------------------------- #

def _make_gateway(**overrides) -> VideoGateway:
    """Build a fully-stubbed VideoGateway, with optional per-field overrides."""
    defaults = dict(
        generate_speech=_stub_generate_speech,
        generate_images=_stub_generate_images,
        copy_images=_stub_copy_images,
        assemble_video=_stub_assemble_video,
        generate_subtitles=_stub_generate_subtitles,
        burn_subtitles=_stub_burn_subtitles,
        modify_images=_stub_modify_images,
        video_dimensions=_stub_video_dimensions,
    )
    defaults.update(overrides)
    return VideoGateway(**defaults)


def _make_orch(tmp_output_dir, **gateway_overrides) -> tuple:
    gw = _make_gateway(**gateway_overrides)
    orch = VideoOrchestrator(output_dir=tmp_output_dir, gateway=gw)
    return orch, gw


# --------------------------------------------------------------------------- #
# Test Flows
# --------------------------------------------------------------------------- #

class TestMinimalVideo:
    def test_minimal_video(self, sample_images, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="Minimal",
            speech_content="Short test sentence.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images[:1],
            ),
        )
        result = orch.create_video(cfg)

        assert result.output_path.endswith(".mp4")
        assert result.title == "Minimal"
        assert result.subtitles_enabled is False
        assert os.path.isfile(result.output_path)


class TestAIImageGeneration:
    def test_ai_image_prompts(self, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="AI Images",
            speech_content="Testing AI image generation from prompts.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.TEXT_PROMPTS,
                prompts=["A futuristic city", "A forest at dawn"],
            ),
        )
        result = orch.create_video(cfg)
        assert os.path.isfile(result.output_path)


class TestVideoWithSubtitles:
    def test_subtitles(self, sample_images, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="Subtitled",
            speech_content="This video should have burned-in subtitles.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            subtitles_enabled=True,
            length_seconds=10.0,
        )
        result = orch.create_video(cfg)
        assert result.subtitles_enabled is True
        assert os.path.isfile(result.output_path)


class TestWithBackgroundMusic:
    def test_background_music(self, sample_images, sample_audio, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="With Music",
            speech_content="Testing background music integration.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            background_music=sample_audio,
        )
        result = orch.create_video(cfg)
        assert os.path.isfile(result.output_path)

    def test_background_music_forwarded_to_assemble(self, sample_images, sample_audio, tmp_output_dir):
        mock_assemble = MagicMock(side_effect=_stub_assemble_video)
        orch, _ = _make_orch(tmp_output_dir, assemble_video=mock_assemble)
        cfg = VideoConfiguration(
            title="Music Forward Test",
            speech_content="With background music.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            background_music=sample_audio,
        )
        orch.create_video(cfg)
        _, kwargs = mock_assemble.call_args
        assert kwargs.get("background_music") == sample_audio


class TestCustomOutputFormat:
    def test_webm_output(self, sample_images, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="WebM Test",
            speech_content="Output as WebM format.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            output_format=OutputFormat.WEBM,
        )
        result = orch.create_video(cfg)
        assert result.format == "webm"
        assert result.output_path.endswith(".webm")
        assert os.path.isfile(result.output_path)


class TestImageModification:
    def test_modify_images_called_with_instructions(self, sample_images, tmp_output_dir):
        mock_modify = MagicMock(side_effect=_stub_modify_images)
        orch, _ = _make_orch(tmp_output_dir, modify_images=mock_modify)
        cfg = VideoConfiguration(
            title="Modified",
            speech_content="Test image modification.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            image_modification_instructions="Apply sepia filter",
        )
        result = orch.create_video(cfg)
        mock_modify.assert_called_once()
        assert mock_modify.call_args[0][1] == "Apply sepia filter"
        assert os.path.isfile(result.output_path)

    def test_modify_images_not_called_without_instructions(self, sample_images, tmp_output_dir):
        mock_modify = MagicMock(side_effect=_stub_modify_images)
        orch, _ = _make_orch(tmp_output_dir, modify_images=mock_modify)
        cfg = VideoConfiguration(
            title="No Modify",
            speech_content="No modification instructions.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
        )
        orch.create_video(cfg)
        mock_modify.assert_not_called()


class TestSubtitleBurnIn:
    def test_burn_subtitles_called_when_enabled(self, sample_images, tmp_output_dir):
        mock_burn = MagicMock(side_effect=_stub_burn_subtitles)
        orch, _ = _make_orch(tmp_output_dir, burn_subtitles=mock_burn)
        cfg = VideoConfiguration(
            title="Burn Test",
            speech_content="Testing subtitle burn-in.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            subtitles_enabled=True,
            length_seconds=10.0,
        )
        orch.create_video(cfg)
        mock_burn.assert_called_once()

    def test_burn_subtitles_not_called_when_disabled(self, sample_images, tmp_output_dir):
        mock_burn = MagicMock(side_effect=_stub_burn_subtitles)
        orch, _ = _make_orch(tmp_output_dir, burn_subtitles=mock_burn)
        cfg = VideoConfiguration(
            title="No Burn Test",
            speech_content="No subtitle burn-in.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            subtitles_enabled=False,
        )
        orch.create_video(cfg)
        mock_burn.assert_not_called()

    def test_subtitle_output_has_clean_filename(self, sample_images, tmp_output_dir):
        """Final promoted video must use the clean title-based name, not a subtitled_ prefix."""
        import uuid

        def _burn_with_prefix(video_path, segments, output_dir, output_filename, **kwargs):
            prefixed = os.path.join(output_dir, f"subtitled_{uuid.uuid4().hex[:8]}_{output_filename}")
            Path(video_path).rename(prefixed) if Path(video_path).exists() else Path(prefixed).write_text("fake")
            return prefixed

        orch, _ = _make_orch(tmp_output_dir, burn_subtitles=_burn_with_prefix)
        cfg = VideoConfiguration(
            title="Clean Name",
            speech_content="Some speech content here.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            subtitles_enabled=True,
            length_seconds=10.0,
        )
        result = orch.create_video(cfg)
        filename = Path(result.output_path).name
        assert not filename.startswith("subtitled_"), f"Got prefixed name: {filename}"
        assert filename == "Clean_Name.mp4"


class TestSubtitleDurationGuard:
    def test_raises_when_duration_unknown(self, sample_images, tmp_output_dir):
        from unittest.mock import patch
        with patch("moviepy.AudioFileClip", side_effect=Exception("ffmpeg not found")):
            orch, _ = _make_orch(tmp_output_dir)
            cfg = VideoConfiguration(
                title="No Duration",
                speech_content="Some text.",
                visual_assets=VisualAssetConfig(
                    asset_type=VisualAssetType.IMAGE_SEQUENCE,
                    images=sample_images,
                ),
                subtitles_enabled=True,
            )
            with pytest.raises(RuntimeError, match="Could not determine video duration"):
                orch.create_video(cfg)


class TestNoVisualsRaises:
    def test_empty_images(self, tmp_output_dir):
        orch, _ = _make_orch(tmp_output_dir)
        cfg = VideoConfiguration(
            title="Empty",
            speech_content="No visuals here.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=[],
            ),
        )
        with pytest.raises(ValueError, match="No visual assets"):
            orch.create_video(cfg)


class TestHorizontalOrientation:
    def test_horizontal_orientation(self, tmp_output_dir):
        from src.schema import Orientation
        mock_gen = MagicMock(side_effect=_stub_generate_images)
        mock_assemble = MagicMock(side_effect=_stub_assemble_video)
        orch, _ = _make_orch(tmp_output_dir, generate_images=mock_gen, assemble_video=mock_assemble)
        cfg = VideoConfiguration(
            title="Horizontal Video",
            speech_content="Testing horizontal.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.TEXT_PROMPTS,
                prompts=["A landscape"],
            ),
            orientation=Orientation.HORIZONTAL,
        )
        orch.create_video(cfg)

        _, kwargs_gen = mock_gen.call_args
        assert kwargs_gen.get("aspect_ratio") == "16:9"
        assert kwargs_gen.get("width") == 1920
        assert kwargs_gen.get("height") == 1080

        _, kwargs_asm = mock_assemble.call_args
        assert kwargs_asm.get("width") == 1920
        assert kwargs_asm.get("height") == 1080


class TestTtsVoicePerVideo:
    def test_explicit_voice_forwarded(self, sample_images, tmp_output_dir):
        mock_tts = MagicMock(side_effect=_stub_generate_speech)
        orch, _ = _make_orch(tmp_output_dir, generate_speech=mock_tts)
        cfg = VideoConfiguration(
            title="Voice Test",
            speech_content="Testing explicit voice.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            tts_voice="es-AR-ElenaNeural",
            language="es",
        )
        orch.create_video(cfg)
        _, kwargs = mock_tts.call_args
        assert kwargs.get("voice") == "es-AR-ElenaNeural"

    def test_no_voice_field_passes_none(self, sample_images, tmp_output_dir):
        mock_tts = MagicMock(side_effect=_stub_generate_speech)
        orch, _ = _make_orch(tmp_output_dir, generate_speech=mock_tts)
        cfg = VideoConfiguration(
            title="No Voice Test",
            speech_content="No explicit voice.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            language="es",
        )
        orch.create_video(cfg)
        _, kwargs = mock_tts.call_args
        assert kwargs.get("voice") is None


class TestDIConfigIsolation:
    def test_two_orchestrators_different_tts_voices(self, sample_images, tmp_path):
        """Each gateway's closure must carry its own config — no shared state."""
        from src.config_loader import ConfigLoader

        recorded = {}

        def make_speech_recorder(label):
            def _speech(text, output_path, **kwargs):
                recorded[label] = kwargs.get("voice")
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                Path(output_path).write_text("fake-audio")
                return output_path
            return _speech

        out_a = str(tmp_path / "a")
        out_b = str(tmp_path / "b")

        gw_a = _make_gateway(generate_speech=make_speech_recorder("a"))
        gw_b = _make_gateway(generate_speech=make_speech_recorder("b"))

        orch_a = VideoOrchestrator(output_dir=out_a, gateway=gw_a)
        orch_b = VideoOrchestrator(output_dir=out_b, gateway=gw_b)

        cfg_a = VideoConfiguration(
            title="DI A",
            speech_content="Test.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            tts_voice="voice-A",
        )
        cfg_b = VideoConfiguration(
            title="DI B",
            speech_content="Test.",
            visual_assets=VisualAssetConfig(
                asset_type=VisualAssetType.IMAGE_SEQUENCE,
                images=sample_images,
            ),
            tts_voice="voice-B",
        )
        orch_a.create_video(cfg_a)
        orch_b.create_video(cfg_b)

        assert recorded["a"] == "voice-A"
        assert recorded["b"] == "voice-B"
