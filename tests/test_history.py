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
