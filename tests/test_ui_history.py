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
