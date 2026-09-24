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
