"""Configuration management for WhisperFree."""

from __future__ import annotations

from dataclasses import dataclass, asdict
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from dotenv import load_dotenv


CONFIG_DIR = Path.home() / ".whisperfree"
CONFIG_PATH = CONFIG_DIR / "config.json"
CONFIG_VERSION = 3


def _ensure_config_dir() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)


@dataclass
class AppConfig:
    """Represents persisted WhisperFree configuration."""

    version: int = CONFIG_VERSION
    mic_device_name: Optional[str] = None
    sample_rate: int = 16000
    language: str = "auto"
    api_key_env: str = "OPENAI_API_KEY"
    api_whisper_model: str = "whisper-1"
    append_newline: bool = True
    input_gain_db: float = 0.0
    overlay_enabled: bool = True
    paste_retries: int = 1
    hotkey_modifier_primary: str = "ctrl"
    hotkey_modifier_secondary: str = "win"

    def to_dict(self) -> Dict[str, Any]:
        """Convert config to a JSON serialisable dictionary."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "AppConfig":
        """Instantiate from persisted dictionary, ignoring unknown keys."""
        kwargs: Dict[str, Any] = {}
        for field_name in cls.__dataclass_fields__:  # type: ignore[attr-defined]
            if field_name in data:
                kwargs[field_name] = data[field_name]
        return cls(**kwargs)

    def save(self, path: Path = CONFIG_PATH) -> None:
        """Persist configuration to disk."""
        _ensure_config_dir()
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    def resolve_api_key(self) -> Optional[str]:
        """Return the OpenAI API key using env var + .env convenience loading."""
        load_dotenv()
        return os.environ.get(self.api_key_env)


def load_config(path: Path = CONFIG_PATH) -> AppConfig:
    """Load configuration from disk, falling back to defaults on error."""
    if not path.exists():
        return AppConfig()

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return AppConfig()

    if not isinstance(raw, dict):
        return AppConfig()

    config = AppConfig.from_dict(raw)
    if config.version != CONFIG_VERSION:
        config.version = CONFIG_VERSION
        config.save(path)
    return config
