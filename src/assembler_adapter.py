"""
Assembler Adapter — video assembly bridge using moviepy.

Subtitle burn-in is handled by the orchestrator as a separate post-processing
step; this adapter is responsible only for assembling audio and visuals.
"""

import os
import logging
from typing import List, Optional

from src import config_loader
from src.backends import AssemblerBackend
from src.utils import sanitize_filename

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def assemble_video(
    audio_path: str,
    visual_files: List[str],
    *,
    title: str = "untitled",
    output_dir: str = "output",
    output_format: str = "mp4",
    background_music: Optional[str] = None,
    width: Optional[int] = None,
    height: Optional[int] = None,
    backend: Optional[AssemblerBackend] = None,
) -> str:
    """Assemble audio and visuals into a video file.

    Subtitle burn-in is not handled here — the orchestrator applies it as a
    separate post-processing step via ``subtitle_renderer.burn_subtitles``.

    Parameters
    ----------
    backend:
        Optional assembler backend. When provided, its ``assemble()`` method
        is called first; if it returns ``None`` the local moviepy path is used
        as a fallback. Pass a mock here in tests to avoid real video assembly.

    Returns
    -------
    str
        Absolute path to the assembled video file.
    """
    cfg = config_loader.video()
    if width is None:
        width = cfg.get("width", 1080)
    if height is None:
        height = cfg.get("height", 1920)
    os.makedirs(output_dir, exist_ok=True)
    output_filename = f"{sanitize_filename(title)}.{output_format}"

    path: Optional[str] = None
    if backend is not None:
        path = backend.assemble(
            audio_path=audio_path,
            visual_files=visual_files,
            title=title,
            output_dir=output_dir,
            output_filename=output_filename,
            background_music=background_music,
            width=width,
            height=height,
        )

    if path is None:
        path = _local_moviepy_assemble(
            audio_path=audio_path,
            visual_files=visual_files,
            output_dir=output_dir,
            output_filename=output_filename,
            width=width,
            height=height,
        )

    return path

# ---------------------------------------------------------------------------
# Local moviepy fallback  (audio + visuals only — no captions)
# ---------------------------------------------------------------------------

def _local_moviepy_assemble(
    audio_path: str,
    visual_files: List[str],
    output_dir: str,
    output_filename: str,
    width: int,
    height: int,
) -> str:
    """Assemble video using moviepy directly.

    Produces a video without subtitles; subtitle burn-in is handled by
    ``subtitle_renderer.burn_subtitles``.
    """
    try:
        from moviepy import AudioFileClip, ImageClip, concatenate_videoclips
        from moviepy.video.fx import Resize, Crop
    except ImportError as exc:
        raise RuntimeError(
            f"moviepy is required for local video assembly but could not be imported: {exc}. "
            "Ensure moviepy==2.1.2 is installed."
        ) from exc

    logger.info("Local moviepy assembly: %d visuals + audio", len(visual_files))

    output_path = os.path.join(output_dir, output_filename)
    audio = AudioFileClip(audio_path)
    try:
        duration = audio.duration
        time_per_visual = duration / max(len(visual_files), 1)

        clips = []
        for vf in visual_files:
            clip = ImageClip(vf).with_duration(time_per_visual)
            img_w, img_h = clip.size
            
            # 1. Resize so the smaller dimension matches the target dimension
            target_ratio = width / height
            img_ratio    = img_w / img_h
            
            if img_ratio > target_ratio:
                clip = clip.with_effects([Resize(height=height)])
            else:
                clip = clip.with_effects([Resize(width=width)])
            
            # 2. Center crop to exactly width x height
            cw, ch = clip.size
            clip = clip.with_effects([Crop(width=width, height=height, x_center=cw//2, y_center=ch//2)])
            clips.append(clip)

        video = concatenate_videoclips(clips, method="compose").with_audio(audio)
        try:
            fps = config_loader.video().get("fps", 30)
            video.write_videofile(
                output_path,
                fps=fps,
                codec="libx264",
                audio_codec="aac",
                threads=4,
                preset="ultrafast",
                logger=None,
            )
        finally:
            video.close()
    finally:
        audio.close()

    logger.info("Local assembly complete → %s", output_path)
    return output_path
