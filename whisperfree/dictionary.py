"""Custom vocabulary and replacement rules applied to transcriptions."""

from __future__ import annotations

import contextlib
import json
import os
import re
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from whisperfree.config import CONFIG_DIR
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

DICTIONARY_PATH = CONFIG_DIR / "dictionary.json"
DICTIONARY_VERSION = 1
PROMPT_PREFIX = "Glossary: "
PROMPT_MAX_CHARS = 800


@dataclass(frozen=True)
class Replacement:
    """A single "when I say X, paste Y" rule."""

    match: str
    replace: str


class Dictionary:
    """Thread-safe store for custom terms and replacement rules.

    The UI thread mutates it while the transcription worker reads it, so every
    public method takes the lock. Mutations persist immediately.
    """

    def __init__(self, path: Path = DICTIONARY_PATH) -> None:
        self._path = path
        self._lock = threading.Lock()
        self._terms: List[str] = []
        self._replacements: List[Replacement] = []
        self._pattern: Optional[re.Pattern[str]] = None
        self._lookup: Dict[str, str] = {}
        self.last_save_error: Optional[str] = None
        self._load()
        self._rebuild_pattern_unlocked()

    # ------------------------------------------------------------------ queries

    def terms(self) -> List[str]:
        with self._lock:
            return list(self._terms)

    def replacements(self) -> List[Replacement]:
        with self._lock:
            return list(self._replacements)

    def build_prompt(self) -> str:
        """Return a Whisper prompt listing terms, newest kept first when over the limit."""
        with self._lock:
            terms = list(self._terms)
        selected: List[str] = []
        length = len(PROMPT_PREFIX) + 1  # trailing "."
        for term in reversed(terms):
            extra = len(term) + (2 if selected else 0)
            if length + extra > PROMPT_MAX_CHARS:
                break
            selected.append(term)
            length += extra
        if not selected:
            return ""
        selected.reverse()
        return PROMPT_PREFIX + ", ".join(selected) + "."

    def apply_replacements(self, text: str) -> str:
        """Apply all rules in one pass: whole words, case-insensitive, longest first."""
        with self._lock:
            pattern, lookup = self._pattern, self._lookup
        if pattern is None or not text:
            return text
        result = pattern.sub(lambda m: lookup.get(m.group(0).casefold(), m.group(0)), text)
        if result == text:
            return text
        return re.sub(r"[ \t]{2,}", " ", result).strip()

    # ------------------------------------------------------------------ mutations

    def add_term(self, term: str) -> bool:
        with self._lock:
            added = self._add_term_unlocked(term)
            if added:
                self._save_unlocked()
            return added

    def remove_term(self, term: str) -> bool:
        key = term.strip().casefold()
        with self._lock:
            for index, existing in enumerate(self._terms):
                if existing.casefold() == key:
                    del self._terms[index]
                    self._save_unlocked()
                    return True
            return False

    def add_replacement(self, match: str, replace: str) -> bool:
        with self._lock:
            added = self._add_replacement_unlocked(match, replace)
            if added:
                self._rebuild_pattern_unlocked()
                self._save_unlocked()
            return added

    def update_replacement(self, index: int, match: str, replace: str) -> bool:
        with self._lock:
            if not 0 <= index < len(self._replacements):
                return False
            cleaned = match.strip()
            if not cleaned or self._match_taken(cleaned, ignore_index=index):
                return False
            self._replacements[index] = Replacement(cleaned, replace.strip())
            self._rebuild_pattern_unlocked()
            self._save_unlocked()
            return True

    def remove_replacement(self, index: int) -> bool:
        with self._lock:
            if not 0 <= index < len(self._replacements):
                return False
            del self._replacements[index]
            self._rebuild_pattern_unlocked()
            self._save_unlocked()
            return True

    # ------------------------------------------------------------------ internals

    def _add_term_unlocked(self, term: str) -> bool:
        cleaned = term.strip()
        if not cleaned:
            return False
        key = cleaned.casefold()
        if any(existing.casefold() == key for existing in self._terms):
            return False
        self._terms.append(cleaned)
        return True

    def _match_taken(self, match: str, ignore_index: Optional[int] = None) -> bool:
        key = match.casefold()
        return any(
            index != ignore_index and rule.match.casefold() == key
            for index, rule in enumerate(self._replacements)
        )

    def _add_replacement_unlocked(self, match: str, replace: str) -> bool:
        cleaned = match.strip()
        if not cleaned or self._match_taken(cleaned):
            return False
        self._replacements.append(Replacement(cleaned, replace.strip()))
        return True

    def _rebuild_pattern_unlocked(self) -> None:
        if not self._replacements:
            self._pattern = None
            self._lookup = {}
            return
        ordered = sorted(self._replacements, key=lambda rule: len(rule.match), reverse=True)
        alternatives = "|".join(re.escape(rule.match) for rule in ordered)
        self._pattern = re.compile(rf"(?<!\w)(?:{alternatives})(?!\w)", re.IGNORECASE)
        self._lookup = {rule.match.casefold(): rule.replace for rule in self._replacements}

    def _load(self) -> None:
        if not self._path.exists():
            return
        try:
            raw: Any = json.loads(self._path.read_text(encoding="utf-8"))
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON value is not an object")
        except (OSError, ValueError) as exc:
            self._quarantine(exc)
            return
        terms = raw.get("terms", [])
        if isinstance(terms, list):
            for term in terms:
                if isinstance(term, str):
                    self._add_term_unlocked(term)
        rules = raw.get("replacements", [])
        if isinstance(rules, list):
            for item in rules:
                if not isinstance(item, dict) or not isinstance(item.get("match"), str):
                    continue
                replace = item.get("replace", "")
                if isinstance(replace, str):
                    self._add_replacement_unlocked(item["match"], replace)

    def _quarantine(self, error: Exception) -> None:
        backup = self._path.with_name(self._path.name + ".bak")
        try:
            os.replace(self._path, backup)
        except OSError as exc:
            logger.warning("Dictionary file unreadable ({}) and could not be moved aside: {}", error, exc)
            return
        logger.warning("Dictionary file unreadable ({}); moved to {}", error, backup)

    def _save_unlocked(self) -> None:
        payload = {
            "version": DICTIONARY_VERSION,
            "terms": self._terms,
            "replacements": [{"match": r.match, "replace": r.replace} for r in self._replacements],
        }
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp_name = tempfile.mkstemp(prefix=".dictionary-", suffix=".tmp", dir=self._path.parent)
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as handle:
                    json.dump(payload, handle, ensure_ascii=False, indent=2)
                os.replace(tmp_name, self._path)
            except BaseException:
                with contextlib.suppress(OSError):
                    os.unlink(tmp_name)
                raise
        except OSError as exc:
            self.last_save_error = str(exc)
            logger.warning("Failed to save dictionary to {}: {}", self._path, exc)
        else:
            self.last_save_error = None
