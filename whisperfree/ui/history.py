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
