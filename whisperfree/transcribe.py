"""Transcription backend for WhisperFree."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence

from openai import OpenAI

from whisperfree.config import AppConfig
from whisperfree.models import DEFAULT_TRANSCRIPTION_MODEL, KEYWORD_MODELS
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

# The API rejects keywords containing angle brackets or line breaks.
_KEYWORD_FORBIDDEN = re.compile(r"[<>]")
_KEYWORD_LINE_BREAKS = re.compile(r"[\r\n]+")


@dataclass
class TranscriptionResult:
    """Value object capturing transcription output."""

    text: str
    language: Optional[str] = None


def _clean_keywords(keywords: Sequence[str]) -> List[str]:
    cleaned = []
    for keyword in keywords:
        value = _KEYWORD_LINE_BREAKS.sub(" ", _KEYWORD_FORBIDDEN.sub("", keyword)).strip()
        if value:
            cleaned.append(value)
    return cleaned


def _detected_language(response: Any, fallback: str) -> str:
    """Read the detected language from either response shape.

    gpt-transcribe returns ``languages: [{"code": "fr"}]`` (empty when unsure);
    older models return a single ``language`` string, if anything.
    """
    languages = getattr(response, "languages", None)
    if languages:
        first = languages[0]
        code = first.get("code") if isinstance(first, dict) else getattr(first, "code", None)
        if code:
            return code
    return getattr(response, "language", None) or fallback


class ApiTranscriber:
    """Transcribe using the OpenAI audio transcription API."""

    def __init__(self, api_key: str, model_name: str = DEFAULT_TRANSCRIPTION_MODEL) -> None:
        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name

    def transcribe(
        self,
        audio_bytes: bytes,
        language: str = "auto",
        prompt: str = "",
        keywords: Sequence[str] = (),
    ) -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", language=language)
        file_tuple = ("audio.wav", audio_bytes, "audio/wav")
        params: Dict[str, Any] = {"model": self._model_name, "file": file_tuple}
        pinned_language = language if language and language.lower() != "auto" else None

        if self._model_name in KEYWORD_MODELS:
            # The installed SDK predates these parameters, so they travel in extra_body.
            # Dictionary terms go in as keywords, which replace the glossary prompt.
            extra: Dict[str, Any] = {}
            cleaned = _clean_keywords(keywords)
            if cleaned:
                extra["keywords"] = cleaned
            if pinned_language:
                extra["languages"] = [pinned_language]
            if extra:
                params["extra_body"] = extra
        else:
            if pinned_language:
                params["language"] = pinned_language
            if prompt:
                params["prompt"] = prompt

        logger.info("Invoking OpenAI transcription model={}", self._model_name)
        response = self._client.audio.transcriptions.create(**params)
        text = response.text.strip() if response.text else ""
        return TranscriptionResult(text=text, language=_detected_language(response, language))


class TranscriptionRouter:
    """Routes transcription to the configured OpenAI backend."""

    def __init__(self, config: AppConfig):
        self._config = config
        self._api_client: Optional[ApiTranscriber] = None
        self._api_client_key: Optional[str] = None
        self._api_model_name: Optional[str] = None

    def _get_api(self) -> ApiTranscriber:
        api_key = self._config.resolve_api_key()
        if not api_key:
            raise RuntimeError(f"Missing OpenAI API key. Set environment variable {self._config.api_key_env}.")
        model_name = self._config.api_whisper_model
        if (
            not self._api_client
            or self._api_client_key != api_key
            or self._api_model_name != model_name
        ):
            self._api_client = ApiTranscriber(api_key, model_name=model_name)
            self._api_client_key = api_key
            self._api_model_name = model_name
        return self._api_client

    def transcribe(self, audio_bytes: bytes, prompt: str = "", keywords: Sequence[str] = ()) -> TranscriptionResult:
        """Transcribe audio with the configured model, language, and dictionary hints."""
        return self._get_api().transcribe(
            audio_bytes,
            language=self._config.language,
            prompt=prompt,
            keywords=keywords,
        )
