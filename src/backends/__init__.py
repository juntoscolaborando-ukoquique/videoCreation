"""
Backend protocols — stable interfaces between adapters and concrete
implementations (ffmpeg, moviepy, future alternatives).
"""

from typing import Dict, List, Optional, Protocol, runtime_checkable


@runtime_checkable
class AssemblerBackend(Protocol):
    """Minimal interface every assembler backend must satisfy."""

    def assemble(
        self,
        audio_path: str,
        visual_files: List[str],
        title: str,
        output_dir: str,
        output_filename: str,
        background_music: Optional[str],
        width: int,
        height: int,
    ) -> Optional[str]:
        """Assemble audio + visuals into a video file.

        Returns the output path on success, or ``None`` if the backend is
        unavailable so the caller can fall through to the next option.
        """
        ...


@runtime_checkable
class SubtitleBackend(Protocol):
    """Minimal interface every subtitle burn-in backend must satisfy."""

    def burn_subtitles(
        self,
        video_path: str,
        segments: List[Dict],
        output_dir: str,
        output_filename: str,
        output_format: str,
        width: int,
        height: int,
    ) -> str:
        """Burn subtitle segments onto *video_path*.

        Returns the path to the output video (may equal *video_path* if
        burn-in is skipped or fails gracefully).
        """
        ...
