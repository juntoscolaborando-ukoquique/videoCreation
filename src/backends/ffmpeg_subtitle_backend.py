"""
FFmpeg Subtitle Backend — ffmpeg/ASS subtitle burn-in.

All production logic lives here. The former src/subtitle_renderer.py
has been consolidated into this module.
"""

import logging
import os
import subprocess
import tempfile
import textwrap
import uuid
from typing import Dict, List

from src import config_loader as _default_config_loader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public backend class
# ---------------------------------------------------------------------------

class FFmpegSubtitleBackend:
    """Burns subtitles using ffmpeg and ASS format."""

    def burn_subtitles(
        self,
        video_path: str,
        segments: List[Dict],
        output_dir: str,
        output_filename: str,
        output_format: str,
        width: int,
        height: int,
        config_loader=None,
    ) -> str:
        return burn_subtitles(
            video_path=video_path,
            segments=segments,
            output_dir=output_dir,
            output_filename=output_filename,
            output_format=output_format,
            width=width,
            height=height,
            config_loader=config_loader,
        )


# ---------------------------------------------------------------------------
# Public API (module-level, callable without instantiating the backend)
# ---------------------------------------------------------------------------

def burn_subtitles(
    video_path: str,
    segments: List[Dict],
    output_dir: str,
    output_filename: str,
    output_format: str,
    width: int,
    height: int,
    config_loader=None,
) -> str:
    """Burn subtitles onto a video using ffmpeg and ASS format.

    Returns
    -------
    str
        Path to the subtitled output video.
    """
    if not segments:
        logger.warning("burn_subtitles: no segments provided — returning original video.")
        return video_path

    valid = [s for s in segments if s.get("text", "").strip() and s.get("end", 0) > s.get("start", 0)]
    if not valid:
        return video_path

    run_id = str(uuid.uuid4())[:8]
    output_path = os.path.join(output_dir, f"subtitled_{run_id}_{output_filename}")

    ass_fd, ass_path = tempfile.mkstemp(suffix=".ass", dir=output_dir)
    try:
        with os.fdopen(ass_fd, "w", encoding="utf-8") as f:
            f.write(_segments_to_ass(valid, width, height, config_loader=config_loader))

        success = _ffmpeg_burn(video_path, ass_path, output_path)
        if success:
            logger.info("Subtitle burn-in complete → %s", output_path)
            return output_path
        else:
            logger.error("ffmpeg burn-in failed — returning original video.")
            return video_path
    finally:
        try:
            os.unlink(ass_path)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# ASS generation
# ---------------------------------------------------------------------------

_FONT_NAME_MAP = {
    "liberationsans-regular":  "Liberation Sans",
    "liberationsans-bold":     "Liberation Sans",
    "liberationserif-regular": "Liberation Serif",
    "dejavusans":              "DejaVu Sans",
    "dejavusans-bold":         "DejaVu Sans",
    "arial":                   "Arial",
}


def _font_name_from_path(font_path: str) -> str:
    """Derive an ASS-compatible font family name from a font file path."""
    stem = os.path.splitext(os.path.basename(font_path))[0].lower().replace("_", "-")
    if stem in _FONT_NAME_MAP:
        return _FONT_NAME_MAP[stem]
    return " ".join(word.capitalize() for word in stem.replace("-", " ").split())


def _segments_to_ass(segments: List[Dict], width: int, height: int, config_loader=None) -> str:
    """Convert segment dicts to ASS format string with embedded styles."""
    _cfg = config_loader or _default_config_loader
    scfg = _cfg.subtitles()

    font_path    = scfg.get("font", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
    font_name    = _font_name_from_path(font_path)
    font_size    = int(scfg.get("font_size", 22))
    font_color   = _color_to_ass(scfg.get("font_color", "white"))
    stroke_color = _color_to_ass(scfg.get("stroke_color", "black"))
    stroke_width = int(scfg.get("stroke_width", 1))
    margin_v     = int(scfg.get("margin", 120))
    position     = scfg.get("position", "bottom")
    max_chars    = int(scfg.get("max_chars_per_line", 42))

    alignment = 8 if position == "middle" else 2

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font_name},{font_size},{font_color},&H000000FF,{stroke_color},&H99000000,0,0,0,0,100,100,0,0,3,{stroke_width},0,{alignment},60,60,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = []
    for seg in segments:
        start = _seconds_to_ass_timestamp(seg["start"])
        end   = _seconds_to_ass_timestamp(seg["end"])
        text  = seg["text"].strip().replace("\n", " ")
        wrapped = textwrap.wrap(text, width=max_chars)[:2]
        display_text = "\\N".join(wrapped)
        events.append(f"Dialogue: 0,{start},{end},Default,,0,0,0,,{display_text}")

    return header + "\n".join(events)


def _seconds_to_ass_timestamp(seconds: float) -> str:
    """Convert float seconds to ASS timestamp: H:MM:SS.cc"""
    cs = int(round(seconds * 100))
    h  = cs // 360000;  cs %= 360000
    m  = cs // 6000;    cs %= 6000
    s  = cs // 100;     cs %= 100
    return f"{h:d}:{m:02d}:{s:02d}.{cs:02d}"


def _color_to_ass(color: str) -> str:
    """Convert color to ASS &HAABBGGRR format.

    Handles named colors, 7-char #RRGGBB, and 4-char #RGB shorthand.
    """
    _named = {
        "white":  "&H00FFFFFF",
        "black":  "&H00000000",
        "yellow": "&H0000FFFF",
        "red":    "&H000000FF",
        "blue":   "&H00FF0000",
        "green":  "&H0000FF00",
    }
    color = color.strip().lower()
    if color in _named:
        return _named[color]
    if color.startswith("#") and len(color) == 4:
        # Expand #RGB → #RRGGBB
        r, g, b = color[1], color[2], color[3]
        color = f"#{r}{r}{g}{g}{b}{b}"
    if color.startswith("#") and len(color) == 7:
        r, g, b = color[1:3], color[3:5], color[5:7]
        return f"&H00{b}{g}{r}".upper()
    logger.debug("_color_to_ass: unrecognised color '%s' — defaulting to white.", color)
    return "&H00FFFFFF"


# ---------------------------------------------------------------------------
# ffmpeg call
# ---------------------------------------------------------------------------

def _ffmpeg_burn(video_path: str, ass_path: str, output_path: str) -> bool:
    """Call ffmpeg to burn the ASS subtitles onto the video."""
    p = ass_path.replace("\\", "/").replace(":", "\\:").replace("'", "\\'")
    escaped_ass = f"'{p}'"

    cmd = [
        "ffmpeg", "-y",
        "-i", video_path,
        "-vf", f"ass={escaped_ass}",
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        "-c:a", "copy",
        output_path,
    ]

    logger.info("Running ffmpeg ASS burn-in …")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        logger.error("ffmpeg failed:\n%s", result.stderr)
        return False

    return True
