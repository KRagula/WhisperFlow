"""Model metadata and constants for WhisperFree."""

from __future__ import annotations

from typing import FrozenSet, List, Tuple


DEFAULT_TRANSCRIPTION_MODEL = "gpt-transcribe"

TRANSCRIPTION_MODELS: List[Tuple[str, str]] = [
    ("gpt-transcribe", "GPT Transcribe (recommended)"),
    ("gpt-4o-mini-transcribe", "GPT-4o mini Transcribe (cheapest)"),
    ("whisper-1", "Whisper (legacy)"),
]

# Models that take dictionary terms as `keywords` and the language as a `languages` list.
KEYWORD_MODELS: FrozenSet[str] = frozenset({"gpt-transcribe"})

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
