"""
Tests for src.utils shared utilities.
"""

from src.utils import sanitize_filename


class TestSanitizeFilename:
    def test_dots_replaced(self):
        assert sanitize_filename("my.video") == "my_video"
        assert sanitize_filename("intro.v2") == "intro_v2"

    def test_spaces_replaced(self):
        assert sanitize_filename("my video") == "my_video"
        assert sanitize_filename("hello world test") == "hello_world_test"

    def test_illegal_chars_replaced(self):
        assert sanitize_filename('a/b\\c:d*e?f"g<h>i|j') == "a_b_c_d_e_f_g_h_i_j"

    def test_empty_becomes_untitled(self):
        assert sanitize_filename("...") == "untitled"
        assert sanitize_filename("") == "untitled"

    def test_consecutive_underscores_collapsed(self):
        assert sanitize_filename("a..b") == "a_b"
        assert sanitize_filename("a  b") == "a_b"

    def test_leading_trailing_underscores_stripped(self):
        assert sanitize_filename(".hidden") == "hidden"
        assert sanitize_filename("trailing.") == "trailing"

    def test_normal_title_unchanged(self):
        assert sanitize_filename("My Cool Video") == "My_Cool_Video"
