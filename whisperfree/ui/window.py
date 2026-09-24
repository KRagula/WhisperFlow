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
