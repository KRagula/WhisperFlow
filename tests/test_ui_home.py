from datetime import date, datetime

from PyQt6 import QtGui

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


def test_show_event_refreshes_greeting_and_stats(qapp):
    page = HomePage("Kanishka", [entry(24, words=10)], today=TODAY)
    before_words = page.words_card.value_label.text()
    before_streak = page.streak_card.value_label.text()

    page.showEvent(QtGui.QShowEvent())

    assert "Kanishka" in page.title_label.text()
    assert page.words_card.value_label.text() == before_words
    assert page.streak_card.value_label.text() == before_streak
