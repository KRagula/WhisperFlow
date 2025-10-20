"""Model metadata and constants for WhisperFree."""

from __future__ import annotations

from typing import List, Tuple


LANGUAGE_CHOICES: List[Tuple[str, str]] = [
    ("auto", "Auto Detect"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("de", "German"),
    ("hi", "Hindi"),
    ("ja", "Japanese"),
    ("ko", "Korean"),
    ("pt", "Portuguese"),
    ("zh", "Chinese"),
]
