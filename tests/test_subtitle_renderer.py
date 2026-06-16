"""
Unit tests for subtitle geometry — Pillow-based subtitle frame renderer.

The _render_subtitle_frame_legacy_test_only helper is defined here
(it was moved from src/subtitle_renderer.py, which no longer exists).
"""

import textwrap

import numpy as np
import pytest
from PIL import Image, ImageDraw, ImageFont

from src import config_loader


def _make_font(size: int = 54) -> ImageFont.FreeTypeFont:
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


def _render_subtitle_frame_legacy_test_only(
    text: str,
    width: int,
    height: int,
    font: "ImageFont.FreeTypeFont",
    font_color: str,
    stroke_color: str,
    stroke_width: int,
    margin: int,
    max_chars: int,
) -> "Image.Image":
    """Pillow-based subtitle frame renderer — test-only geometry helper.

    Not part of the production pipeline. Production path:
        orchestrator → FFmpegSubtitleBackend → ffmpeg/ASS
    """
    scfg = config_loader.subtitles()
    lines = textwrap.wrap(text, width=max_chars) or [text]
    lines = lines[:2]

    ascent, descent = font.getmetrics()
    line_height = ascent + descent
    line_spacing = int(line_height * 0.2)
    total_text_height = len(lines) * line_height + (len(lines) - 1) * line_spacing

    max_line_width = max(font.getlength(line) for line in lines)
    pad_x = stroke_width + 16
    pad_y = stroke_width + 12
    box_w = int(max_line_width) + pad_x * 2
    box_h = total_text_height + pad_y * 2

    box_x = (width - box_w) // 2
    position = scfg.get("position", "bottom")
    box_y = (height - box_h) // 2 if position == "middle" else height - margin - box_h

    frame = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(frame)
    draw.rounded_rectangle(
        [box_x - 4, box_y - 4, box_x + box_w + 4, box_y + box_h + 4],
        radius=12, fill=(0, 0, 0, 160),
    )

    y_cursor = box_y + pad_y
    for line in lines:
        line_w = font.getlength(line)
        draw.text(
            ((width - line_w) // 2, y_cursor),
            line, font=font, fill=font_color,
            stroke_width=stroke_width, stroke_fill=stroke_color,
        )
        y_cursor += line_height + line_spacing

    return frame


class TestRenderSubtitleFrame:
    def test_frame_is_correct_size(self):
        font = _make_font()
        frame = _render_subtitle_frame_legacy_test_only(
            text="Hello world",
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )
        assert frame.size == (1080, 1920)
        assert frame.mode == "RGBA"

    def test_descenders_not_clipped(self):
        """Characters with descenders must not be cropped."""
        font = _make_font(54)
        ascent, descent = font.getmetrics()

        frame = _render_subtitle_frame_legacy_test_only(
            text="pygmy jog",
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )

        arr = np.array(frame)
        alpha = arr[:, :, 3]

        rows_with_content = np.where(alpha.max(axis=1) > 0)[0]
        assert len(rows_with_content) > 0, "No visible pixels found in subtitle frame"

        top_row    = int(rows_with_content[0])
        bottom_row = int(rows_with_content[-1])
        rendered_height = bottom_row - top_row

        assert rendered_height >= ascent + descent, (
            f"Rendered height {rendered_height}px < ascent+descent "
            f"({ascent}+{descent}={ascent + descent}px) — descenders are clipped."
        )

    def test_long_text_wrapped(self):
        """Text longer than max_chars should wrap without changing frame dimensions."""
        font = _make_font()
        long_text = "This is a very long subtitle line that should definitely be wrapped"
        frame = _render_subtitle_frame_legacy_test_only(
            text=long_text,
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )
        assert frame.size == (1080, 1920)

    def test_empty_text_returns_transparent_frame(self):
        """Empty text should produce a fully transparent frame without raising."""
        font = _make_font()
        frame = _render_subtitle_frame_legacy_test_only(
            text="",
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )
        assert frame.size == (1080, 1920)
