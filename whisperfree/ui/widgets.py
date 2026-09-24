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
