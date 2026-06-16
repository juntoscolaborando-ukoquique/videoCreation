"""
Integration tests for the real assembly path.

These tests perform actual I/O (ffmpeg, moviepy) and are skipped in the
default CI run. Run manually with:

    pytest tests/test_integration.py -v -m integration
"""

import os
import pytest
from src.assembler_adapter import _local_moviepy_assemble


@pytest.mark.integration
def test_local_assembly_produces_valid_mp4(sample_images, sample_audio, tmp_path):
    out = _local_moviepy_assemble(
        audio_path=sample_audio,
        visual_files=sample_images,
        output_dir=str(tmp_path),
        output_filename="test_out.mp4",
        width=320,
        height=240,
    )
    assert os.path.isfile(out)
    assert os.path.getsize(out) > 1000
