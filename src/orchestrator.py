"""
Video Orchestrator — pure pipeline logic.

The orchestrator knows only ``VideoGateway`` (what to call) and
``VideoConfiguration`` / ``PipelineResult`` (the data contracts).
It imports no adapter module directly; all I/O is injected via the gateway.

Usage::

    from src.gateway import VideoGateway
    from src.orchestrator import VideoOrchestrator
    from src.schema import VideoConfiguration, VisualAssetConfig, VisualAssetType

    config = VideoConfiguration(
        title="My Video",
        speech_content="Hello world, this is a test.",
        visual_assets=VisualAssetConfig(
            asset_type=VisualAssetType.TEXT_PROMPTS,
            prompts=["A sunny beach"],
        ),
    )
    orchestrator = VideoOrchestrator(output_dir="output")
    result = orchestrator.create_video(config)
    print(result.output_path)
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Dict, List, Optional

from src.schema import VideoConfiguration, VisualAssetType, Orientation, PipelineResult
from src.gateway import VideoGateway
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)


class VideoOrchestrator:
    """End-to-end video creation pipeline.

    All external I/O is performed through the injected ``VideoGateway``.
    The orchestrator contains no adapter imports and reads no config directly.
    """

    def __init__(
        self,
        output_dir: str = "output",
        gateway: Optional[VideoGateway] = None,
        # Legacy parameters kept for backward compatibility —
        # prefer passing a fully-wired VideoGateway instead.
        config_loader=None,
        subtitle_backend=None,
        assembler_backend=None,
    ):
        """
        Parameters
        ----------
        output_dir:
            Base directory for all output files. Use an absolute path when
            calling from threads or subprocesses.
        gateway:
            Pre-wired ``VideoGateway``. When ``None``, ``VideoGateway.default()``
            is called with *config_loader* (if provided) to build one.
        config_loader:
            Passed to ``VideoGateway.default()`` when *gateway* is ``None``.
            Ignored when a gateway is supplied directly.
        subtitle_backend:
            Ignored in all cases — subtitle backend is now wired inside
            ``VideoGateway.default()``. Pass a custom *gateway* to swap it.
        assembler_backend:
            When *gateway* is ``None``, forwarded as ``backend=`` to
            ``assemble_video`` on every call, allowing the moviepy local path
            to be replaced by an alternative ``AssemblerBackend`` without a
            full custom gateway. Ignored when a gateway is supplied directly.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        if gateway is not None:
            self._gateway = gateway
        else:
            self._gateway = VideoGateway.default(config_loader=config_loader)

        # Store the assembler_backend so the default gateway can forward it
        # when the legacy parameter is used without a custom gateway.
        self._assembler_backend = assembler_backend

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def create_video(self, config: VideoConfiguration) -> PipelineResult:
        """Run the full pipeline and return a ``PipelineResult``."""
        logger.info("=== Starting video generation: %s ===", config.title)

        # 1. Prepare workspace
        workspace = self.output_dir / sanitize_filename(config.title)
        workspace.mkdir(parents=True, exist_ok=True)

        # 2. Generate TTS audio
        audio_path = str(workspace / "speech.mp3")
        logger.info("[1/4] Generating TTS audio …")
        self._gateway.generate_speech(
            config.speech_content,
            audio_path,
            voice=config.tts_voice,
            language=config.language.value,
            method=config.tts_backend.value if config.tts_backend else None,
            rate=config.tts_rate,
        )

        # 3. Resolve orientation dimensions
        # Read dimensions from config via the gateway's closure; fall back to
        # defaults here so the orchestrator stays config-free.
        final_width, final_height, aspect_ratio = self._resolve_dimensions(config)

        # 4. Prepare visual assets
        logger.info("[2/4] Preparing visual assets …")
        visual_files = self._prepare_visuals(config, str(workspace), aspect_ratio, final_width, final_height)

        if not visual_files:
            raise ValueError("No visual assets available. Provide images or text prompts.")

        # 5. (Optional) Modify images with AI
        if config.image_modification_instructions:
            logger.info("[+] Applying image modifications …")
            visual_files = self._gateway.modify_images(
                visual_files, config.image_modification_instructions,
            )
        else:
            logger.debug("Image modifications skipped (no instructions provided).")

        # 6. Generate subtitle segments
        segments: List[Dict] = []
        if config.subtitles_enabled:
            logger.info("[3/4] Generating subtitle segments …")
            total_duration = self._resolve_audio_duration(config, audio_path)
            segments = self._gateway.generate_subtitles(
                config.speech_content,
                total_duration=total_duration,
            )
        else:
            logger.debug("Subtitles disabled — skipping.")

        # 7. Assemble final video
        logger.info("[4/4] Assembling final video …")
        output_path = self._gateway.assemble_video(
            audio_path,
            visual_files,
            title=config.title,
            output_dir=str(workspace),
            output_format=config.output_format.value,
            background_music=config.background_music,
            width=final_width,
            height=final_height,
            backend=self._assembler_backend,
        )

        if not output_path or not os.path.exists(output_path):
            raise RuntimeError(f"Video assembly failed: output file not found at {output_path}")

        # 8. (Optional) Burn subtitles
        if config.subtitles_enabled and segments:
            output_path = self._burn_subtitles(
                output_path, segments, workspace, config, final_width, final_height,
            )

        # 9. Promote final video out of workspace into output_dir
        final_filename = Path(output_path).name
        final_path = self.output_dir / final_filename
        if Path(output_path).resolve() != final_path.resolve():
            shutil.move(output_path, final_path)
            logger.info("Video promoted → %s", final_path)
            output_path = str(final_path)

        logger.info("=== Video complete: %s ===", output_path)

        # 10. Cleanup workspace
        self._cleanup_workspace(workspace)

        return PipelineResult(
            output_path=output_path,
            title=config.title,
            format=config.output_format.value,
            subtitles_enabled=config.subtitles_enabled,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _resolve_dimensions(self, config: VideoConfiguration):
        """Return (width, height, aspect_ratio) based on orientation."""
        base_w, base_h = self._gateway.video_dimensions()
        v_width, v_height = min(base_w, base_h), max(base_w, base_h)
        if config.orientation == Orientation.HORIZONTAL:
            return v_height, v_width, "16:9"
        return v_width, v_height, "9:16"

    def _resolve_audio_duration(self, config: VideoConfiguration, audio_path: str) -> float:
        """Return audio duration in seconds, raising if it cannot be determined."""
        total_duration = config.length_seconds
        if total_duration is None:
            try:
                from moviepy import AudioFileClip
                audio = AudioFileClip(audio_path)
                total_duration = audio.duration
                audio.close()
                logger.info("Measured audio duration: %.2fs", total_duration)
            except Exception as exc:
                logger.warning("Could not measure audio duration (%s).", exc)

        if total_duration is None:
            raise RuntimeError(
                "Could not determine video duration: set 'length_seconds' in your config "
                "or ensure the generated audio file is readable by ffmpeg."
            )
        return total_duration

    def _burn_subtitles(
        self,
        output_path: str,
        segments: List[Dict],
        workspace: Path,
        config: VideoConfiguration,
        width: int,
        height: int,
    ) -> str:
        logger.info("[+] Burning subtitles …")
        output_filename = f"{sanitize_filename(config.title)}.{config.output_format.value}"
        burned = self._gateway.burn_subtitles(
            output_path,
            segments,
            output_dir=str(workspace),
            output_filename=output_filename,
            output_format=config.output_format.value,
            width=width,
            height=height,
        )
        if not burned or not os.path.exists(burned):
            raise RuntimeError("Subtitle burn-in failed: output file not found.")

        # Rename to the clean title-based filename if the backend added a prefix.
        clean_path = workspace / output_filename
        if clean_path.exists() and clean_path.resolve() != Path(burned).resolve():
            clean_path.unlink()
        if Path(burned).resolve() != clean_path.resolve():
            shutil.move(burned, clean_path)
            burned = str(clean_path)
        return burned

    def _cleanup_workspace(self, workspace: Path) -> None:
        temp_dir = workspace / "temp"
        if temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        for transient in workspace.glob("*TEMP_MPY*"):
            try:
                transient.unlink()
            except Exception as exc:
                logger.warning("Could not remove transient file %s: %s", transient, exc)

    def _save_uploaded_images(self, uploads: dict, dest_dir: str) -> List[str]:
        saved: List[str] = []
        for filename, data in uploads.items():
            path = os.path.join(dest_dir, filename)
            with open(path, "wb") as f:
                f.write(data)
            logger.info("Saved uploaded image → %s", path)
            saved.append(path)
        return saved

    def _prepare_visuals(
        self, config: VideoConfiguration, workspace: str,
        aspect_ratio: str, width: int, height: int,
    ) -> List[str]:
        visuals_dir = os.path.join(workspace, "visuals")
        os.makedirs(visuals_dir, exist_ok=True)

        if config.visual_assets.asset_type == VisualAssetType.IMAGE_SEQUENCE:
            images = list(config.visual_assets.images or [])
            if config.visual_assets.uploaded_images:
                images.extend(self._save_uploaded_images(config.visual_assets.uploaded_images, visuals_dir))
            if not images:
                logger.warning("IMAGE_SEQUENCE selected but no images provided.")
                return []
            return self._gateway.copy_images(images, visuals_dir)

        prompts = config.visual_assets.prompts or []
        if not prompts:
            logger.warning("TEXT_PROMPTS selected but no prompts provided.")
            return []
        return self._gateway.generate_images(
            prompts,
            visuals_dir,
            style=config.image_style,
            engine=config.image_engine.value if config.image_engine else None,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
        )
