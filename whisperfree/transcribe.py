"""Transcription backend for WhisperFree."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from openai import OpenAI

from whisperfree.config import AppConfig
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)


@dataclass
class TranscriptionResult:
    """Value object capturing transcription output."""

    text: str
    language: Optional[str] = None


class ApiTranscriber:
    """Transcribe using the OpenAI Whisper API."""

    def __init__(self, api_key: str, model_name: str = "whisper-1") -> None:
        self._client = OpenAI(api_key=api_key)
        self._model_name = model_name

    def transcribe(self, audio_bytes: bytes, language: str = "auto") -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", language=language)
        file_tuple = ("audio.wav", audio_bytes, "audio/wav")
        params = {"model": self._model_name, "file": file_tuple}
        if language and language.lower() != "auto":
            params["language"] = language
        logger.info("Invoking OpenAI Whisper API model=%s", self._model_name)
        response = self._client.audio.transcriptions.create(**params)
        detected_language = getattr(response, "language", language)
        text = response.text.strip() if response.text else ""
        return TranscriptionResult(
            text=text,
            language=detected_language,
        )


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

    def transcribe(self, audio_bytes: bytes) -> TranscriptionResult:
        """Transcribe audio using the OpenAI Whisper API."""
        return self._get_api().transcribe(audio_bytes, language=self._config.language)

