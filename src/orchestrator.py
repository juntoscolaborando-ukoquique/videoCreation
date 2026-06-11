"""
Video Orchestrator — main pipeline that ties all adapters together.

Usage::

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
    # Recommended: Use an absolute path for output_dir to ensure stability
    orchestrator = VideoOrchestrator(output_dir="output")
    result = orchestrator.create_video(config)
    print(result["output_path"])
"""

import logging
import os
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional

from src.schema import VideoConfiguration, VisualAssetType, Orientation
from src import tts_adapter, image_adapter, subtitle_adapter, assembler_adapter
from src import config_loader as _default_config_loader
from src.config_loader import ConfigLoader
from src.backends import AssemblerBackend, SubtitleBackend
from src.backends.ffmpeg_subtitle_backend import FFmpegSubtitleBackend
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)


class VideoOrchestrator:
    """End-to-end video creation pipeline.

    Each step delegates to a specialised adapter module so that
    backends can be swapped independently.
    """

    def __init__(
        self,
        output_dir: str = "output",
        subtitle_backend: SubtitleBackend = None,
        assembler_backend: AssemblerBackend = None,
        config_loader: ConfigLoader = None,
    ):
        """
        Parameters
        ----------
        output_dir:
            Base directory for all output files. Relative paths are resolved
            against the current working directory at instantiation time — use
            an absolute path when calling from threads or subprocesses.
        subtitle_backend:
            Backend used for subtitle burn-in. Defaults to
            ``FFmpegSubtitleBackend``. Pass an alternative to swap renderers
            or inject a mock in tests.
        assembler_backend:
            Backend used for video assembly. Defaults to ``None``, which
            causes ``assemble_video`` to use the local moviepy implementation.
            Pass an alternative to swap assemblers or inject a mock in tests.
        config_loader:
            ``ConfigLoader`` instance to use for this orchestrator. Defaults
            to the module-level singleton. Only affects orchestrator-level
            config reads (e.g. output dimensions). Note: adapters
            (tts_adapter, image_adapter, etc.) read config from the
            module-level singleton directly and are not affected by this
            parameter. In practice this is fine — there is only ever one
            config file per process. For parallel batch scenarios, use
            separate processes rather than threads.
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self._subtitle_backend: SubtitleBackend = (
            subtitle_backend if subtitle_backend is not None else FFmpegSubtitleBackend()
        )
        self._assembler_backend: Optional[AssemblerBackend] = assembler_backend
        self._config = config_loader if config_loader is not None else _default_config_loader

    # ------------------------------------------------------------------
    # Public
    # ------------------------------------------------------------------

    def create_video(self, config: VideoConfiguration) -> Dict[str, Any]:
        """Run the full pipeline and return a result dict.

        Returns
        -------
        dict
            Keys: ``output_path``, ``title``, ``format``, ``subtitles_enabled``.
            The final video is always at ``output_path`` inside ``output_dir``.
        """
        logger.info("=== Starting video generation: %s ===", config.title)

        # 1. Prepare workspace
        workspace = self.output_dir / sanitize_filename(config.title)
        workspace.mkdir(parents=True, exist_ok=True)

        # 2. Generate audio from speech text
        audio_path = str(workspace / "speech.mp3")
        logger.info("[1/4] Generating TTS audio …")
        tts_adapter.generate_speech(
            text=config.speech_content,
            output_path=audio_path,
            language=config.language.value,
            method=config.tts_backend.value if config.tts_backend else None,
            rate=config.tts_rate,
        )

        # Determine orientation dimensions
        cfg = self._config.video()
        base_w = cfg.get("width", 1080)
        base_h = cfg.get("height", 1920)
        v_width, v_height = min(base_w, base_h), max(base_w, base_h)
        
        if config.orientation == Orientation.HORIZONTAL:
            final_width, final_height = v_height, v_width
            aspect_ratio = "16:9"
        else:
            final_width, final_height = v_width, v_height
            aspect_ratio = "9:16"

        # 3. Prepare visual assets
        logger.info("[2/4] Preparing visual assets …")
        visual_files = self._prepare_visuals(config, str(workspace), aspect_ratio, final_width, final_height)

        if not visual_files:
            raise ValueError(
                "No visual assets available. Provide images or text prompts."
            )

        # 4. (Optional) Modify images with AI
        if config.image_modification_instructions:
            logger.info("[+] Applying image modifications …")
            visual_files = image_adapter.modify_images(
                visual_files, config.image_modification_instructions,
            )
        else:
            logger.debug("Image modifications skipped (no instructions provided).")

        # 5. Generate subtitle segments
        segments: List[Dict] = []
        if config.subtitles_enabled:
            logger.info("[3/4] Generating subtitle segments …")
            
            # Determine total duration for subtitle scaling
            total_duration = config.length_seconds
            if total_duration is None:
                try:
                    from moviepy import AudioFileClip
                    audio = AudioFileClip(audio_path)
                    total_duration = audio.duration
                    audio.close()
                    logger.info("Measured audio duration: %.2fs", total_duration)
                except Exception as exc:
                    logger.warning("Could not measure audio duration (%s) — falling back to estimation.", exc)

            segments = subtitle_adapter.generate_subtitle_segments(
                text=config.speech_content,
                total_duration=total_duration,
            )
        else:
            logger.debug("Subtitles disabled — skipping.")

        # 6. Assemble final video
        logger.info("[4/4] Assembling final video …")
        output_path = assembler_adapter.assemble_video(
            audio_path=audio_path,
            visual_files=visual_files,
            title=config.title,
            output_dir=str(workspace),
            output_format=config.output_format.value,
            background_music=config.background_music,
            width=final_width,
            height=final_height,
            backend=self._assembler_backend,
        )

        if not output_path or not os.path.exists(output_path):
            raise RuntimeError(
                f"Video assembly failed: output file not found at {output_path}"
            )

        # 7. (Optional) Burn subtitles onto the assembled video
        if config.subtitles_enabled and segments:
            logger.info("[+] Burning subtitles …")
            output_filename = f"{sanitize_filename(config.title)}.{config.output_format.value}"
            output_path = self._subtitle_backend.burn_subtitles(
                video_path=output_path,
                segments=segments,
                output_dir=str(workspace),
                output_filename=output_filename,
                output_format=config.output_format.value,
                width=final_width,
                height=final_height,
            )
            if not output_path or not os.path.exists(output_path):
                raise RuntimeError("Subtitle burn-in failed: output file not found.")

        # 8. Promote final video out of the workspace into output_dir
        final_filename = Path(output_path).name
        final_path = self.output_dir / final_filename
        if Path(output_path).resolve() != final_path.resolve():
            shutil.move(output_path, final_path)
            logger.info("Video promoted → %s", final_path)
            output_path = str(final_path)

        logger.info("=== Video complete: %s ===", output_path)

        # 9. Cleanup workspace temporary files
        self._cleanup_workspace(workspace)

        return {
            "output_path": output_path,
            "title": config.title,
            "format": config.output_format.value,
            "subtitles_enabled": config.subtitles_enabled,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _cleanup_workspace(self, workspace: Path) -> None:
        """Remove transient files from the workspace directory.

        Deletes the ``temp/`` subdirectory (if present) and any moviepy
        scratch files matching ``*TEMP_MPY*``. All other workspace contents
        (audio, visuals) are left in place.
        """
        temp_dir = workspace / "temp"
        if temp_dir.exists():
            logger.info("Cleaning up temporary directory: %s", temp_dir)
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        # Add any other transient files to cleanup here if needed
        # For example, moviepy often leaves .mp3TEMP_MPY_wvf_snd.mp4 files
        for transient in workspace.glob("*TEMP_MPY*"):
            try:
                transient.unlink()
                logger.info("Removed transient file: %s", transient)
            except Exception as e:
                logger.warning("Could not remove transient file %s: %s", transient, e)

    def _save_uploaded_images(self, uploads: dict, dest_dir: str) -> List[str]:
        """Write in-memory image bytes to *dest_dir* and return the file paths."""
        saved: List[str] = []
        for filename, data in uploads.items():
            path = os.path.join(dest_dir, filename)
            with open(path, "wb") as f:
                f.write(data)
            logger.info("Saved uploaded image → %s", path)
            saved.append(path)
        return saved

    def _prepare_visuals(
        self, config: VideoConfiguration, workspace: str, aspect_ratio: str, width: int, height: int
    ) -> List[str]:
        """Resolve visual assets — either copy provided images or generate from prompts."""
        visuals_dir = os.path.join(workspace, "visuals")
        os.makedirs(visuals_dir, exist_ok=True)

        if config.visual_assets.asset_type == VisualAssetType.IMAGE_SEQUENCE:
            images = list(config.visual_assets.images or [])

            # Persist any in-memory uploads (from UI) to the workspace.
            if config.visual_assets.uploaded_images:
                images.extend(
                    self._save_uploaded_images(config.visual_assets.uploaded_images, visuals_dir)
                )

            if not images:
                logger.warning("IMAGE_SEQUENCE selected but no images provided.")
                return []
            return image_adapter.copy_provided_images(images, visuals_dir)

        # TEXT_PROMPTS
        prompts = config.visual_assets.prompts or []
        if not prompts:
            logger.warning("TEXT_PROMPTS selected but no prompts provided.")
            return []
        return image_adapter.generate_from_prompts(
            prompts,
            visuals_dir,
            style=config.image_style,
            engine=config.image_engine.value if config.image_engine else None,
            aspect_ratio=aspect_ratio,
            width=width,
            height=height,
        )
