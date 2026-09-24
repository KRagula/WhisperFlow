# Voquill-style UI, Dictionary, and Launch on Startup — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restyle WhisperFree's control panel after Voquill (light theme, Home/History/Dictionary/Settings), add a dictionary (Whisper spelling hints + replacement rules), and add a per-user "Launch on startup" toggle.

**Architecture:** Three Qt-free core modules (`dictionary.py`, `startup.py`, history stats) with unit tests, wired into the existing `WhisperFreeController` pipeline. The single `ui.py` becomes a `whisperfree/ui/` package: one global stylesheet in `theme.py`, shared widgets in `widgets.py`, one file per page, assembled by `window.py`.

**Tech Stack:** Python 3.11, PyQt6 6.7, OpenAI Python SDK, loguru, pytest (all already in `requirements.txt`).

**Spec:** `docs/superpowers/specs/2026-09-24-voquill-ui-dictionary-startup-design.md`

## Global Constraints

- Run tests from the repo root with `py -3.11 -m pytest tests -q` (Python 3.11 at `py -3.11` has every dependency installed; there is no venv).
- PyQt6 6.7 only — do not use APIs added later (e.g. no `QStyleHints.setColorScheme`).
- No new third-party dependencies.
- Do **not** modify `whisperfree/overlay.py` (the talking indicator is out of scope).
- Logging: `logger = get_logger(__name__)` from `whisperfree.utils.logger`; messages use loguru `{}` placeholders.
- Persistent data lives under `whisperfree.config.CONFIG_DIR` (`~/.whisperfree`). Tests must never read/write the real `~/.whisperfree` files or the real `WhisperFree` registry value — use `tmp_path` and throwaway registry value names.
- All UI colours come from constants in `whisperfree/ui/theme.py`; widgets get styled via `objectName`, not inline `setStyleSheet` (exception: none needed).
- Light theme only. Font: "Segoe UI Variable Text" falling back to "Segoe UI", 13px body.
- Qt tests use the session `qapp` fixture from `tests/conftest.py` (offscreen platform, created in Task 5).
- Every commit message ends with a blank line then `Co-Authored-By: Claude Opus 5.5 (1M context) <noreply@anthropic.com>`.
- Commit only the files the task lists. Do not push.

## Review Focus

1. **Autostart from a foreign working directory** — at Windows sign-in the CWD is not the repo; the app must still import and find an API key kept in the repo-root `.env`. Pinned by `test_launch_command_*` and `test_resolve_api_key_reads_project_env` (Task 2).
2. **A replacement rule that blanks the whole transcript** (e.g. rule "um" → "") must produce "Nothing to paste", not paste an empty string or log an empty history entry. Pinned by `test_blanked_transcript_is_not_pasted` (Task 4).
3. **Windows set to dark mode** — Qt 6.7's default Windows palette goes dark; the control panel, message boxes, and tray menu must still render light and readable. Pinned by `test_apply_theme_forces_light_palette` (Task 5).
4. **Hand-edited or partially invalid `dictionary.json`** (wrong types, missing keys) must load the valid parts without crashing; unparseable files are moved to `.bak`, never silently overwritten. Pinned by `test_partially_invalid_file_keeps_valid_entries` and `test_corrupt_file_is_moved_to_bak` (Task 1).
5. **Large histories** (thousands of entries) must not freeze the History page. Pinned by `test_history_page_renders_lazily` (Task 7).

---

### Task 1: Dictionary store

**Files:**
- Create: `whisperfree/dictionary.py`
- Test: `tests/test_dictionary.py`

**Interfaces:**
- Consumes: `whisperfree.config.CONFIG_DIR`, `whisperfree.utils.logger.get_logger`.
- Produces:
  - `DICTIONARY_PATH: Path`
  - `@dataclass(frozen=True) class Replacement: match: str; replace: str`
  - `class Dictionary(path: Path = DICTIONARY_PATH)` with
    `terms() -> list[str]`, `replacements() -> list[Replacement]`,
    `add_term(term: str) -> bool`, `remove_term(term: str) -> bool`,
    `add_replacement(match: str, replace: str) -> bool`,
    `update_replacement(index: int, match: str, replace: str) -> bool`,
    `remove_replacement(index: int) -> bool`,
    `build_prompt() -> str`, `apply_replacements(text: str) -> str`,
    attribute `last_save_error: Optional[str]`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_dictionary.py`:

```python
import json

from whisperfree.dictionary import Dictionary, Replacement


def make(tmp_path):
    return Dictionary(tmp_path / "dictionary.json")


def test_add_term_trims_and_dedupes_case_insensitively(tmp_path):
    d = make(tmp_path)
    assert d.add_term("  Kanishka ")
    assert not d.add_term("kanishka")
    assert not d.add_term("   ")
    assert d.terms() == ["Kanishka"]


def test_remove_term_is_case_insensitive(tmp_path):
    d = make(tmp_path)
    d.add_term("PyQt6")
    assert d.remove_term("pyqt6")
    assert not d.remove_term("pyqt6")
    assert d.terms() == []


def test_changes_persist_to_disk(tmp_path):
    d = make(tmp_path)
    d.add_term("5Point")
    d.add_replacement("five point", "5Point")
    reloaded = make(tmp_path)
    assert reloaded.terms() == ["5Point"]
    assert reloaded.replacements() == [Replacement("five point", "5Point")]
    raw = json.loads((tmp_path / "dictionary.json").read_text(encoding="utf-8"))
    assert raw["version"] == 1
    assert not list(tmp_path.glob("*.tmp"))


def test_build_prompt_empty_without_terms(tmp_path):
    assert make(tmp_path).build_prompt() == ""


def test_build_prompt_lists_terms(tmp_path):
    d = make(tmp_path)
    for term in ("Kanishka", "5Point", "PyQt6"):
        d.add_term(term)
    assert d.build_prompt() == "Glossary: Kanishka, 5Point, PyQt6."


def test_build_prompt_keeps_most_recent_terms_within_limit(tmp_path):
    d = make(tmp_path)
    for i in range(200):
        d.add_term(f"term{i:03d}")
    prompt = d.build_prompt()
    assert len(prompt) <= 800
    assert prompt.startswith("Glossary: ")
    assert prompt.endswith("term199.")
    assert "term000" not in prompt


def test_replacement_is_whole_word_and_case_insensitive(tmp_path):
    d = make(tmp_path)
    d.add_replacement("gpt four", "GPT-4")
    d.add_replacement("cat", "dog")
    assert d.apply_replacements("I asked GPT Four about my category.") == "I asked GPT-4 about my category."
    assert d.apply_replacements("Cat.") == "dog."


def test_longest_match_wins(tmp_path):
    d = make(tmp_path)
    d.add_replacement("new", "NEW")
    d.add_replacement("new york", "NYC")
    assert d.apply_replacements("I love New York and new things") == "I love NYC and NEW things"


def test_replacements_do_not_chain(tmp_path):
    d = make(tmp_path)
    d.add_replacement("a", "b")
    d.add_replacement("b", "c")
    assert d.apply_replacements("a b") == "b c"


def test_special_character_rules(tmp_path):
    d = make(tmp_path)
    d.add_replacement("c++", "C++")
    d.add_replacement("@me", "kragula@example.com")
    assert d.apply_replacements("I write c++ daily, ping @me") == "I write C++ daily, ping kragula@example.com"


def test_unicode_terms_match(tmp_path):
    d = make(tmp_path)
    d.add_replacement("josé", "José")
    assert d.apply_replacements("JOSÉ said hi") == "José said hi"


def test_blank_replacement_removes_phrase_and_collapses_spaces(tmp_path):
    d = make(tmp_path)
    d.add_replacement("um", "")
    assert d.apply_replacements("So um I think  um yes") == "So I think yes"
    assert d.apply_replacements("um") == ""


def test_text_without_matches_is_unchanged(tmp_path):
    d = make(tmp_path)
    d.add_replacement("foo", "bar")
    assert d.apply_replacements("  keep   spacing  ") == "  keep   spacing  "


def test_add_replacement_rejects_blank_and_duplicate_match(tmp_path):
    d = make(tmp_path)
    assert not d.add_replacement("  ", "x")
    assert d.add_replacement("Five Point", "5Point")
    assert not d.add_replacement("five point", "other")
    assert d.replacements() == [Replacement("Five Point", "5Point")]


def test_update_and_remove_replacement(tmp_path):
    d = make(tmp_path)
    d.add_replacement("a", "1")
    d.add_replacement("b", "2")
    assert not d.update_replacement(0, "B", "x")  # collides with rule 1
    assert d.update_replacement(0, "alpha", "A")
    assert not d.update_replacement(5, "z", "z")
    assert d.apply_replacements("alpha b") == "A 2"
    assert d.remove_replacement(0)
    assert not d.remove_replacement(3)
    assert d.replacements() == [Replacement("b", "2")]
    assert d.apply_replacements("alpha b") == "alpha 2"


def test_corrupt_file_is_moved_to_bak(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text("{not json", encoding="utf-8")
    d = Dictionary(path)
    assert d.terms() == []
    assert (tmp_path / "dictionary.json.bak").read_text(encoding="utf-8") == "{not json"
    assert not path.exists()


def test_partially_invalid_file_keeps_valid_entries(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(
        json.dumps(
            {
                "terms": ["Good", 42, None, "good", "Also"],
                "replacements": [
                    {"match": "ok", "replace": "OK"},
                    {"replace": "missing match"},
                    {"match": 5, "replace": "x"},
                    {"match": "bad", "replace": 7},
                    "not a dict",
                    {"match": "no replace key"},
                ],
            }
        ),
        encoding="utf-8",
    )
    d = Dictionary(path)
    assert d.terms() == ["Good", "Also"]
    assert d.replacements() == [Replacement("ok", "OK"), Replacement("no replace key", "")]


def test_non_list_sections_are_ignored(tmp_path):
    path = tmp_path / "dictionary.json"
    path.write_text(json.dumps({"terms": "abc", "replacements": {"a": "b"}}), encoding="utf-8")
    d = Dictionary(path)
    assert d.terms() == []
    assert d.replacements() == []


def test_save_failure_is_reported_not_raised(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("i am a file", encoding="utf-8")
    d = Dictionary(blocker / "dictionary.json")
    assert d.add_term("Kanishka")
    assert d.terms() == ["Kanishka"]
    assert d.last_save_error
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_dictionary.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'whisperfree.dictionary'`

- [ ] **Step 3: Implement `whisperfree/dictionary.py`**

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_dictionary.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whisperfree/dictionary.py tests/test_dictionary.py
git commit -m "Add dictionary store for custom terms and replacement rules"
```
(with the Co-Authored-By trailer from Global Constraints)

---

### Task 2: Launch-on-startup module

**Files:**
- Create: `whisperfree/startup.py`
- Create: `run_whisperfree.pyw` (repo root)
- Modify: `whisperfree/config.py` (`resolve_api_key` + new `PROJECT_ENV_PATH` constant)
- Test: `tests/test_startup.py`

**Interfaces:**
- Consumes: `whisperfree.utils.logger.get_logger`.
- Produces (module `whisperfree.startup`):
  `RUN_KEY: str`, `VALUE_NAME = "WhisperFree"`, `LAUNCHER_SCRIPT: Path`,
  `is_supported() -> bool`, `launch_command() -> str`,
  `read_command(value_name: str = VALUE_NAME) -> Optional[str]`,
  `is_enabled(value_name: str = VALUE_NAME) -> bool`,
  `set_enabled(enabled: bool, value_name: str = VALUE_NAME) -> None` (raises `OSError` on registry failure),
  `refresh_if_stale(value_name: str = VALUE_NAME) -> bool`.
- Produces (module `whisperfree.config`): `PROJECT_ENV_PATH: Path`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_startup.py`:

```python
import sys
import uuid

import pytest

from whisperfree import config as config_module
from whisperfree import startup
from whisperfree.config import AppConfig


def test_launch_command_frozen(monkeypatch):
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", r"C:\Apps\WhisperFree\WhisperFree.exe")
    assert startup.launch_command() == '"C:\\Apps\\WhisperFree\\WhisperFree.exe"'


def test_launch_command_source_prefers_pythonw(monkeypatch, tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    (tmp_path / "pythonw.exe").write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert startup.launch_command() == f'"{tmp_path / "pythonw.exe"}" "{startup.LAUNCHER_SCRIPT}"'


def test_launch_command_source_falls_back_to_python(monkeypatch, tmp_path):
    (tmp_path / "python.exe").write_bytes(b"")
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "python.exe"))
    assert startup.launch_command() == f'"{tmp_path / "python.exe"}" "{startup.LAUNCHER_SCRIPT}"'


def test_launcher_script_exists_and_is_absolute():
    assert startup.LAUNCHER_SCRIPT.is_absolute()
    assert startup.LAUNCHER_SCRIPT.exists()


def test_resolve_api_key_reads_project_env(monkeypatch, tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text("WF_TEST_API_KEY=from-project-env\n", encoding="utf-8")
    monkeypatch.setattr(config_module, "PROJECT_ENV_PATH", env_file)
    monkeypatch.setenv("WF_TEST_API_KEY", "placeholder")  # records original state for undo
    monkeypatch.delenv("WF_TEST_API_KEY")
    monkeypatch.chdir(tmp_path.parent)  # CWD is not the project
    assert AppConfig(api_key_env="WF_TEST_API_KEY").resolve_api_key() == "from-project-env"


def test_unsupported_platform_is_noop(monkeypatch):
    monkeypatch.setattr(startup, "is_supported", lambda: False)
    assert startup.read_command() is None
    assert startup.is_enabled() is False
    startup.set_enabled(True)  # must not raise


@pytest.fixture
def value_name():
    name = f"WhisperFreeTest-{uuid.uuid4().hex[:8]}"
    yield name
    startup.set_enabled(False, name)


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_registry_round_trip(value_name):
    assert not startup.is_enabled(value_name)
    startup.set_enabled(True, value_name)
    assert startup.is_enabled(value_name)
    assert startup.read_command(value_name) == startup.launch_command()
    startup.set_enabled(False, value_name)
    assert not startup.is_enabled(value_name)
    startup.set_enabled(False, value_name)  # deleting twice is fine


@pytest.mark.skipif(sys.platform != "win32", reason="Windows registry only")
def test_refresh_if_stale_rewrites_old_path(value_name):
    import winreg

    assert startup.refresh_if_stale(value_name) is False  # not enabled: nothing to do
    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, startup.RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, '"C:\\old\\WhisperFree.exe"')
    assert startup.refresh_if_stale(value_name) is True
    assert startup.read_command(value_name) == startup.launch_command()
    assert startup.refresh_if_stale(value_name) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_startup.py -q`
Expected: `ImportError: cannot import name 'startup'`

- [ ] **Step 3: Create the launcher script `run_whisperfree.pyw`**

```python
"""Windowless launcher used by "Launch on startup" when running from source.

Living at the repo root puts the project on sys.path no matter which working
directory Windows starts us in.
"""

from whisperfree.app import main


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Implement `whisperfree/startup.py`**

```python
"""Launch-on-startup support via the per-user Windows Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WhisperFree"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SCRIPT = PROJECT_ROOT / "run_whisperfree.pyw"


def is_supported() -> bool:
    """Launch on startup is only implemented for Windows."""
    return sys.platform == "win32"


def launch_command() -> str:
    """Return the command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'
    interpreter = Path(sys.executable)
    pythonw = interpreter.parent / "pythonw.exe"
    if pythonw.exists():
        interpreter = pythonw
    return f'"{interpreter}" "{LAUNCHER_SCRIPT}"'


def read_command(value_name: str = VALUE_NAME) -> Optional[str]:
    """Return the registered command, or None when not registered."""
    if not is_supported():
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    return str(value)


def is_enabled(value_name: str = VALUE_NAME) -> bool:
    """Whether WhisperFree is registered to launch at sign-in."""
    try:
        return read_command(value_name) is not None
    except OSError as exc:
        logger.warning("Could not read startup registry value: {}", exc)
        return False


def set_enabled(enabled: bool, value_name: str = VALUE_NAME) -> None:
    """Register or unregister launch at sign-in. Raises OSError on registry failure."""
    if not is_supported():
        return
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, value_name)
            except FileNotFoundError:
                pass
    logger.info("Launch on startup {}", "enabled" if enabled else "disabled")


def refresh_if_stale(value_name: str = VALUE_NAME) -> bool:
    """Rewrite the registered command if the app moved. Returns True when rewritten."""
    current = read_command(value_name)
    if current is None or current == launch_command():
        return False
    set_enabled(True, value_name)
    logger.info("Updated stale startup command: {}", current)
    return True
```

- [ ] **Step 5: Update `whisperfree/config.py`**

Add below `CONFIG_PATH = CONFIG_DIR / "config.json"`:

```python
PROJECT_ENV_PATH = Path(__file__).resolve().parent.parent / ".env"
```

Replace the body of `resolve_api_key` with:

```python
    def resolve_api_key(self) -> Optional[str]:
        """Return the OpenAI API key using env var + .env convenience loading."""
        # Earlier files win: load_dotenv never overrides variables that are already set.
        load_dotenv(CONFIG_DIR / ".env")
        load_dotenv(PROJECT_ENV_PATH)  # repo-root .env, found by absolute path (autostart CWD differs)
        load_dotenv()  # CWD fallback for dev convenience
        return os.environ.get(self.api_key_env)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_startup.py -q`
Expected: all pass (registry tests run on this Windows machine).

- [ ] **Step 7: Commit**

```bash
git add whisperfree/startup.py run_whisperfree.pyw whisperfree/config.py tests/test_startup.py
git commit -m "Add launch-on-startup registry helpers and windowless launcher"
```

---

### Task 3: History durations, stats, and recording length

**Files:**
- Modify: `whisperfree/history.py`
- Modify: `whisperfree/audio.py` (add `AudioRecorder.last_duration`)
- Test: `tests/test_history.py`, `tests/test_audio.py`

**Interfaces:**
- Produces:
  - `TranscriptionEntry(timestamp: datetime, text: str, words: int, duration: Optional[float] = None)`
  - `TranscriptionHistory.add_entry(text: str, timestamp: Optional[datetime] = None, duration: Optional[float] = None) -> TranscriptionEntry`
  - `day_streak(entries: Iterable[TranscriptionEntry], today: date) -> int`
  - `average_wpm(entries: Iterable[TranscriptionEntry]) -> Optional[float]`
  - `MIN_WPM_DURATION = 1.0`
  - `AudioRecorder.last_duration -> float` (property, seconds of audio captured in the latest recording)

- [ ] **Step 1: Write the failing tests**

Create `tests/test_history.py`:

```python
import json
from datetime import date, datetime, timedelta

from whisperfree.history import (
    TranscriptionEntry,
    TranscriptionHistory,
    average_wpm,
    day_streak,
)


def local(year, month, day, hour=12):
    return datetime(year, month, day, hour, 0).astimezone()


def entry(ts, words=10, duration=None):
    return TranscriptionEntry(timestamp=ts, text="x " * words, words=words, duration=duration)


def test_add_entry_persists_duration(tmp_path):
    history = TranscriptionHistory(tmp_path / "history.jsonl")
    history.add_entry("hello there world", duration=2.5)
    [loaded] = TranscriptionHistory(tmp_path / "history.jsonl").entries()
    assert loaded.duration == 2.5
    assert loaded.words == 3


def test_entry_without_duration_omits_key(tmp_path):
    path = tmp_path / "history.jsonl"
    TranscriptionHistory(path).add_entry("hi")
    assert "duration" not in json.loads(path.read_text(encoding="utf-8").splitlines()[0])


def test_legacy_entries_load_without_duration(tmp_path):
    path = tmp_path / "history.jsonl"
    path.write_text(
        json.dumps({"timestamp": "2025-10-19T22:38:00+00:00", "text": "Have a great day.", "words": 4}) + "\n",
        encoding="utf-8",
    )
    [loaded] = TranscriptionHistory(path).entries()
    assert loaded.duration is None
    assert loaded.words == 4


def test_day_streak_counts_consecutive_days_ending_today():
    today = date(2026, 9, 24)
    entries = [entry(local(2026, 9, 24)), entry(local(2026, 9, 23)), entry(local(2026, 9, 23, 8)), entry(local(2026, 9, 22))]
    assert day_streak(entries, today) == 3


def test_day_streak_alive_if_last_dictation_was_yesterday():
    today = date(2026, 9, 24)
    entries = [entry(local(2026, 9, 23)), entry(local(2026, 9, 22))]
    assert day_streak(entries, today) == 2


def test_day_streak_broken_by_gap():
    today = date(2026, 9, 24)
    assert day_streak([entry(local(2026, 9, 22))], today) == 0
    assert day_streak([entry(local(2026, 9, 24)), entry(local(2026, 9, 22))], today) == 1
    assert day_streak([], today) == 0


def test_average_wpm_uses_only_timed_entries():
    ts = local(2026, 9, 24)
    entries = [
        entry(ts, words=10, duration=6.0),
        entry(ts, words=20, duration=12.0),
        entry(ts, words=500, duration=None),  # legacy: ignored
        entry(ts, words=5, duration=0.4),  # too short to be meaningful: ignored
    ]
    assert average_wpm(entries) == 100.0


def test_average_wpm_none_without_timed_entries():
    assert average_wpm([entry(local(2026, 9, 24))]) is None
    assert average_wpm([]) is None
```

Create `tests/test_audio.py`:

```python
import numpy as np

from whisperfree.audio import AudioRecorder
from whisperfree.config import AppConfig


def test_last_duration_counts_captured_frames():
    recorder = AudioRecorder(AppConfig(sample_rate=16000))
    assert recorder.last_duration == 0.0
    block = np.zeros((1600, 1), dtype=np.int16)
    recorder._callback(block, 1600, None, None)
    recorder._callback(block, 1600, None, None)
    assert recorder.last_duration == 0.2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_history.py tests/test_audio.py -q`
Expected: ImportError for `average_wpm` / `day_streak`; AttributeError `last_duration`.

- [ ] **Step 3: Implement history changes in `whisperfree/history.py`**

1. Change the imports line `from datetime import datetime, timezone` to `from datetime import date, datetime, timedelta, timezone`.
2. Add after `HISTORY_PATH = ...`:

```python
MIN_WPM_DURATION = 1.0  # seconds; shorter clips give meaningless words-per-minute
```

3. Replace the `TranscriptionEntry` class with:

```python
@dataclass(frozen=True)
class TranscriptionEntry:
    """Represents a single transcription event."""

    timestamp: datetime
    text: str
    words: int
    duration: Optional[float] = None  # seconds of recorded audio, when known

    def to_dict(self) -> dict:
        data = {
            "timestamp": self.timestamp.isoformat(),
            "text": self.text,
            "words": self.words,
        }
        if self.duration is not None:
            data["duration"] = round(self.duration, 3)
        return data

    @staticmethod
    def from_dict(data: dict) -> Optional["TranscriptionEntry"]:
        """Create an entry from raw JSON data."""
        try:
            timestamp = datetime.fromisoformat(data["timestamp"])
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            text = str(data.get("text", ""))
            words = int(data.get("words", _word_count(text)))
            raw_duration = data.get("duration")
            duration = float(raw_duration) if raw_duration is not None else None
        except Exception as exc:  # pragma: no cover - defensive parsing
            logger.warning("Skipping malformed history entry: {} (error={})", data, exc)
            return None
        return TranscriptionEntry(timestamp=timestamp, text=text, words=words, duration=duration)
```

4. Replace `add_entry`'s signature and entry construction:

```python
    def add_entry(
        self,
        text: str,
        timestamp: Optional[datetime] = None,
        duration: Optional[float] = None,
    ) -> TranscriptionEntry:
        """Append a transcription event to the history log."""
        ts = timestamp or datetime.now(timezone.utc)
        entry = TranscriptionEntry(timestamp=ts, text=text, words=_word_count(text), duration=duration)
```
(the rest of the method body is unchanged)

5. Append at the end of the module:

```python
def day_streak(entries: Iterable[TranscriptionEntry], today: date) -> int:
    """Consecutive local days with dictation, ending today (or yesterday if none yet today)."""
    days = {entry.timestamp.astimezone().date() for entry in entries}
    one_day = timedelta(days=1)
    if today in days:
        cursor = today
    elif today - one_day in days:
        cursor = today - one_day
    else:
        return 0
    streak = 0
    while cursor in days:
        streak += 1
        cursor -= one_day
    return streak


def average_wpm(entries: Iterable[TranscriptionEntry]) -> Optional[float]:
    """Words per minute across entries with a known duration, or None if there are none."""
    words = 0
    seconds = 0.0
    for entry in entries:
        if entry.duration is not None and entry.duration >= MIN_WPM_DURATION:
            words += entry.words
            seconds += entry.duration
    if seconds <= 0:
        return None
    return words / (seconds / 60.0)
```

- [ ] **Step 4: Add `last_duration` to `AudioRecorder` in `whisperfree/audio.py`**

Insert directly after the `gain_multiplier` property:

```python
    @property
    def last_duration(self) -> float:
        """Seconds of audio captured by the current or most recent recording."""
        with self._lock:
            return self._frames_recorded / float(self._config.sample_rate)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_history.py tests/test_audio.py -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add whisperfree/history.py whisperfree/audio.py tests/test_history.py tests/test_audio.py
git commit -m "Record dictation duration and add streak and WPM stats"
```

---

### Task 4: Wire dictionary and duration into the transcription pipeline

**Files:**
- Modify: `whisperfree/transcribe.py`
- Modify: `whisperfree/app.py`
- Test: `tests/test_pipeline.py`

**Interfaces:**
- Consumes: `Dictionary` (Task 1), `startup.refresh_if_stale` (Task 2), `TranscriptionHistory.add_entry(..., duration=)` and `AudioRecorder.last_duration` (Task 3).
- Produces:
  - `ApiTranscriber.transcribe(audio_bytes: bytes, language: str = "auto", prompt: str = "") -> TranscriptionResult`
  - `TranscriptionRouter.transcribe(audio_bytes: bytes, prompt: str = "") -> TranscriptionResult`
  - `WhisperFreeController._dictionary: Dictionary` (Task 10 passes it to the window)
  - `WhisperFreeController._process_session(audio_bytes: bytes, duration: Optional[float] = None) -> None`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_pipeline.py`:

```python
from types import SimpleNamespace

import whisperfree.app as app_module
from whisperfree.app import WhisperFreeController
from whisperfree.config import AppConfig
from whisperfree.dictionary import Dictionary
from whisperfree.history import TranscriptionHistory
from whisperfree.transcribe import ApiTranscriber, TranscriptionResult


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _FakeTranscriber:
    def __init__(self, text):
        self.text = text
        self.prompts = []

    def transcribe(self, audio_bytes, prompt=""):
        self.prompts.append(prompt)
        return TranscriptionResult(text=self.text)


def _controller(tmp_path, text, dictionary):
    return SimpleNamespace(
        _transcriber=_FakeTranscriber(text),
        _dictionary=dictionary,
        _config=AppConfig(),
        _history=TranscriptionHistory(tmp_path / "history.jsonl"),
        toast_requested=_Signal(),
        idle_requested=_Signal(),
        history_entry_added=_Signal(),
    )


def test_pipeline_applies_dictionary_and_records_duration(tmp_path, monkeypatch):
    pasted = []
    monkeypatch.setattr(app_module, "paste_text", lambda text, **kwargs: pasted.append(text) or True)
    dictionary = Dictionary(tmp_path / "dictionary.json")
    dictionary.add_term("5Point")
    dictionary.add_replacement("five point", "5Point")
    fake = _controller(tmp_path, "I work at five point.", dictionary)

    WhisperFreeController._process_session(fake, b"RIFF", 3.0)

    assert fake._transcriber.prompts == ["Glossary: 5Point."]
    assert pasted == ["I work at 5Point."]
    [saved] = fake._history.entries()
    assert saved.text == "I work at 5Point."
    assert saved.duration == 3.0
    assert fake.history_entry_added.calls and fake.idle_requested.calls


def test_blanked_transcript_is_not_pasted(tmp_path, monkeypatch):
    pasted = []
    monkeypatch.setattr(app_module, "paste_text", lambda text, **kwargs: pasted.append(text) or True)
    dictionary = Dictionary(tmp_path / "dictionary.json")
    dictionary.add_replacement("um", "")
    fake = _controller(tmp_path, "Um.", dictionary)
    fake._transcriber.text = "um"

    WhisperFreeController._process_session(fake, b"RIFF", 1.0)

    assert pasted == []
    assert fake._history.entries() == []
    assert fake.toast_requested.calls == [("Nothing to paste", 2000)]


class _FakeTranscriptions:
    def __init__(self):
        self.params = None

    def create(self, **params):
        self.params = params
        return SimpleNamespace(text=" hello ", language="en")


def _api_with_fake_client():
    api = ApiTranscriber("sk-test")
    transcriptions = _FakeTranscriptions()
    api._client = SimpleNamespace(audio=SimpleNamespace(transcriptions=transcriptions))
    return api, transcriptions


def test_api_transcriber_sends_prompt_when_given():
    api, transcriptions = _api_with_fake_client()
    result = api.transcribe(b"RIFF", prompt="Glossary: 5Point.")
    assert transcriptions.params["prompt"] == "Glossary: 5Point."
    assert result.text == "hello"


def test_api_transcriber_omits_empty_prompt():
    api, transcriptions = _api_with_fake_client()
    api.transcribe(b"RIFF")
    assert "prompt" not in transcriptions.params
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_pipeline.py -q`
Expected: failures — `transcribe() got an unexpected keyword argument 'prompt'`, and `_process_session()` takes 2 positional arguments.

- [ ] **Step 3: Add `prompt` to `whisperfree/transcribe.py`**

`ApiTranscriber.transcribe`:

```python
    def transcribe(self, audio_bytes: bytes, language: str = "auto", prompt: str = "") -> TranscriptionResult:
        if not audio_bytes:
            return TranscriptionResult(text="", language=language)
        file_tuple = ("audio.wav", audio_bytes, "audio/wav")
        params = {"model": self._model_name, "file": file_tuple}
        if language and language.lower() != "auto":
            params["language"] = language
        if prompt:
            params["prompt"] = prompt
        logger.info("Invoking OpenAI Whisper API model={}", self._model_name)
```
(rest unchanged)

`TranscriptionRouter.transcribe`:

```python
    def transcribe(self, audio_bytes: bytes, prompt: str = "") -> TranscriptionResult:
        """Transcribe audio using the OpenAI Whisper API."""
        return self._get_api().transcribe(audio_bytes, language=self._config.language, prompt=prompt)
```

- [ ] **Step 4: Update `whisperfree/app.py`**

1. Imports — add:

```python
from whisperfree import startup
from whisperfree.dictionary import Dictionary
```

2. In `WhisperFreeController.__init__`, right after `self._history = TranscriptionHistory()` add:

```python
        self._dictionary = Dictionary()
```

3. Replace `_handle_push_to_talk_stop`'s last line `self._executor.submit(self._process_session, audio_bytes)` with:

```python
        duration = self._audio.last_duration
        self._executor.submit(self._process_session, audio_bytes, duration)
```

4. Replace `_process_session` entirely with:

```python
    def _process_session(self, audio_bytes: bytes, duration: Optional[float] = None) -> None:
        logger.info("Processing transcription payload of {} bytes", len(audio_bytes))
        try:
            result = self._transcriber.transcribe(audio_bytes, prompt=self._dictionary.build_prompt())
        except Exception as exc:
            logger.exception("Transcription failed: {}", exc)
            self.toast_requested.emit("Transcription failed", 2500)
            self.idle_requested.emit()
            return

        transcribed_text = self._dictionary.apply_replacements(result.text).strip()

        if not transcribed_text:
            self.toast_requested.emit("Nothing to paste", 2000)
            self.idle_requested.emit()
            return

        success = paste_text(
            transcribed_text,
            append_newline=self._config.append_newline,
            retries=self._config.paste_retries,
        )
        entry = self._history.add_entry(transcribed_text, duration=duration)
        self.history_entry_added.emit(entry)
        if not success:
            self.toast_requested.emit("Paste failed", 2500)
        self.idle_requested.emit()
```

5. In `main()`, after `config = load_config()` add:

```python
    try:
        startup.refresh_if_stale()
    except OSError as exc:
        logger.warning("Could not refresh launch-on-startup entry: {}", exc)
```

- [ ] **Step 5: Run the full suite**

Run: `py -3.11 -m pytest tests -q`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add whisperfree/transcribe.py whisperfree/app.py tests/test_pipeline.py
git commit -m "Apply dictionary prompt and replacements in transcription pipeline"
```

---

### Task 5: UI package, light theme, and shared widgets

**Files:**
- Move: `whisperfree/ui.py` → `whisperfree/ui/window.py` (`git mv`)
- Create: `whisperfree/ui/__init__.py`, `whisperfree/ui/theme.py`, `whisperfree/ui/widgets.py`
- Modify: `whisperfree/ui/window.py` (asset path only), `whisperfree/app.py` (apply theme)
- Create: `tests/conftest.py`
- Test: `tests/test_theme_widgets.py`

**Interfaces:**
- Produces (`whisperfree.ui.theme`): colour constants `BACKGROUND, SURFACE, SURFACE_HOVER, BORDER, BORDER_STRONG, TEXT, TEXT_SECONDARY, TEXT_MUTED, ACCENT, ACCENT_HOVER, ACCENT_SOFT, DANGER`; `STYLESHEET: str`; `ui_font() -> QFont`; `build_palette() -> QPalette`; `apply_theme(app: QApplication) -> None`.
- Produces (`whisperfree.ui.widgets`): `asset_path(name) -> Path`, `friendly_username() -> str`, `format_day(dt, today: Optional[date] = None) -> str`, `format_time(dt) -> str`, `make_label(text, object_name, *, wrap=False) -> QLabel`, `set_object_name(widget, name) -> None` (re-polishes), `clear_layout(layout) -> None`, `divider() -> QFrame`, `scroll_page(content) -> QScrollArea`, classes `Card` (attribute `body: QVBoxLayout`), `ToggleSwitch`, `SettingRow(title, description, control)`, `HistoryRow(entry)` (attributes `text_label`, `copy_button`), `FlowLayout(parent=None, spacing=8)`.
- Produces (`whisperfree.ui`): `ControlPanelWindow`, `TrayController` (re-exported).
- Produces (`tests/conftest.py`): session fixture `qapp`.

- [ ] **Step 1: Move the module and create the package shim**

```bash
mkdir whisperfree/ui
git mv whisperfree/ui.py whisperfree/ui/window.py
```

Create `whisperfree/ui/__init__.py`:

```python
"""Control panel and tray UI built with PyQt6."""

from whisperfree.ui.window import ControlPanelWindow, TrayController

__all__ = ["ControlPanelWindow", "TrayController"]
```

In `whisperfree/ui/window.py`, delete the whole `_asset_path` function at the bottom of the file and add this import near the other `whisperfree` imports (the existing call sites keep using `_asset_path`):

```python
from whisperfree.ui.widgets import asset_path as _asset_path
```

- [ ] **Step 2: Create `tests/conftest.py`**

```python
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402


@pytest.fixture(scope="session")
def qapp():
    from PyQt6 import QtWidgets

    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    yield app
```

- [ ] **Step 3: Write the failing tests**

Create `tests/test_theme_widgets.py`:

```python
from datetime import date, datetime

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.history import TranscriptionEntry
from whisperfree.ui import theme
from whisperfree.ui.widgets import (
    FlowLayout,
    HistoryRow,
    ToggleSwitch,
    asset_path,
    format_day,
    format_time,
)


def test_apply_theme_forces_light_palette(qapp):
    theme.apply_theme(qapp)
    palette = qapp.palette()
    assert palette.color(QtGui.QPalette.ColorRole.Window).name().upper() == theme.BACKGROUND
    assert palette.color(QtGui.QPalette.ColorRole.WindowText).name().upper() == theme.TEXT
    assert palette.color(QtGui.QPalette.ColorRole.Base).name().upper() == theme.SURFACE
    assert qapp.style().name().lower() == "fusion"


def test_stylesheet_braces_balance():
    assert theme.STYLESHEET.count("{") == theme.STYLESHEET.count("}")
    assert "#Card" in theme.STYLESHEET and "#NavButton" in theme.STYLESHEET


def test_ui_font_prefers_segoe_variable():
    font = theme.ui_font()
    assert font.families()[0] == "Segoe UI Variable Text"
    assert font.pixelSize() == 13


def test_asset_path_points_at_repo_assets():
    assert asset_path("app_icon.ico").exists()


def test_format_day_relative_labels():
    today = date(2026, 9, 24)
    assert format_day(datetime(2026, 9, 24, 9).astimezone(), today) == "Today"
    assert format_day(datetime(2026, 9, 23, 9).astimezone(), today) == "Yesterday"
    assert format_day(datetime(2026, 9, 21, 9).astimezone(), today) == "Monday, September 21"
    assert format_day(datetime(2025, 10, 19, 9).astimezone(), today) == "Sunday, October 19, 2025"


def test_format_time_drops_leading_zero():
    assert format_time(datetime(2026, 9, 24, 9, 5).astimezone()) == "9:05 AM"
    assert format_time(datetime(2026, 9, 24, 22, 38).astimezone()) == "10:38 PM"


def test_toggle_switch_toggles_on_click(qapp):
    toggle = ToggleSwitch()
    seen = []
    toggle.toggled.connect(seen.append)
    toggle.click()
    assert toggle.isChecked() and seen == [True]
    toggle.blockSignals(True)
    toggle.setChecked(False)
    toggle.blockSignals(False)
    assert not toggle.grab().isNull()  # paints without animation state
    assert toggle.sizeHint() == QtCore.QSize(36, 20)


def test_flow_layout_wraps(qapp):
    container = QtWidgets.QWidget()
    layout = FlowLayout(container, spacing=8)
    for _ in range(5):
        label = QtWidgets.QLabel("x")
        label.setFixedSize(80, 20)
        layout.addWidget(label)
    assert layout.count() == 5
    assert layout.heightForWidth(1000) == 20
    assert layout.heightForWidth(200) == 20 * 3 + 8 * 2


def test_history_row_copy(qapp):
    entry = TranscriptionEntry(timestamp=datetime(2026, 9, 24, 10).astimezone(), text="  Hello world  ", words=2)
    row = HistoryRow(entry)
    assert row.text_label.text() == "Hello world"
    row.copy_button.click()
    assert QtWidgets.QApplication.clipboard().text() == "Hello world"
    assert row.copy_button.text() == "Copied"
```

- [ ] **Step 4: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_theme_widgets.py -q`
Expected: `ImportError: cannot import name 'theme' from 'whisperfree.ui'` (or ModuleNotFoundError for widgets).

- [ ] **Step 5: Create `whisperfree/ui/theme.py`**

```python
"""Light theme: palette constants and the global control panel stylesheet."""

from __future__ import annotations

from PyQt6 import QtGui, QtWidgets


BACKGROUND = "#F7F7F8"
SURFACE = "#FFFFFF"
SURFACE_HOVER = "#F2F2F5"
BORDER = "#E6E6EA"
BORDER_STRONG = "#D4D4DA"
TEXT = "#1C1B22"
TEXT_SECONDARY = "#6B6A75"
TEXT_MUTED = "#9A99A3"
ACCENT = "#4332D8"
ACCENT_HOVER = "#3727B7"
ACCENT_SOFT = "#EEECFC"
DANGER = "#C93636"

FONT_FAMILIES = ["Segoe UI Variable Text", "Segoe UI"]
BASE_FONT_PX = 13


STYLESHEET = f"""
QMainWindow {{ background: {BACKGROUND}; }}

QFrame#Sidebar {{ background: {BACKGROUND}; border: none; border-right: 1px solid {BORDER}; }}
QLabel#AppName {{ font-size: 17px; font-weight: 600; color: {TEXT}; }}
QLabel#SidebarFooter {{ font-size: 12px; color: {TEXT_MUTED}; }}
QPushButton#NavButton {{
    background: transparent; border: none; border-radius: 8px;
    padding: 8px 12px; text-align: left;
    font-size: 13px; font-weight: 500; color: {TEXT_SECONDARY};
}}
QPushButton#NavButton:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#NavButton:checked {{ background: {ACCENT_SOFT}; color: {ACCENT}; font-weight: 600; }}

QLabel#PageTitle {{ font-size: 26px; font-weight: 600; color: {TEXT}; }}
QLabel#PageSubtitle {{ font-size: 13px; color: {TEXT_SECONDARY}; }}
QLabel#SectionTitle {{ font-size: 15px; font-weight: 600; color: {TEXT}; }}
QLabel#SettingTitle {{ font-size: 13px; font-weight: 600; color: {TEXT}; }}
QLabel#Body {{ font-size: 13px; color: {TEXT}; }}
QLabel#Caption {{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#Muted {{ font-size: 12px; color: {TEXT_MUTED}; }}
QLabel#DayHeader {{ font-size: 12px; font-weight: 600; color: {TEXT_MUTED}; padding-top: 12px; }}
QLabel#StatValue {{ font-size: 24px; font-weight: 600; color: {TEXT}; }}
QLabel#StatusError {{ font-size: 12px; color: {DANGER}; }}
QLabel#StatusOk {{ font-size: 12px; color: {TEXT_SECONDARY}; }}
QLabel#RuleMatch {{ font-size: 13px; font-weight: 600; color: {TEXT}; }}

QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 12px; }}
QFrame#HintBanner {{ background: {ACCENT_SOFT}; border: none; border-radius: 10px; }}
QLabel#HintText {{ font-size: 13px; font-weight: 500; color: {ACCENT}; }}
QFrame#HistoryRow {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#HistoryRow:hover {{ border-color: {BORDER_STRONG}; }}
QFrame#Divider {{ background: {BORDER}; border: none; min-height: 1px; max-height: 1px; }}

QPushButton#PrimaryButton {{
    background: {ACCENT}; color: #FFFFFF; border: none; border-radius: 8px;
    padding: 7px 16px; font-weight: 600;
}}
QPushButton#PrimaryButton:hover {{ background: {ACCENT_HOVER}; }}
QPushButton#PrimaryButton:disabled {{ background: {BORDER_STRONG}; }}
QPushButton#SecondaryButton {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 14px; font-weight: 500;
}}
QPushButton#SecondaryButton:hover {{ background: {SURFACE_HOVER}; }}
QPushButton#SecondaryButton:disabled {{ color: {TEXT_MUTED}; }}
QPushButton#GhostButton, QPushButton#DangerGhostButton {{
    background: transparent; color: {TEXT_SECONDARY}; border: none; border-radius: 6px;
    padding: 4px 8px; font-size: 12px; font-weight: 500;
}}
QPushButton#GhostButton:hover {{ background: {SURFACE_HOVER}; color: {TEXT}; }}
QPushButton#DangerGhostButton:hover {{ background: {SURFACE_HOVER}; color: {DANGER}; }}
QPushButton#LinkButton {{ background: transparent; border: none; padding: 0; color: {ACCENT}; font-weight: 600; }}
QPushButton#LinkButton:hover {{ color: {ACCENT_HOVER}; }}

QLineEdit, QComboBox {{
    background: {SURFACE}; color: {TEXT}; border: 1px solid {BORDER_STRONG}; border-radius: 8px;
    padding: 6px 10px; min-height: 20px;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}
QLineEdit:focus, QComboBox:focus {{ border-color: {ACCENT}; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{
    background: {SURFACE}; border: 1px solid {BORDER}; outline: none;
    selection-background-color: {ACCENT_SOFT}; selection-color: {TEXT};
}}

QSlider::groove:horizontal {{ height: 4px; background: {BORDER}; border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{
    background: {SURFACE}; border: 1px solid {BORDER_STRONG};
    width: 16px; height: 16px; margin: -7px 0; border-radius: 8px;
}}

QTabWidget::pane {{ border: none; }}
QTabBar::tab {{
    background: transparent; color: {TEXT_SECONDARY}; border: none;
    border-bottom: 2px solid transparent; padding: 8px 14px; margin-right: 4px; font-weight: 500;
}}
QTabBar::tab:hover {{ color: {TEXT}; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}

QFrame#Chip {{ background: {ACCENT_SOFT}; border: none; border-radius: 14px; }}
QLabel#ChipText {{ color: {ACCENT}; font-weight: 500; }}
QPushButton#ChipRemove {{ background: transparent; border: none; color: {ACCENT}; font-weight: 700; padding: 0 2px; }}
QPushButton#ChipRemove:hover {{ color: {DANGER}; }}

QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 0; }}
QScrollBar::handle:vertical {{ background: {BORDER_STRONG}; border-radius: 3px; min-height: 32px; margin: 2px; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
"""


def ui_font() -> QtGui.QFont:
    """Base font for the control panel."""
    font = QtGui.QFont()
    font.setFamilies(FONT_FAMILIES)
    font.setPixelSize(BASE_FONT_PX)
    return font


def build_palette() -> QtGui.QPalette:
    """Light palette so Windows dark mode never leaks into the app."""
    role = QtGui.QPalette.ColorRole
    palette = QtGui.QPalette()
    colours = {
        role.Window: BACKGROUND,
        role.WindowText: TEXT,
        role.Base: SURFACE,
        role.AlternateBase: BACKGROUND,
        role.Text: TEXT,
        role.Button: SURFACE,
        role.ButtonText: TEXT,
        role.ToolTipBase: SURFACE,
        role.ToolTipText: TEXT,
        role.PlaceholderText: TEXT_MUTED,
        role.Highlight: ACCENT,
        role.HighlightedText: "#FFFFFF",
        role.BrightText: "#FFFFFF",
        role.Link: ACCENT,
    }
    for colour_role, value in colours.items():
        palette.setColor(colour_role, QtGui.QColor(value))
    disabled = QtGui.QPalette.ColorGroup.Disabled
    for colour_role in (role.WindowText, role.Text, role.ButtonText):
        palette.setColor(disabled, colour_role, QtGui.QColor(TEXT_MUTED))
    return palette


def apply_theme(app: QtWidgets.QApplication) -> None:
    """Use Fusion with a fixed light palette app-wide (message boxes, tray menu, panel)."""
    app.setStyle("Fusion")
    app.setPalette(build_palette())
```

- [ ] **Step 6: Create `whisperfree/ui/widgets.py`**

```python
"""Shared building blocks for the control panel pages."""

from __future__ import annotations

import getpass
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.history import TranscriptionEntry
from whisperfree.ui import theme


def asset_path(name: str) -> Path:
    """Locate a bundled asset, both from source and inside a PyInstaller build."""
    if getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS) / "assets"
    else:
        base = Path(__file__).resolve().parents[2] / "assets"
    return base / name


def friendly_username() -> str:
    try:
        return getpass.getuser().split("\\")[-1].capitalize()
    except Exception:  # pragma: no cover - fallback
        return ""


def format_day(dt: datetime, today: Optional[date] = None) -> str:
    """"Today", "Yesterday", "Monday, September 21", or with the year if not this year."""
    local = dt.astimezone()
    day = local.date()
    today = today or date.today()
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    label = f"{local:%A, %B} {local.day}"
    if day.year != today.year:
        label += f", {day.year}"
    return label


def format_time(dt: datetime) -> str:
    return dt.astimezone().strftime("%I:%M %p").lstrip("0")


def make_label(text: str, object_name: str, *, wrap: bool = False) -> QtWidgets.QLabel:
    label = QtWidgets.QLabel(text)
    label.setObjectName(object_name)
    label.setWordWrap(wrap)
    return label


def set_object_name(widget: QtWidgets.QWidget, name: str) -> None:
    """Change objectName and re-apply the stylesheet rules that depend on it."""
    widget.setObjectName(name)
    style = widget.style()
    if style:
        style.unpolish(widget)
        style.polish(widget)


def clear_layout(layout: QtWidgets.QLayout) -> None:
    """Remove and destroy every item in a layout."""
    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.setParent(None)
            widget.deleteLater()
        elif item.layout() is not None:
            clear_layout(item.layout())


def divider() -> QtWidgets.QFrame:
    line = QtWidgets.QFrame()
    line.setObjectName("Divider")
    line.setFixedHeight(1)
    return line


def scroll_page(content: QtWidgets.QWidget) -> QtWidgets.QScrollArea:
    """Wrap page content in a frameless vertical scroll area."""
    area = QtWidgets.QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
    area.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(content)
    return area


class Card(QtWidgets.QFrame):
    """White rounded container; add children to ``card.body``."""

    def __init__(
        self,
        parent: Optional[QtWidgets.QWidget] = None,
        *,
        margins: tuple[int, int, int, int] = (20, 18, 20, 18),
        spacing: int = 12,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Card")
        self.body = QtWidgets.QVBoxLayout(self)
        self.body.setContentsMargins(*margins)
        self.body.setSpacing(spacing)


class ToggleSwitch(QtWidgets.QAbstractButton):
    """Pill-shaped on/off switch."""

    WIDTH = 36
    HEIGHT = 20
    KNOB_MARGIN = 2

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setCheckable(True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self._offset = 0.0
        self._animation = QtCore.QPropertyAnimation(self, b"offset", self)
        self._animation.setDuration(120)
        self._animation.setEasingCurve(QtCore.QEasingCurve.Type.OutCubic)
        self.toggled.connect(self._animate)

    def sizeHint(self) -> QtCore.QSize:
        return QtCore.QSize(self.WIDTH, self.HEIGHT)

    def hitButton(self, pos: QtCore.QPoint) -> bool:
        return self.rect().contains(pos)

    def _animate(self, checked: bool) -> None:
        self._animation.stop()
        self._animation.setStartValue(0.0 if checked else 1.0)
        self._animation.setEndValue(1.0 if checked else 0.0)
        self._animation.start()

    def _position(self) -> float:
        if self._animation.state() == QtCore.QAbstractAnimation.State.Running:
            return self._offset
        return 1.0 if self.isChecked() else 0.0

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        _ = event
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        track = QtGui.QColor(theme.ACCENT if self.isChecked() else theme.BORDER_STRONG)
        if not self.isEnabled():
            track.setAlpha(110)
        painter.setBrush(track)
        painter.drawRoundedRect(QtCore.QRectF(0, 0, self.WIDTH, self.HEIGHT), self.HEIGHT / 2, self.HEIGHT / 2)
        knob = self.HEIGHT - 2 * self.KNOB_MARGIN
        travel = self.WIDTH - knob - 2 * self.KNOB_MARGIN
        x = self.KNOB_MARGIN + self._position() * travel
        painter.setBrush(QtGui.QColor(theme.SURFACE))
        painter.drawEllipse(QtCore.QRectF(x, self.KNOB_MARGIN, knob, knob))

    def getOffset(self) -> float:
        return self._offset

    def setOffset(self, value: float) -> None:
        self._offset = value
        self.update()

    offset = QtCore.pyqtProperty(float, fget=getOffset, fset=setOffset)


class SettingRow(QtWidgets.QWidget):
    """Title + description on the left, a control on the right."""

    def __init__(
        self,
        title: str,
        description: str,
        control: QtWidgets.QWidget,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 4)
        layout.setSpacing(24)
        text = QtWidgets.QVBoxLayout()
        text.setSpacing(2)
        text.addWidget(make_label(title, "SettingTitle"))
        if description:
            text.addWidget(make_label(description, "Caption", wrap=True))
        layout.addLayout(text, 1)
        layout.addWidget(control, 0, QtCore.Qt.AlignmentFlag.AlignVCenter)


class HistoryRow(QtWidgets.QFrame):
    """One transcription: time, text, word count, copy button."""

    def __init__(self, entry: TranscriptionEntry, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryRow")
        self._text = entry.text.strip()

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 12, 12)
        layout.setSpacing(16)

        time_label = make_label(format_time(entry.timestamp), "Caption")
        time_label.setFixedWidth(64)
        layout.addWidget(time_label, 0, QtCore.Qt.AlignmentFlag.AlignTop)

        self.text_label = make_label(self._text, "Body", wrap=True)
        self.text_label.setTextInteractionFlags(QtCore.Qt.TextInteractionFlag.TextSelectableByMouse)
        self.text_label.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.IBeamCursor))
        layout.addWidget(self.text_label, 1)

        side = QtWidgets.QVBoxLayout()
        side.setSpacing(4)
        words = make_label(f"{entry.words} words", "Muted")
        words.setAlignment(QtCore.Qt.AlignmentFlag.AlignRight)
        side.addWidget(words)
        self.copy_button = QtWidgets.QPushButton("Copy")
        self.copy_button.setObjectName("GhostButton")
        self.copy_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.copy_button.clicked.connect(self._copy)
        side.addWidget(self.copy_button, 0, QtCore.Qt.AlignmentFlag.AlignRight)
        side.addStretch(1)
        layout.addLayout(side)

        self._reset_timer = QtCore.QTimer(self)
        self._reset_timer.setSingleShot(True)
        self._reset_timer.setInterval(1200)
        self._reset_timer.timeout.connect(lambda: self.copy_button.setText("Copy"))

    def _copy(self) -> None:
        clipboard = QtWidgets.QApplication.clipboard()
        if clipboard is not None:
            clipboard.setText(self._text)
        self.copy_button.setText("Copied")
        self._reset_timer.start()


class FlowLayout(QtWidgets.QLayout):
    """Lays children out left-to-right, wrapping onto new lines (used for term chips)."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None, spacing: int = 8) -> None:
        super().__init__(parent)
        self._items: List[QtWidgets.QLayoutItem] = []
        self._spacing = spacing
        self.setContentsMargins(0, 0, 0, 0)

    def addItem(self, item: QtWidgets.QLayoutItem) -> None:
        self._items.append(item)

    def count(self) -> int:
        return len(self._items)

    def itemAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        return self._items[index] if 0 <= index < len(self._items) else None

    def takeAt(self, index: int) -> Optional[QtWidgets.QLayoutItem]:
        return self._items.pop(index) if 0 <= index < len(self._items) else None

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        return self._do_layout(QtCore.QRect(0, 0, width, 0), test_only=True)

    def setGeometry(self, rect: QtCore.QRect) -> None:
        super().setGeometry(rect)
        self._do_layout(rect, test_only=False)

    def sizeHint(self) -> QtCore.QSize:
        return self.minimumSize()

    def minimumSize(self) -> QtCore.QSize:
        size = QtCore.QSize()
        for item in self._items:
            size = size.expandedTo(item.minimumSize())
        margins = self.contentsMargins()
        return size + QtCore.QSize(margins.left() + margins.right(), margins.top() + margins.bottom())

    def _do_layout(self, rect: QtCore.QRect, test_only: bool) -> int:
        margins = self.contentsMargins()
        area = rect.adjusted(margins.left(), margins.top(), -margins.right(), -margins.bottom())
        x, y, line_height = area.x(), area.y(), 0
        for item in self._items:
            hint = item.sizeHint()
            if x > area.x() and x + hint.width() > area.right() + 1:
                x = area.x()
                y += line_height + self._spacing
                line_height = 0
            if not test_only:
                item.setGeometry(QtCore.QRect(QtCore.QPoint(x, y), hint))
            x += hint.width() + self._spacing
            line_height = max(line_height, hint.height())
        return y + line_height - rect.y() + margins.bottom()
```

- [ ] **Step 7: Apply the theme in `whisperfree/app.py`**

Add import `from whisperfree.ui.theme import apply_theme` and, in `main()`, directly after `app.setApplicationName("WhisperFree")`:

```python
    apply_theme(app)
```

- [ ] **Step 8: Run the full suite and an import smoke check**

Run: `py -3.11 -m pytest tests -q`
Expected: all pass.
Run: `py -3.11 -c "import whisperfree.app; from whisperfree.ui import ControlPanelWindow, TrayController; print('ok')"`
Expected: `ok`

- [ ] **Step 9: Commit**

```bash
git add whisperfree/ui whisperfree/app.py tests/conftest.py tests/test_theme_widgets.py
git commit -m "Split UI into a package with a light theme and shared widgets"
```

---

### Task 6: Home page

**Files:**
- Create: `whisperfree/ui/home.py`
- Test: `tests/test_ui_home.py`

**Interfaces:**
- Consumes: `day_streak`, `average_wpm`, `TranscriptionEntry` (Task 3); `Card`, `HistoryRow`, `clear_layout`, `make_label`, `scroll_page` (Task 5).
- Produces: `greeting_for(hour: int) -> str`; `RECENT_LIMIT = 5`; `class HomePage(QWidget)` with `__init__(name: str, entries: Sequence[TranscriptionEntry], hotkey_label: str = "Ctrl+Win", today: Optional[date] = None, parent=None)`, signal `view_all_requested`, `add_entry(entry)`, `recent_count() -> int`, attributes `title_label`, `words_card`, `streak_card`, `wpm_card` (each a `StatCard` with `value_label`), `empty_label`, `view_all_button`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_home.py`:

```python
from datetime import date, datetime

from whisperfree.history import TranscriptionEntry
from whisperfree.ui.home import HomePage, greeting_for

TODAY = date(2026, 9, 24)


def entry(day, hour=12, words=10, duration=None, text=None):
    return TranscriptionEntry(
        timestamp=datetime(2026, 9, day, hour).astimezone(),
        text=text or f"entry on {day} at {hour}",
        words=words,
        duration=duration,
    )


def test_greeting_for_hour():
    assert greeting_for(6) == "Good morning"
    assert greeting_for(13) == "Good afternoon"
    assert greeting_for(20) == "Good evening"
    assert greeting_for(2) == "Good evening"


def test_stats_and_recent_list(qapp):
    entries = [
        entry(24, 15, words=10, duration=6.0),
        entry(24, 14, words=20, duration=12.0),
        entry(23),
        entry(22),
        entry(22, 9),
        entry(21),
        entry(20),
    ]
    page = HomePage("Kanishka", entries, today=TODAY)
    assert "Kanishka" in page.title_label.text()
    assert page.words_card.value_label.text() == "80"
    assert page.streak_card.value_label.text() == "5 days"
    assert page.wpm_card.value_label.text() == "100"
    assert page.recent_count() == 5
    assert page.empty_label.isHidden()


def test_empty_state(qapp):
    page = HomePage("", [], today=TODAY)
    assert page.words_card.value_label.text() == "0"
    assert page.streak_card.value_label.text() == "0 days"
    assert page.wpm_card.value_label.text() == "—"
    assert page.recent_count() == 0
    assert not page.empty_label.isHidden()


def test_add_entry_updates_stats(qapp):
    page = HomePage("K", [], today=TODAY)
    page.add_entry(entry(24, words=1234))
    assert page.words_card.value_label.text() == "1,234"
    assert page.streak_card.value_label.text() == "1 day"
    assert page.recent_count() == 1
    assert page.empty_label.isHidden()


def test_view_all_emits(qapp):
    page = HomePage("K", [entry(24)], today=TODAY)
    fired = []
    page.view_all_requested.connect(lambda: fired.append(True))
    page.view_all_button.click()
    assert fired == [True]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_ui_home.py -q`
Expected: `ModuleNotFoundError: No module named 'whisperfree.ui.home'`

- [ ] **Step 3: Implement `whisperfree/ui/home.py`**

```python
"""Home page: greeting, stats, and the most recent transcriptions."""

from __future__ import annotations

from datetime import date, datetime
from typing import List, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.history import TranscriptionEntry, average_wpm, day_streak
from whisperfree.ui.widgets import Card, HistoryRow, clear_layout, make_label, scroll_page


RECENT_LIMIT = 5


def greeting_for(hour: int) -> str:
    if 5 <= hour < 12:
        return "Good morning"
    if 12 <= hour < 17:
        return "Good afternoon"
    return "Good evening"


class StatCard(Card):
    """A caption over a large number."""

    def __init__(self, caption: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent, margins=(18, 16, 18, 16), spacing=4)
        self.body.addWidget(make_label(caption, "Caption"))
        self.value_label = make_label("", "StatValue")
        self.body.addWidget(self.value_label)

    def set_value(self, value: str) -> None:
        self.value_label.setText(value)


class HomePage(QtWidgets.QWidget):
    """Greeting, headline stats, a hotkey hint, and recent transcriptions."""

    view_all_requested = QtCore.pyqtSignal()

    def __init__(
        self,
        name: str,
        entries: Sequence[TranscriptionEntry],
        hotkey_label: str = "Ctrl+Win",
        today: Optional[date] = None,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._entries: List[TranscriptionEntry] = list(entries)
        self._today = today

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(20)

        greeting = greeting_for(datetime.now().hour)
        header = QtWidgets.QVBoxLayout()
        header.setSpacing(4)
        self.title_label = make_label(f"{greeting}, {name}" if name else greeting, "PageTitle")
        header.addWidget(self.title_label)
        header.addWidget(make_label("Here's your dictation at a glance.", "PageSubtitle"))
        layout.addLayout(header)

        stats = QtWidgets.QHBoxLayout()
        stats.setSpacing(12)
        self.words_card = StatCard("Total words")
        self.streak_card = StatCard("Day streak")
        self.wpm_card = StatCard("Avg. words / min")
        for card in (self.words_card, self.streak_card, self.wpm_card):
            stats.addWidget(card, 1)
        layout.addLayout(stats)

        banner = QtWidgets.QFrame()
        banner.setObjectName("HintBanner")
        banner_layout = QtWidgets.QHBoxLayout(banner)
        banner_layout.setContentsMargins(16, 12, 16, 12)
        banner_layout.addWidget(
            make_label(f"Hold {hotkey_label} to dictate in any app — release to paste.", "HintText", wrap=True)
        )
        layout.addWidget(banner)

        recent_header = QtWidgets.QHBoxLayout()
        recent_header.addWidget(make_label("Recent transcriptions", "SectionTitle"))
        recent_header.addStretch(1)
        self.view_all_button = QtWidgets.QPushButton("View all →")
        self.view_all_button.setObjectName("LinkButton")
        self.view_all_button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.view_all_button.clicked.connect(self.view_all_requested.emit)
        recent_header.addWidget(self.view_all_button)
        layout.addLayout(recent_header)

        self._recent_layout = QtWidgets.QVBoxLayout()
        self._recent_layout.setSpacing(8)
        layout.addLayout(self._recent_layout)

        self.empty_label = make_label(
            f"Your transcriptions will appear here. Hold {hotkey_label} and start talking.",
            "Muted",
            wrap=True,
        )
        layout.addWidget(self.empty_label)
        layout.addStretch(1)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(content))

        self._refresh()

    def add_entry(self, entry: TranscriptionEntry) -> None:
        self._entries.insert(0, entry)
        self._refresh()

    def recent_count(self) -> int:
        return self._recent_layout.count()

    def _refresh(self) -> None:
        today = self._today or date.today()
        total_words = sum(entry.words for entry in self._entries)
        self.words_card.set_value(f"{total_words:,}")
        streak = day_streak(self._entries, today)
        self.streak_card.set_value(f"{streak} day" if streak == 1 else f"{streak} days")
        wpm = average_wpm(self._entries)
        self.wpm_card.set_value("—" if wpm is None else f"{wpm:.0f}")

        clear_layout(self._recent_layout)
        for entry in self._entries[:RECENT_LIMIT]:
            self._recent_layout.addWidget(HistoryRow(entry))
        self.empty_label.setVisible(not self._entries)
        self.view_all_button.setVisible(bool(self._entries))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_ui_home.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whisperfree/ui/home.py tests/test_ui_home.py
git commit -m "Add Home page with stats and recent transcriptions"
```

---

### Task 7: History page

**Files:**
- Create: `whisperfree/ui/history.py`
- Test: `tests/test_ui_history.py`

**Interfaces:**
- Consumes: `TranscriptionEntry`; `HistoryRow`, `clear_layout`, `format_day`, `make_label` (Task 5).
- Produces: `BATCH_SIZE = 50`; `class HistoryPage(QWidget)` with `__init__(entries: Sequence[TranscriptionEntry], parent=None)`, `set_filter(text: str) -> None`, `add_entry(entry) -> None`, `rendered_count() -> int`, `matching_count() -> int`, attributes `search_input: QLineEdit`, `empty_label: QLabel`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_history.py`:

```python
from datetime import datetime, timedelta

from PyQt6 import QtWidgets

from whisperfree.history import TranscriptionEntry
from whisperfree.ui.history import BATCH_SIZE, HistoryPage


def make_entries(count):
    start = datetime(2026, 9, 24, 23, 0).astimezone()
    return [
        TranscriptionEntry(timestamp=start - timedelta(hours=i), text=f"note number {i}", words=3)
        for i in range(count)
    ]


def day_headers(page):
    return [label.text() for label in page.findChildren(QtWidgets.QLabel, "DayHeader")]


def test_history_page_renders_lazily(qapp):
    page = HistoryPage(make_entries(1000))
    assert page.matching_count() == 1000
    assert page.rendered_count() == BATCH_SIZE
    page._maybe_load_more(page._scroll.verticalScrollBar().maximum())
    assert page.rendered_count() == 2 * BATCH_SIZE


def test_groups_by_day(qapp):
    page = HistoryPage(make_entries(30))  # 30 hours back from 23:00 spans two days
    assert len(day_headers(page)) == 2


def test_search_filters_case_insensitively(qapp):
    entries = make_entries(5) + [
        TranscriptionEntry(timestamp=datetime(2026, 9, 1, 9).astimezone(), text="Call the DENTIST", words=3)
    ]
    page = HistoryPage(entries)
    page.search_input.setText("dentist")
    assert page.matching_count() == 1
    assert page.rendered_count() == 1
    page.search_input.setText("")
    assert page.matching_count() == 6


def test_empty_states(qapp):
    page = HistoryPage([])
    assert not page.empty_label.isHidden()
    assert "No transcriptions yet" in page.empty_label.text()
    page = HistoryPage(make_entries(3))
    assert page.empty_label.isHidden()
    page.set_filter("zebra")
    assert not page.empty_label.isHidden()
    assert "zebra" in page.empty_label.text()


def test_add_entry_prepends_and_respects_filter(qapp):
    page = HistoryPage(make_entries(3))
    page.search_input.setText("meeting")
    assert page.matching_count() == 0
    page.add_entry(TranscriptionEntry(timestamp=datetime.now().astimezone(), text="Team meeting notes", words=3))
    assert page.matching_count() == 1
    page.search_input.setText("")
    assert page.matching_count() == 4
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_ui_history.py -q`
Expected: `ModuleNotFoundError: No module named 'whisperfree.ui.history'`

- [ ] **Step 3: Implement `whisperfree/ui/history.py`**

```python
"""History page: every transcription, searchable and grouped by day."""

from __future__ import annotations

from typing import List, Optional, Sequence

from PyQt6 import QtCore, QtWidgets

from whisperfree.history import TranscriptionEntry
from whisperfree.ui.widgets import HistoryRow, clear_layout, format_day, make_label


BATCH_SIZE = 50
LOAD_MORE_THRESHOLD_PX = 200


class HistoryPage(QtWidgets.QWidget):
    """Full transcription history, rendered in batches as you scroll."""

    def __init__(self, entries: Sequence[TranscriptionEntry], parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._entries: List[TranscriptionEntry] = list(entries)
        self._filtered: List[TranscriptionEntry] = []
        self._rendered = 0
        self._last_day: Optional[str] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 0)
        layout.setSpacing(16)
        layout.addWidget(make_label("History", "PageTitle"))

        self.search_input = QtWidgets.QLineEdit()
        self.search_input.setPlaceholderText("Search transcriptions")
        self.search_input.setClearButtonEnabled(True)
        self.search_input.textChanged.connect(self.set_filter)
        layout.addWidget(self.search_input)

        self.empty_label = make_label("", "Muted", wrap=True)
        layout.addWidget(self.empty_label)

        container = QtWidgets.QWidget()
        self._list_layout = QtWidgets.QVBoxLayout(container)
        self._list_layout.setContentsMargins(0, 0, 0, 24)
        self._list_layout.setSpacing(8)

        self._scroll = QtWidgets.QScrollArea()
        self._scroll.setWidgetResizable(True)
        self._scroll.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self._scroll.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._scroll.setWidget(container)
        self._scroll.verticalScrollBar().valueChanged.connect(self._maybe_load_more)
        layout.addWidget(self._scroll, 1)

        self.set_filter("")

    # ------------------------------------------------------------------ public API

    def set_filter(self, text: str) -> None:
        needle = text.strip().casefold()
        if needle:
            self._filtered = [entry for entry in self._entries if needle in entry.text.casefold()]
        else:
            self._filtered = list(self._entries)
        clear_layout(self._list_layout)
        self._list_layout.addStretch(1)
        self._rendered = 0
        self._last_day = None
        self._render_more()

        if not self._entries:
            self.empty_label.setText("No transcriptions yet. Hold Ctrl+Win to dictate.")
        elif not self._filtered:
            self.empty_label.setText(f"No transcriptions match “{text.strip()}”.")
        self.empty_label.setVisible(not self._filtered)

    def add_entry(self, entry: TranscriptionEntry) -> None:
        self._entries.insert(0, entry)
        self.set_filter(self.search_input.text())

    def rendered_count(self) -> int:
        return self._rendered

    def matching_count(self) -> int:
        return len(self._filtered)

    # ------------------------------------------------------------------ internals

    def _render_more(self) -> None:
        end = min(len(self._filtered), self._rendered + BATCH_SIZE)
        for entry in self._filtered[self._rendered:end]:
            day = format_day(entry.timestamp)
            if day != self._last_day:
                self._append(make_label(day, "DayHeader"))
                self._last_day = day
            self._append(HistoryRow(entry))
        self._rendered = end

    def _append(self, widget: QtWidgets.QWidget) -> None:
        # Keep the trailing stretch last.
        self._list_layout.insertWidget(self._list_layout.count() - 1, widget)

    def _maybe_load_more(self, value: int) -> None:
        bar = self._scroll.verticalScrollBar()
        if self._rendered < len(self._filtered) and value >= bar.maximum() - LOAD_MORE_THRESHOLD_PX:
            self._render_more()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_ui_history.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whisperfree/ui/history.py tests/test_ui_history.py
git commit -m "Add searchable, lazily rendered History page"
```

---

### Task 8: Dictionary page

**Files:**
- Create: `whisperfree/ui/dictionary.py`
- Test: `tests/test_ui_dictionary.py`

**Interfaces:**
- Consumes: `Dictionary`, `Replacement` (Task 1); `Card`, `FlowLayout`, `clear_layout`, `divider`, `make_label`, `scroll_page` (Task 5).
- Produces: `class DictionaryPage(QWidget)` with `__init__(dictionary: Dictionary, parent=None)`, attributes `tabs`, `term_input`, `add_term_button`, `match_input`, `replace_input`, `save_rule_button`, `cancel_edit_button`, `status_label`; methods `term_chips() -> list[QFrame]` (each chip has `.remove_button` and property `"term"`), `rule_rows() -> list[QWidget]` (each row has `.edit_button`, `.delete_button`).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_dictionary.py`:

```python
from whisperfree.dictionary import Dictionary, Replacement
from whisperfree.ui.dictionary import DictionaryPage


def make_page(tmp_path):
    dictionary = Dictionary(tmp_path / "dictionary.json")
    return dictionary, DictionaryPage(dictionary)


def test_add_term_via_input(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.term_input.setText("Kanishka")
    page.add_term_button.click()
    assert dictionary.terms() == ["Kanishka"]
    assert page.term_input.text() == ""
    assert [chip.property("term") for chip in page.term_chips()] == ["Kanishka"]


def test_enter_key_adds_term(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.term_input.setText("PyQt6")
    page.term_input.returnPressed.emit()
    assert dictionary.terms() == ["PyQt6"]


def test_duplicate_term_shows_status(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_term("5Point")
    page.term_input.setText("5point")
    page.add_term_button.click()
    assert not page.status_label.isHidden()
    assert "already" in page.status_label.text()
    assert page.term_input.text() == "5point"  # kept so the user can fix it


def test_remove_term_chip(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_term("A")
    dictionary.add_term("B")
    page = DictionaryPage(dictionary)
    page.term_chips()[0].remove_button.click()
    assert dictionary.terms() == ["B"]
    assert len(page.term_chips()) == 1


def test_add_edit_delete_rule(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.match_input.setText("five point")
    page.replace_input.setText("5Point")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("five point", "5Point")]
    assert len(page.rule_rows()) == 1

    page.rule_rows()[0].edit_button.click()
    assert page.match_input.text() == "five point"
    assert page.save_rule_button.text() == "Save"
    assert not page.cancel_edit_button.isHidden()
    page.replace_input.setText("5 Point")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("five point", "5 Point")]
    assert page.save_rule_button.text() == "Add"
    assert page.match_input.text() == ""

    page.rule_rows()[0].delete_button.click()
    assert dictionary.replacements() == []
    assert page.rule_rows() == []


def test_cancel_edit_restores_add_mode(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    dictionary.add_replacement("a", "b")
    page = DictionaryPage(dictionary)
    page.rule_rows()[0].edit_button.click()
    page.cancel_edit_button.click()
    assert page.save_rule_button.text() == "Add"
    assert page.match_input.text() == ""
    assert page.cancel_edit_button.isHidden()


def test_rule_validation_messages(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.save_rule_button.click()
    assert "Enter the words" in page.status_label.text()
    dictionary.add_replacement("um", "")
    page.match_input.setText("UM")
    page.save_rule_button.click()
    assert "already a rule" in page.status_label.text()


def test_blank_replacement_allowed(qapp, tmp_path):
    dictionary, page = make_page(tmp_path)
    page.match_input.setText("um")
    page.save_rule_button.click()
    assert dictionary.replacements() == [Replacement("um", "")]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_ui_dictionary.py -q`
Expected: `ModuleNotFoundError: No module named 'whisperfree.ui.dictionary'`

- [ ] **Step 3: Implement `whisperfree/ui/dictionary.py`**

```python
"""Dictionary page: custom terms and replacement rules."""

from __future__ import annotations

from typing import List, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.dictionary import Dictionary, Replacement
from whisperfree.ui.widgets import Card, FlowLayout, clear_layout, divider, make_label, scroll_page


def _pointer(button: QtWidgets.QPushButton) -> QtWidgets.QPushButton:
    button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
    return button


def _button(text: str, object_name: str) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName(object_name)
    return _pointer(button)


class DictionaryPage(QtWidgets.QWidget):
    """Edit the shared Dictionary; every change is saved immediately."""

    def __init__(self, dictionary: Dictionary, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self._dictionary = dictionary
        self._editing_index: Optional[int] = None

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 24)
        layout.setSpacing(12)
        header = QtWidgets.QVBoxLayout()
        header.setSpacing(4)
        header.addWidget(make_label("Dictionary", "PageTitle"))
        header.addWidget(
            make_label("Teach WhisperFree the words you use, and fix the ones it gets wrong.", "PageSubtitle")
        )
        layout.addLayout(header)

        self.tabs = QtWidgets.QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.addTab(self._build_terms_tab(), "Terms")
        self.tabs.addTab(self._build_replacements_tab(), "Replacements")
        layout.addWidget(self.tabs, 1)

        self.status_label = make_label("", "StatusError", wrap=True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        self._render_terms()
        self._render_rules()

    # ------------------------------------------------------------------ terms tab

    def _build_terms_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            make_label(
                "Names, acronyms, and jargon. WhisperFree passes these to the transcriber as spelling hints.",
                "Caption",
                wrap=True,
            )
        )

        row = QtWidgets.QHBoxLayout()
        row.setSpacing(8)
        self.term_input = QtWidgets.QLineEdit()
        self.term_input.setPlaceholderText("Add a word or phrase, e.g. Kanishka")
        self.term_input.returnPressed.connect(self._handle_add_term)
        self.add_term_button = _button("Add", "PrimaryButton")
        self.add_term_button.clicked.connect(self._handle_add_term)
        row.addWidget(self.term_input, 1)
        row.addWidget(self.add_term_button)
        layout.addLayout(row)

        card = Card()
        self._chips_container = QtWidgets.QWidget()
        self._chips_layout = FlowLayout(self._chips_container, spacing=8)
        card.body.addWidget(self._chips_container)
        self._terms_empty = make_label("No terms yet. Add the names and jargon you say often.", "Muted", wrap=True)
        card.body.addWidget(self._terms_empty)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(card)
        content_layout.addStretch(1)
        layout.addWidget(scroll_page(content), 1)
        return page

    def _render_terms(self) -> None:
        clear_layout(self._chips_layout)
        terms = self._dictionary.terms()
        for term in terms:
            self._chips_layout.addWidget(self._make_chip(term))
        self._chips_container.setVisible(bool(terms))
        self._terms_empty.setVisible(not terms)

    def _make_chip(self, term: str) -> QtWidgets.QFrame:
        chip = QtWidgets.QFrame()
        chip.setObjectName("Chip")
        chip.setProperty("term", term)
        layout = QtWidgets.QHBoxLayout(chip)
        layout.setContentsMargins(12, 4, 6, 4)
        layout.setSpacing(4)
        layout.addWidget(make_label(term, "ChipText"))
        remove = _button("×", "ChipRemove")
        remove.setFixedSize(18, 18)
        remove.setToolTip(f"Remove {term}")
        remove.clicked.connect(lambda _checked=False, t=term: self._remove_term(t))
        layout.addWidget(remove)
        chip.remove_button = remove  # type: ignore[attr-defined]
        return chip

    def term_chips(self) -> List[QtWidgets.QFrame]:
        return [self._chips_layout.itemAt(i).widget() for i in range(self._chips_layout.count())]

    def _handle_add_term(self) -> None:
        text = self.term_input.text().strip()
        if not text:
            return
        if not self._dictionary.add_term(text):
            self._show_status(f"“{text}” is already in your dictionary.")
            return
        self.term_input.clear()
        self._render_terms()
        self._show_save_status()

    def _remove_term(self, term: str) -> None:
        self._dictionary.remove_term(term)
        self._render_terms()
        self._show_save_status()

    # ------------------------------------------------------------------ replacements tab

    def _build_replacements_tab(self) -> QtWidgets.QWidget:
        page = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(page)
        layout.setContentsMargins(0, 16, 0, 0)
        layout.setSpacing(12)
        layout.addWidget(
            make_label(
                "Swap what Whisper hears for what you want pasted. Matches whole words and ignores case.",
                "Caption",
                wrap=True,
            )
        )

        form = QtWidgets.QHBoxLayout()
        form.setSpacing(8)
        self.match_input = QtWidgets.QLineEdit()
        self.match_input.setPlaceholderText("When I say…")
        self.replace_input = QtWidgets.QLineEdit()
        self.replace_input.setPlaceholderText("Replace with… (leave empty to remove)")
        for field in (self.match_input, self.replace_input):
            field.returnPressed.connect(self._handle_save_rule)
        self.save_rule_button = _button("Add", "PrimaryButton")
        self.save_rule_button.clicked.connect(self._handle_save_rule)
        self.cancel_edit_button = _button("Cancel", "SecondaryButton")
        self.cancel_edit_button.clicked.connect(self._exit_edit_mode)
        self.cancel_edit_button.hide()
        form.addWidget(self.match_input, 1)
        form.addWidget(make_label("→", "Caption"))
        form.addWidget(self.replace_input, 1)
        form.addWidget(self.save_rule_button)
        form.addWidget(self.cancel_edit_button)
        layout.addLayout(form)

        card = Card(margins=(4, 4, 4, 4), spacing=0)
        self._rules_layout = QtWidgets.QVBoxLayout()
        self._rules_layout.setSpacing(0)
        card.body.addLayout(self._rules_layout)
        self._rules_empty = make_label("No replacement rules yet.", "Muted")
        self._rules_empty.setContentsMargins(16, 12, 16, 12)
        card.body.addWidget(self._rules_empty)

        content = QtWidgets.QWidget()
        content_layout = QtWidgets.QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(card)
        content_layout.addStretch(1)
        layout.addWidget(scroll_page(content), 1)
        return page

    def _render_rules(self) -> None:
        clear_layout(self._rules_layout)
        rules = self._dictionary.replacements()
        for index, rule in enumerate(rules):
            if index:
                self._rules_layout.addWidget(divider())
            self._rules_layout.addWidget(self._make_rule_row(index, rule))
        self._rules_empty.setVisible(not rules)

    def _make_rule_row(self, index: int, rule: Replacement) -> QtWidgets.QWidget:
        row = QtWidgets.QWidget()
        row.setObjectName("RuleRow")
        layout = QtWidgets.QHBoxLayout(row)
        layout.setContentsMargins(12, 8, 8, 8)
        layout.setSpacing(10)
        layout.addWidget(make_label(rule.match, "RuleMatch"))
        layout.addWidget(make_label("→", "Muted"))
        if rule.replace:
            layout.addWidget(make_label(rule.replace, "Body"), 1)
        else:
            layout.addWidget(make_label("(removed)", "Muted"), 1)
        edit = _button("Edit", "GhostButton")
        edit.clicked.connect(lambda _checked=False, i=index: self._start_edit(i))
        delete = _button("Delete", "DangerGhostButton")
        delete.clicked.connect(lambda _checked=False, i=index: self._delete_rule(i))
        layout.addWidget(edit)
        layout.addWidget(delete)
        row.edit_button = edit  # type: ignore[attr-defined]
        row.delete_button = delete  # type: ignore[attr-defined]
        return row

    def rule_rows(self) -> List[QtWidgets.QWidget]:
        rows = []
        for i in range(self._rules_layout.count()):
            widget = self._rules_layout.itemAt(i).widget()
            if widget is not None and widget.objectName() == "RuleRow":
                rows.append(widget)
        return rows

    def _handle_save_rule(self) -> None:
        match = self.match_input.text().strip()
        replace = self.replace_input.text()
        if not match:
            self._show_status("Enter the words to listen for.")
            return
        if self._editing_index is None:
            saved = self._dictionary.add_replacement(match, replace)
        else:
            saved = self._dictionary.update_replacement(self._editing_index, match, replace)
        if not saved:
            self._show_status(f"There's already a rule for “{match}”.")
            return
        self._exit_edit_mode()
        self._render_rules()
        self._show_save_status()

    def _start_edit(self, index: int) -> None:
        rules = self._dictionary.replacements()
        if not 0 <= index < len(rules):
            return
        self._editing_index = index
        self.match_input.setText(rules[index].match)
        self.replace_input.setText(rules[index].replace)
        self.save_rule_button.setText("Save")
        self.cancel_edit_button.show()
        self.match_input.setFocus()

    def _exit_edit_mode(self) -> None:
        self._editing_index = None
        self.match_input.clear()
        self.replace_input.clear()
        self.save_rule_button.setText("Add")
        self.cancel_edit_button.hide()
        self.status_label.hide()

    def _delete_rule(self, index: int) -> None:
        self._exit_edit_mode()
        self._dictionary.remove_replacement(index)
        self._render_rules()
        self._show_save_status()

    # ------------------------------------------------------------------ status

    def _show_status(self, message: str) -> None:
        self.status_label.setText(message)
        self.status_label.show()

    def _show_save_status(self) -> None:
        error = self._dictionary.last_save_error
        if error:
            self._show_status(f"Couldn't save the dictionary: {error}")
        else:
            self.status_label.hide()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_ui_dictionary.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whisperfree/ui/dictionary.py tests/test_ui_dictionary.py
git commit -m "Add Dictionary page with terms and replacement rules"
```

---

### Task 9: Settings page

**Files:**
- Create: `whisperfree/ui/settings.py`
- Test: `tests/test_ui_settings.py`

**Interfaces:**
- Consumes: `AppConfig` (fields `mic_device_name, language, append_newline, overlay_enabled, input_gain_db, api_key_env`, methods `save()`, `resolve_api_key()`); `whisperfree.startup` module (Task 2) — call through the module (`startup.is_supported()` etc.) so tests can monkeypatch; `list_microphones` from `whisperfree.audio`; `models.LANGUAGE_CHOICES`; widgets from Task 5.
- Produces: `class SettingsPage(QWidget)` with `__init__(config: AppConfig, on_change: Callable[[AppConfig], None], parent=None)`; attributes `startup_toggle, overlay_toggle, newline_toggle, mic_combo, refresh_mics_button, gain_slider, gain_value_label, language_combo, api_key_edit, show_key_button, test_api_button, save_api_button, api_status_label`; module-level `_ENV_FILE_PATH: Path`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_settings.py`:

```python
import os

import pytest

import whisperfree.ui.settings as settings_module
from whisperfree import startup
from whisperfree.config import AppConfig
from whisperfree.ui.settings import SettingsPage


@pytest.fixture
def env(monkeypatch, tmp_path):
    state = {"enabled": False, "fail": False, "saves": 0, "changes": 0}

    def set_enabled(enabled, value_name=startup.VALUE_NAME):
        if state["fail"]:
            raise OSError("access denied")
        state["enabled"] = enabled

    monkeypatch.setattr(startup, "is_supported", lambda: True)
    monkeypatch.setattr(startup, "is_enabled", lambda value_name=startup.VALUE_NAME: state["enabled"])
    monkeypatch.setattr(startup, "set_enabled", set_enabled)
    monkeypatch.setattr(settings_module, "list_microphones", lambda: ["Mic A", "Mic B"])
    monkeypatch.setattr(settings_module, "_ENV_FILE_PATH", tmp_path / ".env")
    monkeypatch.setattr(settings_module.QtWidgets.QMessageBox, "warning", lambda *a, **k: None)
    monkeypatch.setenv("WF_SETTINGS_TEST_KEY", "sk-original")

    config = AppConfig(api_key_env="WF_SETTINGS_TEST_KEY", mic_device_name="Mic B", language="en")

    def fake_save(*args, **kwargs):
        state["saves"] += 1

    monkeypatch.setattr(config, "save", fake_save)

    def on_change(cfg):
        state["changes"] += 1

    page = SettingsPage(config, on_change)
    return config, page, state


def test_initial_values_reflect_config(qapp, env):
    config, page, state = env
    assert page.mic_combo.currentText() == "Mic B"
    assert page.language_combo.currentData() == "en"
    assert page.overlay_toggle.isChecked() == config.overlay_enabled
    assert page.newline_toggle.isChecked() == config.append_newline
    assert page.api_key_edit.text() == "sk-original"
    assert not page.startup_toggle.isChecked()
    assert state["saves"] == 0 and state["changes"] == 0  # loading does not save


def test_toggles_apply_immediately(qapp, env):
    config, page, state = env
    page.overlay_toggle.click()
    assert config.overlay_enabled is False
    page.newline_toggle.click()
    assert config.append_newline is False
    assert state["saves"] == 2 and state["changes"] == 2


def test_mic_and_language_apply_immediately(qapp, env):
    config, page, state = env
    page.mic_combo.setCurrentIndex(page.mic_combo.findText("Mic A"))
    assert config.mic_device_name == "Mic A"
    page.mic_combo.setCurrentIndex(0)
    assert config.mic_device_name is None
    page.language_combo.setCurrentIndex(page.language_combo.findData("auto"))
    assert config.language == "auto"


def test_missing_configured_mic_falls_back_without_saving(qapp, env, monkeypatch):
    config, page, state = env
    monkeypatch.setattr(settings_module, "list_microphones", lambda: ["Mic A"])
    page.refresh_mics_button.click()
    assert page.mic_combo.currentText() == "System Default"
    assert config.mic_device_name == "Mic B"
    assert state["saves"] == 0


def test_gain_is_debounced(qapp, env):
    config, page, state = env
    page.gain_slider.setValue(60)
    assert page.gain_value_label.text() == "+6.0 dB"
    assert state["saves"] == 0
    page._commit_gain()
    assert config.input_gain_db == 6.0
    assert state["saves"] == 1


def test_startup_toggle_success(qapp, env):
    config, page, state = env
    page.startup_toggle.click()
    assert state["enabled"] is True
    assert page.startup_toggle.isChecked()


def test_startup_toggle_failure_reverts(qapp, env):
    config, page, state = env
    state["fail"] = True
    page.startup_toggle.click()
    assert state["enabled"] is False
    assert not page.startup_toggle.isChecked()


def test_startup_toggle_hidden_when_unsupported(qapp, env, monkeypatch):
    config, _page, _state = env
    monkeypatch.setattr(startup, "is_supported", lambda: False)
    page = SettingsPage(config, lambda cfg: None)
    assert page.startup_toggle.isHidden()


def test_save_api_key_requires_explicit_action(qapp, env, tmp_path):
    config, page, state = env
    page.api_key_edit.setText("sk-new")
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-original"
    page.save_api_button.click()
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-new"
    assert "WF_SETTINGS_TEST_KEY=sk-new" in (tmp_path / ".env").read_text(encoding="utf-8")
    assert page.api_status_label.text() == "API key saved."


def test_save_blank_api_key_is_rejected(qapp, env):
    config, page, state = env
    page.api_key_edit.setText("   ")
    page.save_api_button.click()
    assert os.environ["WF_SETTINGS_TEST_KEY"] == "sk-original"
    assert page.api_status_label.text() == "Enter an API key first."
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_ui_settings.py -q`
Expected: `ModuleNotFoundError: No module named 'whisperfree.ui.settings'`

- [ ] **Step 3: Implement `whisperfree/ui/settings.py`**

```python
"""Settings page: general, audio, transcription, and OpenAI sections."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Callable, Optional

from openai import OpenAIError
from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree import models, startup
from whisperfree.audio import list_microphones
from whisperfree.config import AppConfig
from whisperfree.ui.widgets import (
    Card,
    SettingRow,
    ToggleSwitch,
    divider,
    make_label,
    scroll_page,
    set_object_name,
)
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

_ENV_FILE_PATH = Path.home() / ".whisperfree" / ".env"


class _ApiTestWorker(QtCore.QObject):
    finished = QtCore.pyqtSignal(bool, object)

    def __init__(self, api_key: str) -> None:
        super().__init__()
        self._api_key = api_key

    @QtCore.pyqtSlot()
    def run(self) -> None:
        try:
            from openai import OpenAI

            client = OpenAI(api_key=self._api_key)
            client.models.list()
        except OpenAIError as exc:
            self.finished.emit(False, exc)
        except Exception as exc:  # pragma: no cover - defensive
            self.finished.emit(False, exc)
        else:
            self.finished.emit(True, None)


def _update_env_file(key: str, value: str) -> None:
    lines: list[str] = []
    updated = False
    if _ENV_FILE_PATH.exists():
        for line in _ENV_FILE_PATH.read_text(encoding="utf-8").splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                lines.append(line)
                continue
            current_key, sep, _ = line.partition("=")
            if sep and current_key.strip() == key:
                lines.append(f"{key}={value}")
                updated = True
            else:
                lines.append(line)
    if not updated:
        lines.append(f"{key}={value}")
    _ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ENV_FILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _row(*widgets: QtWidgets.QWidget, stretch_first: bool = False) -> QtWidgets.QWidget:
    container = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(8)
    for index, widget in enumerate(widgets):
        layout.addWidget(widget, 1 if (stretch_first and index == 0) else 0)
    return container


def _button(text: str, object_name: str) -> QtWidgets.QPushButton:
    button = QtWidgets.QPushButton(text)
    button.setObjectName(object_name)
    button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
    return button


class SettingsPage(QtWidgets.QWidget):
    """Settings apply as soon as they change; the API key needs an explicit Save."""

    def __init__(
        self,
        config: AppConfig,
        on_change: Callable[[AppConfig], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._config = config
        self._on_change = on_change
        self._api_test_thread: Optional[QtCore.QThread] = None
        self._api_test_worker: Optional[_ApiTestWorker] = None
        self._pending_api_key: Optional[str] = None
        self._mic_warning_shown = False

        content = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(content)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(16)
        layout.addWidget(make_label("Settings", "PageTitle"))

        # General -------------------------------------------------------------
        general = Card()
        general.body.addWidget(make_label("General", "SectionTitle"))
        self.startup_toggle = ToggleSwitch()
        if startup.is_supported():
            general.body.addWidget(
                SettingRow(
                    "Launch on startup",
                    "Start WhisperFree automatically when you sign in to Windows.",
                    self.startup_toggle,
                )
            )
            general.body.addWidget(divider())
        else:
            self.startup_toggle.hide()
        self.overlay_toggle = ToggleSwitch()
        general.body.addWidget(
            SettingRow(
                "Show recording overlay",
                "Display the indicator at the bottom of the screen while dictating.",
                self.overlay_toggle,
            )
        )
        general.body.addWidget(divider())
        self.newline_toggle = ToggleSwitch()
        general.body.addWidget(
            SettingRow("Press Enter after pasting", "Append a newline after each transcription.", self.newline_toggle)
        )
        layout.addWidget(general)

        # Audio ---------------------------------------------------------------
        audio = Card()
        audio.body.addWidget(make_label("Audio", "SectionTitle"))
        self.mic_combo = QtWidgets.QComboBox()
        self.mic_combo.setMinimumWidth(240)
        self.refresh_mics_button = _button("Refresh", "SecondaryButton")
        audio.body.addWidget(
            SettingRow(
                "Microphone",
                "Choose which input device to record from.",
                _row(self.mic_combo, self.refresh_mics_button),
            )
        )
        audio.body.addWidget(divider())
        self.gain_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gain_slider.setRange(-120, 240)
        self.gain_slider.setFixedWidth(220)
        self.gain_value_label = make_label("", "Caption")
        self.gain_value_label.setFixedWidth(56)
        audio.body.addWidget(
            SettingRow(
                "Input gain",
                "Boost or reduce your microphone volume.",
                _row(self.gain_slider, self.gain_value_label),
            )
        )
        layout.addWidget(audio)

        # Transcription -------------------------------------------------------
        transcription = Card()
        transcription.body.addWidget(make_label("Transcription", "SectionTitle"))
        self.language_combo = QtWidgets.QComboBox()
        self.language_combo.setMinimumWidth(240)
        for code, label_text in models.LANGUAGE_CHOICES:
            self.language_combo.addItem(label_text, code)
        transcription.body.addWidget(
            SettingRow(
                "Language",
                "Auto-detect, or pick the language you speak for better accuracy.",
                self.language_combo,
            )
        )
        layout.addWidget(transcription)

        # OpenAI --------------------------------------------------------------
        openai_card = Card()
        openai_card.body.addWidget(make_label("OpenAI", "SectionTitle"))
        openai_card.body.addWidget(
            make_label("Your key is stored in ~/.whisperfree/.env on this computer.", "Caption", wrap=True)
        )
        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.api_key_edit.setPlaceholderText("sk-...")
        self.show_key_button = _button("Show", "GhostButton")
        self.test_api_button = _button("Test", "SecondaryButton")
        self.save_api_button = _button("Save key", "PrimaryButton")
        openai_card.body.addWidget(
            _row(self.api_key_edit, self.show_key_button, self.test_api_button, self.save_api_button, stretch_first=True)
        )
        self.api_status_label = make_label("", "StatusOk", wrap=True)
        self.api_status_label.hide()
        openai_card.body.addWidget(self.api_status_label)
        layout.addWidget(openai_card)
        layout.addStretch(1)

        outer = QtWidgets.QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll_page(content))

        self._gain_timer = QtCore.QTimer(self)
        self._gain_timer.setSingleShot(True)
        self._gain_timer.setInterval(300)
        self._gain_timer.timeout.connect(self._commit_gain)

        self._apply_config()

        self.startup_toggle.toggled.connect(self._handle_startup_toggled)
        self.overlay_toggle.toggled.connect(lambda checked: self._update(overlay_enabled=checked))
        self.newline_toggle.toggled.connect(lambda checked: self._update(append_newline=checked))
        self.mic_combo.currentIndexChanged.connect(self._handle_mic_changed)
        self.refresh_mics_button.clicked.connect(lambda: self._populate_microphones(self.mic_combo.currentData()))
        self.gain_slider.valueChanged.connect(self._handle_gain_moved)
        self.language_combo.currentIndexChanged.connect(
            lambda index: self._update(language=self.language_combo.itemData(index))
        )
        self.show_key_button.clicked.connect(self._toggle_key_visibility)
        self.test_api_button.clicked.connect(self._handle_test_api)
        self.save_api_button.clicked.connect(self._handle_save_api)

    # ------------------------------------------------------------------ loading

    def _apply_config(self) -> None:
        if startup.is_supported():
            self.startup_toggle.setChecked(startup.is_enabled())
        self.overlay_toggle.setChecked(self._config.overlay_enabled)
        self.newline_toggle.setChecked(self._config.append_newline)
        self._populate_microphones(self._config.mic_device_name)
        language_index = self.language_combo.findData(self._config.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)
        self.gain_slider.setValue(int(round(self._config.input_gain_db * 10)))
        self._update_gain_label(self.gain_slider.value())
        self.api_key_edit.setText(self._config.resolve_api_key() or "")

    def _populate_microphones(self, select: Optional[str]) -> None:
        self.mic_combo.blockSignals(True)
        try:
            self.mic_combo.clear()
            try:
                devices = list_microphones()
            except Exception as exc:  # pragma: no cover - defensive
                logger.warning("Failed to refresh microphone list: {}", exc)
                if not self._mic_warning_shown:
                    QtWidgets.QMessageBox.warning(
                        self,
                        "Microphones",
                        "Unable to refresh the microphone list. The system default input will be used.",
                    )
                    self._mic_warning_shown = True
                devices = []
            else:
                self._mic_warning_shown = False
            self.mic_combo.addItem("System Default", None)
            for device in devices:
                self.mic_combo.addItem(device, device)
            index = self.mic_combo.findData(select) if select else 0
            self.mic_combo.setCurrentIndex(max(index, 0))
        finally:
            self.mic_combo.blockSignals(False)

    # ------------------------------------------------------------------ changes

    def _update(self, **changes: Any) -> None:
        for name, value in changes.items():
            setattr(self._config, name, value)
        try:
            self._config.save()
        except OSError as exc:
            logger.warning("Failed to save settings: {}", exc)
        self._on_change(self._config)

    def _handle_mic_changed(self, index: int) -> None:
        self._update(mic_device_name=self.mic_combo.itemData(index))

    def _handle_gain_moved(self, value: int) -> None:
        self._update_gain_label(value)
        self._gain_timer.start()

    def _update_gain_label(self, value: int) -> None:
        self.gain_value_label.setText(f"{value / 10.0:+.1f} dB")

    def _commit_gain(self) -> None:
        self._update(input_gain_db=self.gain_slider.value() / 10.0)

    def _handle_startup_toggled(self, checked: bool) -> None:
        try:
            startup.set_enabled(checked)
        except OSError as exc:
            logger.warning("Failed to update launch on startup: {}", exc)
            QtWidgets.QMessageBox.warning(
                self, "Launch on startup", f"Couldn't update the Windows startup setting:\n{exc}"
            )
            self.startup_toggle.blockSignals(True)
            self.startup_toggle.setChecked(not checked)
            self.startup_toggle.blockSignals(False)
            self.startup_toggle.update()

    # ------------------------------------------------------------------ API key

    def _show_api_status(self, message: str, error: bool = False) -> None:
        set_object_name(self.api_status_label, "StatusError" if error else "StatusOk")
        self.api_status_label.setText(message)
        self.api_status_label.show()

    def _toggle_key_visibility(self) -> None:
        hidden = self.api_key_edit.echoMode() == QtWidgets.QLineEdit.EchoMode.Password
        self.api_key_edit.setEchoMode(
            QtWidgets.QLineEdit.EchoMode.Normal if hidden else QtWidgets.QLineEdit.EchoMode.Password
        )
        self.show_key_button.setText("Hide" if hidden else "Show")

    def _handle_save_api(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            self._show_api_status("Enter an API key first.", error=True)
            return
        self._set_api_key(api_key)
        self._show_api_status("API key saved.")

    def _set_api_key(self, api_key: str) -> None:
        os.environ[self._config.api_key_env] = api_key
        try:
            _update_env_file(self._config.api_key_env, api_key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning("Failed to update .env file with new API key: {}", exc)

    def _handle_test_api(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            self._show_api_status("Enter an API key first.", error=True)
            return
        if self._api_test_thread and self._api_test_thread.isRunning():
            return

        self._pending_api_key = api_key
        self.test_api_button.setEnabled(False)
        self.test_api_button.setText("Testing…")

        worker = _ApiTestWorker(api_key)
        thread = QtCore.QThread(self)
        self._api_test_worker = worker
        self._api_test_thread = thread
        worker.moveToThread(thread)
        thread.started.connect(worker.run)
        worker.finished.connect(self._on_api_test_finished)
        worker.finished.connect(thread.quit)
        worker.finished.connect(worker.deleteLater)
        thread.finished.connect(thread.deleteLater)
        thread.start()

    @QtCore.pyqtSlot(bool, object)
    def _on_api_test_finished(self, success: bool, error: object) -> None:
        self.test_api_button.setEnabled(True)
        self.test_api_button.setText("Test")
        if success:
            if self._pending_api_key:
                self._set_api_key(self._pending_api_key)
            self._show_api_status("API key works and has been saved.")
        else:
            message = str(error) if error else "Unknown error."
            logger.error("OpenAI test failed: {}", message)
            self._show_api_status(f"API check failed: {message}", error=True)
        self._pending_api_key = None
        self._api_test_worker = None
        self._api_test_thread = None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `py -3.11 -m pytest tests/test_ui_settings.py -q`
Expected: all pass.

- [ ] **Step 5: Commit**

```bash
git add whisperfree/ui/settings.py tests/test_ui_settings.py
git commit -m "Add sectioned Settings page with launch-on-startup toggle"
```

---

### Task 10: Control panel window, sidebar, and wiring

**Files:**
- Rewrite: `whisperfree/ui/window.py` (replace the legacy content entirely)
- Modify: `whisperfree/app.py` (`open_settings`)
- Test: `tests/test_ui_window.py`

**Interfaces:**
- Consumes: `HomePage` (Task 6), `HistoryPage` (Task 7), `DictionaryPage` (Task 8), `SettingsPage` (Task 9), `theme.STYLESHEET`, `theme.ui_font()`, `asset_path`, `friendly_username`, `make_label` (Task 5), `Dictionary` (Task 1), `WhisperFreeController._dictionary` (Task 4).
- Produces: `ControlPanelWindow(config: AppConfig, on_save: Callable[[AppConfig], None], history: TranscriptionHistory, dictionary: Dictionary)` with `navigate_to(key: str)`, `current_page_key() -> str`, `handle_history_entry(entry)`, attributes `home_page, history_page, dictionary_page, settings_page`; `nav_icon(kind: str) -> QIcon`; `TrayController` (unchanged behaviour).

- [ ] **Step 1: Write the failing tests**

Create `tests/test_ui_window.py`:

```python
from datetime import datetime

import pytest

import whisperfree.ui.settings as settings_module
from whisperfree import startup
from whisperfree.config import AppConfig
from whisperfree.dictionary import Dictionary
from whisperfree.history import TranscriptionEntry, TranscriptionHistory
from whisperfree.ui import ControlPanelWindow
from whisperfree.ui.window import NAV_ITEMS, nav_icon


@pytest.fixture
def window(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(startup, "is_supported", lambda: True)
    monkeypatch.setattr(startup, "is_enabled", lambda value_name=startup.VALUE_NAME: False)
    monkeypatch.setattr(settings_module, "list_microphones", lambda: [])
    config = AppConfig()
    monkeypatch.setattr(config, "save", lambda *a, **k: None)
    history = TranscriptionHistory(tmp_path / "history.jsonl")
    history.add_entry("First note")
    return ControlPanelWindow(
        config=config,
        on_save=lambda cfg: None,
        history=history,
        dictionary=Dictionary(tmp_path / "dictionary.json"),
    )


def test_starts_on_home(window):
    assert window.current_page_key() == "home"
    assert window.home_page.recent_count() == 1


def test_navigation_switches_pages(window):
    for key, _label in NAV_ITEMS:
        window.navigate_to(key)
        assert window.current_page_key() == key


def test_view_all_opens_history(window):
    window.home_page.view_all_button.click()
    assert window.current_page_key() == "history"


def test_new_entries_reach_home_and_history(window):
    entry = TranscriptionEntry(timestamp=datetime.now().astimezone(), text="Second note", words=2)
    window.handle_history_entry(entry)
    assert window.home_page.recent_count() == 2
    assert window.history_page.matching_count() == 2


def test_nav_icons_render(qapp):
    for key, _label in NAV_ITEMS:
        assert not nav_icon(key).isNull()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `py -3.11 -m pytest tests/test_ui_window.py -q`
Expected: `ImportError: cannot import name 'NAV_ITEMS'`

- [ ] **Step 3: Replace `whisperfree/ui/window.py` entirely**

```python
"""Control panel window with sidebar navigation, plus the system tray icon."""

from __future__ import annotations

from typing import Callable, Dict, Optional

from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.config import AppConfig
from whisperfree.dictionary import Dictionary
from whisperfree.history import TranscriptionEntry, TranscriptionHistory
from whisperfree.ui import theme
from whisperfree.ui.dictionary import DictionaryPage
from whisperfree.ui.history import HistoryPage
from whisperfree.ui.home import HomePage
from whisperfree.ui.settings import SettingsPage
from whisperfree.ui.widgets import asset_path, friendly_username, make_label


NAV_ITEMS = (
    ("home", "Home"),
    ("history", "History"),
    ("dictionary", "Dictionary"),
    ("settings", "Settings"),
)
ICON_SIZE = 18


def _draw_icon(kind: str, color: QtGui.QColor) -> QtGui.QPixmap:
    ratio = 2.0
    pixmap = QtGui.QPixmap(int(ICON_SIZE * ratio), int(ICON_SIZE * ratio))
    pixmap.setDevicePixelRatio(ratio)
    pixmap.fill(QtCore.Qt.GlobalColor.transparent)
    painter = QtGui.QPainter(pixmap)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    pen = QtGui.QPen(color, 1.6)
    pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
    pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
    painter.setPen(pen)
    painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    P = QtCore.QPointF
    if kind == "home":
        path = QtGui.QPainterPath(P(2.5, 8.5))
        path.lineTo(9, 3)
        path.lineTo(15.5, 8.5)
        path.moveTo(4.5, 7.2)
        path.lineTo(4.5, 15)
        path.lineTo(13.5, 15)
        path.lineTo(13.5, 7.2)
        painter.drawPath(path)
    elif kind == "history":
        painter.drawEllipse(QtCore.QRectF(2.5, 2.5, 13, 13))
        painter.drawLine(P(9, 5.5), P(9, 9))
        painter.drawLine(P(9, 9), P(11.5, 10.5))
    elif kind == "dictionary":
        painter.drawRoundedRect(QtCore.QRectF(3.5, 2.5, 11, 13), 1.5, 1.5)
        painter.drawLine(P(6.5, 2.5), P(6.5, 15.5))
        painter.drawLine(P(8.8, 6), P(12, 6))
    elif kind == "settings":
        for y, knob_x in ((5.0, 11.0), (9.0, 6.0), (13.0, 12.0)):
            painter.drawLine(P(3, y), P(15, y))
            painter.setBrush(QtGui.QColor(theme.BACKGROUND))
            painter.drawEllipse(P(knob_x, y), 1.9, 1.9)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
    painter.end()
    return pixmap


def nav_icon(kind: str) -> QtGui.QIcon:
    """Icon that is grey when unselected and accent-coloured when selected."""
    icon = QtGui.QIcon()
    for state, colour in (
        (QtGui.QIcon.State.Off, theme.TEXT_SECONDARY),
        (QtGui.QIcon.State.On, theme.ACCENT),
    ):
        icon.addPixmap(_draw_icon(kind, QtGui.QColor(colour)), QtGui.QIcon.Mode.Normal, state)
    return icon


class ControlPanelWindow(QtWidgets.QMainWindow):
    """Sidebar + stacked pages: Home, History, Dictionary, Settings."""

    def __init__(
        self,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
        history: TranscriptionHistory,
        dictionary: Dictionary,
    ) -> None:
        super().__init__()
        self.setWindowTitle("WhisperFree")
        self.setWindowIcon(QtGui.QIcon(str(asset_path("app_icon.ico"))))
        self.resize(1040, 700)
        self.setMinimumSize(820, 560)
        self.setStyleSheet(theme.STYLESHEET)
        self.setFont(theme.ui_font())

        central = QtWidgets.QWidget(self)
        central.setObjectName("PanelCentral")
        layout = QtWidgets.QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)
        self._nav_buttons: Dict[str, QtWidgets.QPushButton] = {}
        layout.addWidget(self._build_sidebar())

        self._stack = QtWidgets.QStackedWidget()
        layout.addWidget(self._stack, 1)
        self.setCentralWidget(central)

        entries = history.entries()
        self.home_page = HomePage(friendly_username(), entries)
        self.history_page = HistoryPage(entries)
        self.dictionary_page = DictionaryPage(dictionary)
        self.settings_page = SettingsPage(config, on_save)
        self._pages: Dict[str, QtWidgets.QWidget] = {
            "home": self.home_page,
            "history": self.history_page,
            "dictionary": self.dictionary_page,
            "settings": self.settings_page,
        }
        for key, _label in NAV_ITEMS:
            self._stack.addWidget(self._pages[key])

        self._nav_group.buttonToggled.connect(self._handle_navigation)
        self.home_page.view_all_requested.connect(lambda: self.navigate_to("history"))
        self.navigate_to("home")

    def navigate_to(self, key: str) -> None:
        self._nav_buttons[key].setChecked(True)

    def current_page_key(self) -> str:
        current = self._stack.currentWidget()
        return next(key for key, page in self._pages.items() if page is current)

    def handle_history_entry(self, entry: TranscriptionEntry) -> None:
        """Receive new history entries from the controller."""
        self.home_page.add_entry(entry)
        self.history_page.add_entry(entry)

    def _build_sidebar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(212)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(16, 24, 16, 20)
        layout.setSpacing(4)

        brand = QtWidgets.QHBoxLayout()
        brand.setSpacing(10)
        logo = QtWidgets.QLabel()
        logo.setPixmap(QtGui.QIcon(str(asset_path("app_icon.ico"))).pixmap(22, 22))
        brand.addWidget(logo)
        brand.addWidget(make_label("WhisperFree", "AppName"))
        brand.addStretch(1)
        layout.addLayout(brand)
        layout.addSpacing(20)

        for index, (key, label) in enumerate(NAV_ITEMS):
            button = QtWidgets.QPushButton(label)
            button.setObjectName("NavButton")
            button.setCheckable(True)
            button.setIcon(nav_icon(key))
            button.setIconSize(QtCore.QSize(ICON_SIZE, ICON_SIZE))
            button.setMinimumHeight(36)
            button.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
            self._nav_group.addButton(button, index)
            self._nav_buttons[key] = button
            layout.addWidget(button)

        layout.addStretch(1)
        layout.addWidget(make_label("Hold Ctrl+Win to dictate", "SidebarFooter", wrap=True))
        return frame

    def _handle_navigation(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if checked:
            self._stack.setCurrentIndex(self._nav_group.id(button))


class TrayController(QtWidgets.QSystemTrayIcon):
    """System tray entry to access the control panel and quit."""

    def __init__(
        self,
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(QtGui.QIcon(str(asset_path("app_icon.ico"))), parent)
        self.setToolTip("WhisperFree")

        menu = QtWidgets.QMenu()
        panel_action = menu.addAction("Open Control Panel")
        quit_action = menu.addAction("Quit")

        panel_action.triggered.connect(on_open_settings)
        quit_action.triggered.connect(on_quit)

        self.setContextMenu(menu)
        self._menu = menu  # keep a reference so the menu is not garbage collected
```

- [ ] **Step 4: Update `open_settings` in `whisperfree/app.py`**

Replace the whole method with (reuses one window so page state and signal connections are not duplicated):

```python
    def open_settings(self) -> None:
        """Display the control panel, creating it on first use."""
        if self._panel_window is None:
            self._panel_window = ControlPanelWindow(
                config=self._config,
                on_save=self._handle_config_saved,
                history=self._history,
                dictionary=self._dictionary,
            )
            self.history_entry_added.connect(self._panel_window.handle_history_entry)
        self._panel_window.show()
        self._panel_window.raise_()
        self._panel_window.activateWindow()
```

- [ ] **Step 5: Run the full suite and an import smoke check**

Run: `py -3.11 -m pytest tests -q`
Expected: all pass.
Run: `py -3.11 -c "import whisperfree.app; print('ok')"`
Expected: `ok`
Run: `git grep -n "DashboardPage\|StatBadge\|HistoryListWidget\|_hint_banner" -- whisperfree`
Expected: no output (legacy UI fully removed).

- [ ] **Step 6: Commit**

```bash
git add whisperfree/ui/window.py whisperfree/app.py tests/test_ui_window.py
git commit -m "Assemble Voquill-style control panel with sidebar navigation"
```

---

### Task 11: Docs and manual verification (orchestrator, not a subagent)

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Update README**
  - Features: add Dictionary (terms + replacement rules), Launch on startup, Home stats (total words, day streak, WPM), searchable History.
  - Project layout: replace `ui.py` with the `ui/` package; add `dictionary.py`, `startup.py`, `run_whisperfree.pyw`, `tests/`.
  - Configuration Highlights: document `~/.whisperfree/dictionary.json` and that settings apply instantly (API key needs Save).
  - Add "Running tests": `py -3.11 -m pytest tests -q`.
  - Remove the stray `py -3 whisperfree/generate_assets.py` block (the script does not exist).
- [ ] **Step 2: Manual verification**
  - Launch `py -3.11 -m whisperfree.app`, open the control panel from the tray, screenshot each page, and check against the spec's visual language.
  - Add a term and a replacement; dictate a sentence containing both; confirm the pasted text and History entry.
  - Toggle Launch on startup; confirm `HKCU\Software\Microsoft\Windows\CurrentVersion\Run\WhisperFree` appears and disappears (`reg query`).
- [ ] **Step 3: Commit**

```bash
git add README.md
git commit -m "Document dictionary, launch on startup, and new control panel"
```
