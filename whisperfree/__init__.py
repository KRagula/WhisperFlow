"""WhisperFree package initialization."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("whisperfree")
except PackageNotFoundError:  # pragma: no cover - local dev fallback
    __version__ = "0.1.0"

__all__ = ["__version__"]
