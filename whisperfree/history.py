"""Simple persistence for transcription history and statistics."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import threading
from pathlib import Path
from typing import Iterable, List, Optional

from whisperfree.config import CONFIG_DIR
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

_WORD_PATTERN = re.compile(r"\b\w+\b", re.UNICODE)
HISTORY_PATH = CONFIG_DIR / "history.jsonl"


def _ensure_history_dir() -> None:
    """Make sure the history directory exists."""
    HISTORY_PATH.parent.mkdir(parents=True, exist_ok=True)


def _word_count(text: str) -> int:
    """Count words in text using a regex-based tokeniser."""
    if not text:
        return 0
    return len(_WORD_PATTERN.findall(text))


@dataclass(frozen=True)
class TranscriptionEntry:
    """Represents a single transcription event."""

    timestamp: datetime
    text: str
    words: int

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp.isoformat(),
            "text": self.text,
            "words": self.words,
        }

    @staticmethod
    def from_dict(data: dict) -> Optional["TranscriptionEntry"]:
        """Create an entry from raw JSON data."""
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            text = str(data.get("text", ""))
            words = int(data.get("words", _word_count(text)))
        except Exception as exc:  # pragma: no cover - defensive parsing
            logger.warning("Skipping malformed history entry: %s (error=%s)", data, exc)
            return None
        return TranscriptionEntry(timestamp=timestamp, text=text, words=words)


class TranscriptionHistory:
    """Persist transcription events to disk and expose statistics."""

    def __init__(self, path: Path = HISTORY_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._total_words: Optional[int] = None

    def add_entry(self, text: str, timestamp: Optional[datetime] = None) -> TranscriptionEntry:
        """Append a transcription event to the history log."""
        ts = timestamp or datetime.now(timezone.utc)
        entry = TranscriptionEntry(timestamp=ts, text=text, words=_word_count(text))
        payload = json.dumps(entry.to_dict(), ensure_ascii=False)
        with self._lock:
            _ensure_history_dir()
            with self._path.open("a", encoding="utf-8") as handle:
                handle.write(payload + "\n")
            self._total_words = (self._total_words or 0) + entry.words
        return entry

    def entries(self, limit: Optional[int] = None) -> List[TranscriptionEntry]:
        """Return history entries in reverse chronological order."""
        records: List[TranscriptionEntry] = []
        total_words = 0
        if not self._path.exists():
            return records
        with self._lock:
            raw_lines = self._path.read_text(encoding="utf-8").splitlines()
        for line in reversed(raw_lines):
            if not line.strip():
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError as exc:  # pragma: no cover - defensive
                logger.warning("Skipping corrupt history line: %s (error=%s)", line, exc)
                continue
            entry = TranscriptionEntry.from_dict(data)
            if entry:
                records.append(entry)
                total_words += entry.words
            if limit and len(records) >= limit:
                break
        if limit is None:
            with self._lock:
                self._total_words = total_words
        return records

    def total_word_count(self) -> int:
        """Return the total number of words transcribed."""
        with self._lock:
            if self._total_words is not None:
                return self._total_words
            if not self._path.exists():
                self._total_words = 0
                return 0
            try:
                raw_lines = self._path.read_text(encoding="utf-8").splitlines()
            except OSError as exc:  # pragma: no cover - defensive
                logger.warning("Unable to read history file for totals: %s", exc)
                self._total_words = 0
                return 0
            total = 0
            for line in raw_lines:
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                except json.JSONDecodeError as json_exc:  # pragma: no cover - defensive
                    logger.warning("Skipping corrupt history line during totals: %s (error=%s)", line, json_exc)
                    continue
                entry = TranscriptionEntry.from_dict(data)
                if entry:
                    total += entry.words
            self._total_words = total
            return total

    @staticmethod
    def group_by_day(entries: Iterable[TranscriptionEntry]) -> dict[str, List[TranscriptionEntry]]:
        """Utility that groups entries by local calendar day."""
        grouped: dict[str, List[TranscriptionEntry]] = {}
        for entry in entries:
            local_time = entry.timestamp.astimezone()
            key = local_time.strftime("%Y-%m-%d")
            grouped.setdefault(key, []).append(entry)
        return grouped

