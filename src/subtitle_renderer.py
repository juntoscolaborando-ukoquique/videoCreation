"""
Subtitle Renderer — ffmpeg-based subtitle burn-in using ASS format for precision.

Replaces the SRT approach with ASS (Advanced Substation Alpha) to ensure
pixel-perfect positioning, font scaling, and background boxes.
"""

import logging
import os
import subprocess
import tempfile
import textwrap
import uuid
from typing import Dict, List

from PIL import Image, ImageDraw, ImageFont

from src import config_loader

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def burn_subtitles(
    video_path: str,
    segments: List[Dict],
    output_dir: str,
    output_filename: str,
    output_format: str,
    width: int,
    height: int,
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

    # Write ASS to a temp file next to the output
    ass_fd, ass_path = tempfile.mkstemp(suffix=".ass", dir=output_dir)
    try:
        with os.fdopen(ass_fd, "w", encoding="utf-8") as f:
            f.write(_segments_to_ass(valid, width, height))

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
# ASS generation — font_name derivado del path en vez de hardcodeado
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
    import os as _os
    stem = _os.path.splitext(_os.path.basename(font_path))[0].lower().replace("_", "-")
    if stem in _FONT_NAME_MAP:
        return _FONT_NAME_MAP[stem]
    return " ".join(word.capitalize() for word in stem.replace("-", " ").split())


def _segments_to_ass(segments: List[Dict], width: int, height: int) -> str:
    """Convert segment dicts to ASS format string with embedded styles."""
    scfg = config_loader.subtitles()
    
    font_path    = scfg.get("font", "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf")
    font_name    = _font_name_from_path(font_path)
    font_size    = int(scfg.get("font_size", 22))
    font_color   = _color_to_ass(scfg.get("font_color", "white"))
    stroke_color = _color_to_ass(scfg.get("stroke_color", "black"))
    stroke_width = int(scfg.get("stroke_width", 1))
    margin_v     = int(scfg.get("margin", 120))
    position     = scfg.get("position", "bottom")
    max_chars    = int(scfg.get("max_chars_per_line", 42))

    # ASS Alignment: 2 = bottom-center, 8 = middle-center
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
        
        # Force wrapping to max 2 lines
        wrapped = textwrap.wrap(text, width=max_chars)
        wrapped = wrapped[:2]
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
    """Convert color to ASS &HAABBGGRR format."""
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
    if color.startswith("#") and len(color) == 7:
        r, g, b = color[1:3], color[3:5], color[5:7]
        return f"&H00{b}{g}{r}".upper()
    return "&H00FFFFFF"


# ---------------------------------------------------------------------------
# ffmpeg call
# ---------------------------------------------------------------------------

def _ffmpeg_burn(video_path: str, ass_path: str, output_path: str) -> bool:
    """Call ffmpeg to burn the ASS subtitles onto the video."""
    # Robust path escaping for ffmpeg filters
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


# ---------------------------------------------------------------------------
# _render_subtitle_frame_legacy_test_only — Pillow geometry helper for tests
# ---------------------------------------------------------------------------
# WARNING: This function is NOT part of the production subtitle pipeline.
# The production path is: burn_subtitles() → _ffmpeg_burn() (ASS/ffmpeg).
# This Pillow-based renderer exists only to let test_subtitle_renderer.py
# verify text-box geometry and descender handling in isolation, without
# needing a real video file or ffmpeg call.
# Do NOT wire this into any new production code paths.
# ---------------------------------------------------------------------------

def _render_subtitle_frame_legacy_test_only(
    text: str,
    width: int,
    height: int,
    font: ImageFont.FreeTypeFont,
    font_color: str,
    stroke_color: str,
    stroke_width: int,
    margin: int,
    max_chars: int,
) -> Image.Image:
    """Pillow-based subtitle frame renderer — **test-only legacy helper**.

    .. warning::
        This is **not** the production subtitle path. The production pipeline
        uses :func:`burn_subtitles` which delegates to ffmpeg/ASS via
        :func:`_ffmpeg_burn`. This function exists solely to support geometry
        tests in ``test_subtitle_renderer.py``.
    """
    lines = textwrap.wrap(text, width=max_chars) or [text]
    lines = lines[:2] # Force 2 lines here too
    
    ascent, descent = font.getmetrics()
    line_height   = ascent + descent
    line_spacing  = int(line_height * 0.2)
    total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing

    max_line_width = max(font.getlength(line) for line in lines)
    pad_x = stroke_width + 16
    pad_y = stroke_width + 12
    box_w = int(max_line_width) + pad_x * 2
    box_h = total_text_height + pad_y * 2

    box_x = (width - box_w) // 2
    scfg     = config_loader.subtitles()
    position = scfg.get("position", "bottom")
    box_y = (height - box_h) // 2 if position == "middle" else height - margin - box_h

    frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw  = ImageDraw.Draw(frame)
    draw.rounded_rectangle(
        [box_x - 4, box_y - 4, box_x + box_w + 4, box_y + box_h + 4],
        radius=12, fill=(0, 0, 0, 160)
    )

    y_cursor = box_y + pad_y
    for line in lines:
        line_w = font.getlength(line)
        draw.text(
            ((width - line_w) // 2, y_cursor),
            line, font=font, fill=font_color,
            stroke_width=stroke_width, stroke_fill=stroke_color
        )
        y_cursor += line_height + line_spacing

    return frame
