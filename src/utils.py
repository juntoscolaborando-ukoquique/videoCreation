"""
Shared utilities for the VideoCreation pipeline.
"""

import re


def sanitize_filename(title: str) -> str:
    """Return a filesystem-safe version of *title* for use in filenames and paths.

    Replaces spaces with underscores and strips characters that are
    illegal on Linux, macOS, or Windows (/ \\ : * ? " < > | and null bytes).
    Dots are also replaced with underscores to avoid confusing extension
    detection (e.g. "My Video v1.0" → "My_Video_v1_0").
    Collapses consecutive underscores and strips leading/trailing ones.
    Returns ``"untitled"`` if the result is empty.
    """
    sanitized = re.sub(r'[/\\:*?"<>|.\x00]', "_", title)
    sanitized = sanitized.replace(" ", "_")
    sanitized = re.sub(r"_+", "_", sanitized).strip("_")
    return sanitized or "untitled"
