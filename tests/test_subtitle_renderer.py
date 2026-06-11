"""
Unit tests for src.subtitle_renderer — Pillow-based subtitle frame renderer.
"""

import numpy as np
import pytest
from PIL import ImageFont

from src import subtitle_renderer


def _make_font(size: int = 54) -> ImageFont.FreeTypeFont:
    font_path = "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
    try:
        return ImageFont.truetype(font_path, size)
    except OSError:
        return ImageFont.load_default()


class TestRenderSubtitleFrame:
    def test_frame_is_correct_size(self):
        font = _make_font()
        frame = subtitle_renderer._render_subtitle_frame_legacy_test_only(
            text="Hello world",
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )
        assert frame.size == (1080, 1920)
        assert frame.mode == "RGBA"

    def test_descenders_not_clipped(self):
        """Characters with descenders must not be cropped.

        Pixels must exist below the ascent line, confirming the text box
        was tall enough to include the descender region.
        """
        font = _make_font(54)
        ascent, descent = font.getmetrics()

        frame = subtitle_renderer._render_subtitle_frame_legacy_test_only(
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
        frame = subtitle_renderer._render_subtitle_frame_legacy_test_only(
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
        frame = subtitle_renderer._render_subtitle_frame_legacy_test_only(
            text="",
            width=1080, height=1920,
            font=font,
            font_color="white", stroke_color="black",
            stroke_width=2, margin=300, max_chars=32,
        )
        assert frame.size == (1080, 1920)
