# WhisperFree: Voquill-style UI, Dictionary, Launch on Startup — Design

Date: 2026-09-24
Status: Approved in conversation, pending written-spec review

## Goal

Make WhisperFree's control panel look and feel closer to Voquill, add a dictionary
(custom terms + replacement rules) that improves transcription output, and add a
"Launch on startup" option.

## Scope

In scope:
1. Restructure and restyle the control panel (light theme only).
2. Dictionary feature: custom terms (Whisper prompt hints) and replacement rules.
3. Launch-on-startup toggle (Windows, per-user).

Out of scope:
- The recording overlay / talking indicator (`whisperfree/overlay.py`) — unchanged by request.
- Dark mode / theme switching.
- Voquill features not requested (writing styles, chats, providers, audio playback, sync).
- Rewriting the UI in another toolkit.

Constraints:
- Remains a Windows-first PyQt6 app, Python 3.11/3.12.
- Existing uncommitted work is preserved (PyInstaller `build.py`, history copy button,
  `~/.whisperfree/.env` location, `_MEIPASS` asset paths, hotkey normalisation fix).
- Must work both from source and as the PyInstaller `--onedir` build.

## Architecture

```
whisperfree/
  dictionary.py      NEW  Dictionary store + build_prompt() + apply_replacements(). No Qt.
  startup.py         NEW  is_enabled() / set_enabled() / refresh_if_stale() via winreg.
  transcribe.py      ApiTranscriber.transcribe() gains optional `prompt`.
  history.py         TranscriptionEntry gains optional `duration`; stats helpers (streak, WPM).
  app.py             Owns the shared Dictionary; applies it in the pipeline; applies theme;
                     passes recording duration to history; refreshes stale startup entry.
  ui/                replaces whisperfree/ui.py
    __init__.py      re-exports ControlPanelWindow, TrayController (app.py import unchanged)
    theme.py         palette constants + one global QSS applied to QApplication
    window.py        ControlPanelWindow, sidebar, nav icons (QPainter-drawn)
    home.py          greeting, stat cards, hint banner, 5 most recent entries
    history.py       searchable, day-grouped full history
    dictionary.py    Terms / Replacements tabs
    settings.py      sectioned settings cards
    widgets.py       Card, ToggleSwitch, HistoryRow, SectionHeader, helpers
tests/
  test_dictionary.py
  test_startup.py
  test_history.py
```

Styling rule: widgets set `objectName`s; all visual styling lives in `ui/theme.py`.
No per-widget inline `setStyleSheet` except where dynamic state requires it.

## UI

### Visual language (light only)
- Window / sidebar background `#F7F7F8`; content cards white.
- Card: 1px `#E6E6EA` border, 12px radius, no shadow.
- Single accent: deep indigo (`#4332D8`), used for active nav item, primary buttons,
  toggles, links.
- Text: primary `#1C1B22`, secondary `#6B6A75`, muted `#9A99A3`.
- Font: "Segoe UI Variable", fallback "Segoe UI". Scale: 26px page title, 15px section
  header, 13px body, 12px caption.
- Checkboxes replaced by a custom pill `ToggleSwitch` widget.

### Sidebar
App name at top; nav items Home, History, Dictionary, Settings, each with a simple
QPainter-drawn icon (no new asset files); hotkey hint in the footer.

### Home
- Greeting by time of day: "Good morning/afternoon/evening, <Name>".
- Three stat cards: Total words, Day streak, Avg. words/min.
  - Day streak: consecutive local calendar days ending today (or yesterday, if nothing
    yet today) with at least one entry.
  - Avg. WPM: sum(words) / sum(duration minutes) over entries that have a duration;
    shows "—" when no entries have a duration.
- Slim hint banner: "Hold Ctrl+Win to dictate in any app".
- 5 most recent transcriptions; "View all →" navigates to History.

### History
- Search box filtering case-insensitively as you type.
- Entries grouped by local day; row = time, text (selectable), word count, Copy button.
- Rows built lazily (initial batch, more on scroll) so large histories stay responsive.
- New entries arriving from the controller appear at the top of Home and History.

### Dictionary
- Tab "Terms": input + "Add" button (Enter also adds); terms shown as removable chips
  in a flowing layout.
- Tab "Replacements": list of rows "When I say" → "Replace with" with edit and delete;
  an add row at top.
- Changes persist immediately (no Save button).

### Settings (cards)
- General: Launch on startup, Show overlay while dictating, Append newline after paste.
- Audio: Microphone (+ Refresh), Input gain slider.
- Transcription: Language.
- OpenAI: API key field, Test and Save buttons.
- Toggles, microphone, gain, and language apply immediately. The API key requires an
  explicit Save (or successful Test) so partially typed keys are never persisted.

## Dictionary

### Storage
`~/.whisperfree/dictionary.json`:
```json
{ "version": 1,
  "terms": ["Kanishka", "5Point", "PyQt6"],
  "replacements": [{ "match": "five point", "replace": "5Point" }] }
```
- Atomic writes: write to a temp file in the same dir, then `os.replace`.
- Missing file → empty dictionary.
- Unreadable/invalid file → rename to `dictionary.json.bak` (overwriting any older
  .bak), log a warning, start empty.

### `Dictionary` API
One instance, created by the controller and shared with the UI. All methods are guarded
by a `threading.Lock` (UI thread writes, worker thread reads).
- `terms() -> list[str]`, `replacements() -> list[Replacement]` (copies).
- `add_term(term) -> bool`: strip; reject blank or case-insensitive duplicate.
- `remove_term(term)`.
- `add_replacement(match, replace) -> bool`: strip match; reject blank match or
  case-insensitive duplicate match; blank `replace` allowed (deletes the phrase).
- `update_replacement(index, match, replace) -> bool`, `remove_replacement(index)`.
- `build_prompt() -> str`: `"Glossary: A, B, C."`; if longer than 800 chars, keep the
  most recently added terms that fit. Empty string when no terms.
- `apply_replacements(text) -> str`: one combined regex of all rules, alternatives
  sorted longest-first, `re.IGNORECASE`, boundaries `(?<!\w)` / `(?!\w)`, single pass
  (no chaining). After replacement, collapse runs of spaces created by blank
  replacements and strip the result.
- Every mutation saves to disk.

### Pipeline (`WhisperFreeController._process_session`)
```
audio → Whisper(prompt=dictionary.build_prompt() or omitted)
      → dictionary.apply_replacements → paste → history.add_entry(final_text, duration)
```
History stores the final, pasted text.

## Launch on startup

`whisperfree/startup.py`, key `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`,
value name `WhisperFree`.
- `launch_command()`:
  - Frozen (`sys.frozen`): `"<sys.executable>"`.
  - Source: `"<dir of sys.executable>\pythonw.exe" -m whisperfree.app` (falls back to
    `sys.executable` if `pythonw.exe` is absent).
- `is_enabled()` reads the registry (source of truth; no config field).
- `set_enabled(bool)` writes or deletes the value; raises `OSError` on failure.
- `refresh_if_stale()`: called at app start; if the value exists but differs from
  `launch_command()`, rewrite it.
- UI: on `OSError`, show a message box and revert the toggle.
- Non-Windows: functions are no-ops returning False; the toggle is hidden.

## History changes
- `TranscriptionEntry.duration: Optional[float]` (seconds); serialised only when set.
- `add_entry(text, timestamp=None, duration=None)`.
- Duration source: `AudioRecorder` exposes `last_duration` = frames / sample_rate,
  captured in `_handle_push_to_talk_stop` and passed through to `_process_session`.
- Stats helpers (pure functions, testable): `day_streak(entries, today)`,
  `average_wpm(entries)`.

## Error handling
- Dictionary load/save failures log and never crash the app; save failures surface a
  status message in the Dictionary page.
- A regex build failure is impossible by construction (all patterns `re.escape`d).
- Startup registry failures surface a message box and revert the toggle.

## Testing
- `tests/test_dictionary.py`: add/dedupe terms, prompt format + truncation, whole-word
  case-insensitive replacement, longest-first, no chaining, special-char rules
  (`c++`, `@me`), blank replacement + whitespace cleanup, corrupt-file → .bak,
  atomic save round-trip (tmp_path).
- `tests/test_startup.py`: `launch_command()` for frozen vs source (monkeypatched
  `sys`); real registry round-trip against a throwaway value name, cleaned up.
- `tests/test_history.py`: streak (today, yesterday, gaps), WPM with/without durations,
  loading legacy entries without `duration`.
- Manual: launch app, screenshot each page, dictate with a term and a replacement,
  toggle startup and confirm the registry value appears/disappears.
