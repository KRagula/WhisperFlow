"""Control panel and tray UI built with PyQt6."""

from __future__ import annotations

import getpass
from pathlib import Path
from typing import Callable, Optional, Sequence

from PyQt6 import QtCore, QtGui, QtWidgets
from openai import OpenAIError

from whisperfree import models
from whisperfree.audio import list_microphones
from whisperfree.config import AppConfig
from whisperfree.history import TranscriptionEntry, TranscriptionHistory
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

_ENV_FILE_PATH = Path(__file__).resolve().parent.parent / ".env"


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
        existing = _ENV_FILE_PATH.read_text(encoding="utf-8").splitlines()
        for line in existing:
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
    else:
        lines = []
    if not updated:
        lines.append(f"{key}={value}")
    _ENV_FILE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _ENV_FILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


class ControlPanelWindow(QtWidgets.QMainWindow):
    """Modern control panel with dashboard and settings pages."""

    def __init__(
        self,
        config: AppConfig,
        on_save: Callable[[AppConfig], None],
        history: TranscriptionHistory,
    ) -> None:
        super().__init__()
        self.setWindowTitle("WhisperFree")
        self.setWindowIcon(QtGui.QIcon(str(_asset_path("app_icon.ico"))))
        self.resize(960, 640)

        self._config = config
        self._on_save = on_save
        self._history_store = history
        self._display_name = _friendly_username()
        self._home_button: Optional[SidebarButton] = None

        central = QtWidgets.QWidget(self)
        central.setObjectName("PanelCentral")
        main_layout = QtWidgets.QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self._nav_group = QtWidgets.QButtonGroup(self)
        self._nav_group.setExclusive(True)

        sidebar = self._build_sidebar()
        main_layout.addWidget(sidebar)

        self._stack = QtWidgets.QStackedWidget()
        main_layout.addWidget(self._stack, 1)

        self.setCentralWidget(central)

        entries = self._history_store.entries()
        total_words = self._history_store.total_word_count()
        self._dashboard = DashboardPage(self._display_name, entries, total_words)
        self._settings = SettingsPage(self._config, self._on_settings_saved)

        self._stack.addWidget(self._dashboard)
        self._stack.addWidget(self._settings)
        self._nav_group.buttonToggled.connect(self._handle_navigation)

        # Activate the first page
        if self._home_button:
            self._home_button.setChecked(True)
        self._stack.setCurrentIndex(0)

        self._apply_panel_styles()

    def handle_history_entry(self, entry: TranscriptionEntry) -> None:
        """Receive new history entries from the controller."""
        self._dashboard.add_entry(entry)

    def _apply_panel_styles(self) -> None:
        palette = self.palette()
        palette.setColor(QtGui.QPalette.ColorRole.Window, QtGui.QColor("#f7f6fb"))
        self.setPalette(palette)
        self.setAutoFillBackground(True)

    def _build_sidebar(self) -> QtWidgets.QFrame:
        frame = QtWidgets.QFrame()
        frame.setObjectName("Sidebar")
        frame.setFixedWidth(220)
        layout = QtWidgets.QVBoxLayout(frame)
        layout.setContentsMargins(24, 32, 24, 24)
        layout.setSpacing(12)

        title = QtWidgets.QLabel("WhisperFree")
        title.setStyleSheet("font-size: 20px; font-weight: 600; color: #3a3057;")
        layout.addWidget(title)
        layout.addSpacing(12)

        home_btn = SidebarButton("Home")
        settings_btn = SidebarButton("Settings")
        self._home_button = home_btn
        self._nav_group.addButton(home_btn, 0)
        self._nav_group.addButton(settings_btn, 1)
        layout.addWidget(home_btn)
        layout.addWidget(settings_btn)
        layout.addStretch(1)

        footer = QtWidgets.QLabel("Press Ctrl+Win to start dictating")
        footer.setWordWrap(True)
        footer.setStyleSheet("color: #766f88; font-size: 11px;")
        layout.addWidget(footer)
        return frame

    def _handle_navigation(self, button: QtWidgets.QAbstractButton, checked: bool) -> None:
        if not checked:
            return
        index = self._nav_group.id(button)
        self._stack.setCurrentIndex(index)

    def _on_settings_saved(self, config: AppConfig) -> None:
        self._on_save(config)
        self._dashboard.refresh_stats(self._history_store.total_word_count())
        self.statusBar().showMessage("Settings saved", 2500)


class SidebarButton(QtWidgets.QPushButton):
    """Navigation button with toggle styling."""

    def __init__(self, text: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(text, parent)
        self.setCheckable(True)
        self.setCursor(QtGui.QCursor(QtCore.Qt.CursorShape.PointingHandCursor))
        self.setMinimumHeight(40)
        self.setStyleSheet(
            """
            QPushButton {
                border: none;
                border-radius: 12px;
                text-align: left;
                padding: 6px 14px;
                font-size: 14px;
                font-weight: 500;
                color: #4f4669;
            }
            QPushButton:hover {
                background-color: #e9e4fb;
            }
            QPushButton:checked {
                background-color: #4332d8;
                color: white;
            }
            """
        )


class DashboardPage(QtWidgets.QWidget):
    """Home dashboard with welcome message, stats, and history."""

    def __init__(
        self,
        name: str,
        entries: Sequence[TranscriptionEntry],
        total_words: int,
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        super().__init__(parent)
        self._entries = list(entries)
        self._total_words = total_words

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(24)

        header = QtWidgets.QVBoxLayout()
        self._welcome = QtWidgets.QLabel(f"Welcome back, {name or 'there'}")
        self._welcome.setStyleSheet("font-size: 28px; font-weight: 600; color: #2f254d;")
        header.addWidget(self._welcome)

        stats_row = QtWidgets.QHBoxLayout()
        stats_row.setSpacing(12)
        self._words_badge = StatBadge("Words transcribed", f"{self._total_words:,}")
        stats_row.addWidget(self._words_badge)
        stats_row.addStretch(1)
        header.addLayout(stats_row)
        layout.addLayout(header)

        layout.addWidget(_hint_banner())

        self._history_list = HistoryListWidget()
        self._history_list.set_entries(self._entries)
        layout.addWidget(self._history_list, 1)

    def refresh_stats(self, words: int) -> None:
        self._total_words = words
        self._words_badge.set_value(f"{words:,}")

    def add_entry(self, entry: TranscriptionEntry) -> None:
        self._entries.insert(0, entry)
        self._total_words += entry.words
        self._words_badge.set_value(f"{self._total_words:,}")
        self._history_list.prepend_entry(entry)


class StatBadge(QtWidgets.QFrame):
    """Small capsule showing a single statistic."""

    def __init__(self, label: str, value: str, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("StatBadge")
        self.setStyleSheet(
            """
            QFrame#StatBadge {
                background-color: white;
                border-radius: 14px;
                border: 1px solid #ded9f4;
            }
            """
        )
        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(4)
        label_widget = QtWidgets.QLabel(label)
        label_widget.setStyleSheet("color: #6f6591; font-size: 12px;")
        self._value_widget = QtWidgets.QLabel(value)
        self._value_widget.setStyleSheet("font-size: 20px; font-weight: 600; color: #2f254d;")
        layout.addWidget(label_widget)
        layout.addWidget(self._value_widget)

    def set_value(self, value: str) -> None:
        self._value_widget.setText(value)


class HistoryListWidget(QtWidgets.QScrollArea):
    """Scrollable list of transcription history items grouped by day."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.setFrameShape(QtWidgets.QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarPolicy.ScrollBarAlwaysOff)

        self._entries: list[TranscriptionEntry] = []
        self._container = QtWidgets.QWidget()
        self._layout = QtWidgets.QVBoxLayout(self._container)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self._layout.addStretch(1)
        self.setWidget(self._container)

    def set_entries(self, entries: Sequence[TranscriptionEntry]) -> None:
        self._entries = list(entries)
        self._rebuild()

    def prepend_entry(self, entry: TranscriptionEntry) -> None:
        self._entries.insert(0, entry)
        self._rebuild()

    def _clear_layout(self) -> None:
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

    def _rebuild(self) -> None:
        self._clear_layout()
        last_header = None
        for entry in self._entries:
            day_label = _format_day(entry.timestamp)
            if day_label != last_header:
                header = QtWidgets.QLabel(day_label)
                header.setStyleSheet("margin-top: 12px; font-size: 12px; font-weight: 600; color: #8c85a3;")
                self._layout.addWidget(header)
                last_header = day_label
            self._layout.addWidget(HistoryItem(entry))
        self._layout.addStretch(1)


class HistoryItem(QtWidgets.QFrame):
    """Visual representation of a single transcription entry."""

    def __init__(self, entry: TranscriptionEntry, parent: Optional[QtWidgets.QWidget] = None) -> None:
        super().__init__(parent)
        self.setObjectName("HistoryItem")
        self.setStyleSheet(
            """
            QFrame#HistoryItem {
                background-color: white;
                border-radius: 12px;
                border: 1px solid #ece8fb;
            }
            """
        )
        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)
        layout.setSpacing(16)

        time_label = QtWidgets.QLabel(_format_time(entry.timestamp))
        time_label.setStyleSheet("font-weight: 600; color: #574d72;")
        layout.addWidget(time_label)

        text_label = QtWidgets.QLabel(entry.text.strip())
        text_label.setWordWrap(True)
        text_label.setStyleSheet("color: #42385f;")
        layout.addWidget(text_label, 1)

        words_label = QtWidgets.QLabel(f"{entry.words} words")
        words_label.setStyleSheet("color: #8c85a3; font-size: 12px;")
        layout.addWidget(words_label)


class SettingsPage(QtWidgets.QWidget):
    """Settings content embedded in the control panel."""

    def __init__(self, config: AppConfig, on_save: Callable[[AppConfig], None]) -> None:
        super().__init__()
        self._config = config
        self._on_save = on_save
        self._api_key = config.resolve_api_key() or ""
        self._api_test_thread: Optional[QtCore.QThread] = None
        self._api_test_worker: Optional[_ApiTestWorker] = None
        self._pending_api_key: Optional[str] = None
        self._mic_warning_shown = False

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(36, 32, 36, 32)
        layout.setSpacing(24)

        title = QtWidgets.QLabel("Settings")
        title.setStyleSheet("font-size: 26px; font-weight: 600; color: #2f254d;")
        layout.addWidget(title)

        form_frame = QtWidgets.QFrame()
        form_frame.setObjectName("SettingsFrame")
        form_frame.setStyleSheet(
            """
            QFrame#SettingsFrame {
                background-color: white;
                border-radius: 16px;
                border: 1px solid #ded9f4;
            }
            """
        )
        form_layout = QtWidgets.QFormLayout(form_frame)
        form_layout.setContentsMargins(28, 24, 28, 24)
        form_layout.setHorizontalSpacing(24)
        form_layout.setVerticalSpacing(18)

        self.mic_combo = QtWidgets.QComboBox()
        self.refresh_mics_button = QtWidgets.QPushButton("Refresh")
        mic_widget = _wrap_layout(
            [
                (self.mic_combo, 1),
                (self.refresh_mics_button, 0),
            ]
        )
        form_layout.addRow("Microphone", mic_widget)

        self.language_combo = QtWidgets.QComboBox()
        for code, label_text in models.LANGUAGE_CHOICES:
            self.language_combo.addItem(label_text, code)
        form_layout.addRow("Language", self.language_combo)

        self.append_newline_checkbox = QtWidgets.QCheckBox("Append newline after paste")
        form_layout.addRow("Pasting", self.append_newline_checkbox)

        self.overlay_checkbox = QtWidgets.QCheckBox("Show overlay while dictating")
        form_layout.addRow("Overlay", self.overlay_checkbox)

        self.gain_slider = QtWidgets.QSlider(QtCore.Qt.Orientation.Horizontal)
        self.gain_slider.setRange(-120, 240)
        self.gain_label = QtWidgets.QLabel("Input gain: 0 dB")
        gain_widget = _wrap_layout([(self.gain_slider, 1)])
        form_layout.addRow(self.gain_label, gain_widget)

        self.api_key_edit = QtWidgets.QLineEdit()
        self.api_key_edit.setEchoMode(QtWidgets.QLineEdit.EchoMode.Password)
        self.test_api_button = QtWidgets.QPushButton("Test API")
        self._test_api_default_label = self.test_api_button.text()
        api_row = _wrap_layout([(self.api_key_edit, 1), (self.test_api_button, 0)])
        form_layout.addRow("OpenAI API Key", api_row)

        layout.addWidget(form_frame)

        buttons_row = QtWidgets.QHBoxLayout()
        buttons_row.addStretch(1)
        self.save_button = QtWidgets.QPushButton("Save changes")
        self.save_button.setDefault(True)
        self.save_button.setStyleSheet(
            """
            QPushButton {
                background-color: #4332d8;
                color: white;
                padding: 8px 20px;
                border-radius: 10px;
                font-weight: 600;
            }
            QPushButton:hover {
                background-color: #3727b7;
            }
            """
        )
        buttons_row.addWidget(self.save_button)
        layout.addLayout(buttons_row)

        self.refresh_mics_button.clicked.connect(self._populate_microphones)
        self.save_button.clicked.connect(self._handle_save)
        self.gain_slider.valueChanged.connect(self._update_gain_label)
        self.test_api_button.clicked.connect(self._handle_test_api)

        self._populate_microphones()
        self._apply_config()

    def _apply_config(self) -> None:
        if self._config.mic_device_name:
            index = self.mic_combo.findText(self._config.mic_device_name)
            if index >= 0:
                self.mic_combo.setCurrentIndex(index)

        language_index = self.language_combo.findData(self._config.language)
        if language_index >= 0:
            self.language_combo.setCurrentIndex(language_index)

        self.append_newline_checkbox.setChecked(self._config.append_newline)
        self.overlay_checkbox.setChecked(self._config.overlay_enabled)
        self.gain_slider.setValue(int(self._config.input_gain_db * 10))
        self._update_gain_label(self.gain_slider.value())
        self.api_key_edit.setText(self._api_key)

    def _populate_microphones(self) -> None:
        current = self.mic_combo.currentText()
        self.mic_combo.clear()
        try:
            devices = list_microphones()
        except Exception as exc:  # pragma: no cover - defensive
            logger.bind(error=str(exc)).warning("Failed to refresh microphone list")
            if not self._mic_warning_shown:
                QtWidgets.QMessageBox.warning(
                    self,
                    "Microphones",
                    "Unable to refresh microphone list. The system default input will be used.",
                )
                self._mic_warning_shown = True
            devices = []
        else:
            self._mic_warning_shown = False
        self.mic_combo.addItem("System Default", userData=None)
        for device in devices:
            self.mic_combo.addItem(device, userData=device)
        if current:
            idx = self.mic_combo.findText(current)
            if idx >= 0:
                self.mic_combo.setCurrentIndex(idx)

    def _update_gain_label(self, value: int) -> None:
        db_value = value / 10.0
        self.gain_label.setText(f"Input gain: {db_value:+.1f} dB")

    def _handle_save(self) -> None:
        config = self._config
        config.mic_device_name = self.mic_combo.currentData()
        config.language = self.language_combo.currentData()
        config.append_newline = self.append_newline_checkbox.isChecked()
        config.overlay_enabled = self.overlay_checkbox.isChecked()
        config.input_gain_db = self.gain_slider.value() / 10.0

        api_key = self.api_key_edit.text().strip()
        if api_key:
            self._set_api_key(api_key)

        config.save()
        self._on_save(config)

    def _set_api_key(self, api_key: str) -> None:
        import os

        os.environ[self._config.api_key_env] = api_key
        self._api_key = api_key
        try:
            _update_env_file(self._config.api_key_env, api_key)
        except Exception as exc:  # pragma: no cover - defensive
            logger.bind(error=str(exc)).warning("Failed to update .env file with new API key.")

    def _handle_test_api(self) -> None:
        api_key = self.api_key_edit.text().strip()
        if not api_key:
            QtWidgets.QMessageBox.warning(self, "OpenAI", "Enter an API key first.")
            return

        if self._api_test_thread and self._api_test_thread.isRunning():
            return

        self._pending_api_key = api_key
        self.test_api_button.setEnabled(False)
        self.test_api_button.setText("Testing...")

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
        self.test_api_button.setText(self._test_api_default_label)

        if success:
            QtWidgets.QMessageBox.information(self, "OpenAI", "API key validated successfully.")
            if self._pending_api_key:
                self._set_api_key(self._pending_api_key)
        else:
            message = str(error) if error else "Unknown error."
            QtWidgets.QMessageBox.critical(self, "OpenAI", f"API check failed:\n{message}")
            if error:
                logger.bind(error=str(error)).error("OpenAI test failed")
            else:  # pragma: no cover - defensive
                logger.error("OpenAI test failed with unknown error")

        self._pending_api_key = None
        self._api_test_worker = None
        self._api_test_thread = None


class TrayController(QtWidgets.QSystemTrayIcon):
    """System tray entry to access the control panel and quit."""

    def __init__(
        self,
        on_open_settings: Callable[[], None],
        on_quit: Callable[[], None],
        parent: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        icon_path = _asset_path("app_icon.ico")
        super().__init__(QtGui.QIcon(str(icon_path)), parent)
        self.setToolTip("WhisperFree")

        menu = QtWidgets.QMenu()
        panel_action = menu.addAction("Open Control Panel")
        quit_action = menu.addAction("Quit")

        panel_action.triggered.connect(on_open_settings)
        quit_action.triggered.connect(on_quit)

        self.setContextMenu(menu)


def _wrap_layout(widgets: Sequence[tuple[QtWidgets.QWidget, int]]) -> QtWidgets.QWidget:
    container = QtWidgets.QWidget()
    layout = QtWidgets.QHBoxLayout(container)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(10)
    for widget, stretch in widgets:
        layout.addWidget(widget, stretch)
    return container


def _format_day(timestamp: QtCore.QDateTime | object) -> str:
    if isinstance(timestamp, QtCore.QDateTime):
        dt = timestamp.toPyDateTime()
    else:
        dt = timestamp  # type: ignore[assignment]
    if hasattr(dt, "astimezone"):
        local = dt.astimezone()
    else:  # pragma: no cover - unexpected types
        local = dt
    return local.strftime("%A, %B %d, %Y")


def _format_time(timestamp: QtCore.QDateTime | object) -> str:
    if isinstance(timestamp, QtCore.QDateTime):
        dt = timestamp.toPyDateTime()
    else:
        dt = timestamp  # type: ignore[assignment]
    if hasattr(dt, "astimezone"):
        local = dt.astimezone()
    else:  # pragma: no cover - unexpected types
        local = dt
    return local.strftime("%I:%M %p").lstrip("0")


def _hint_banner() -> QtWidgets.QFrame:
    frame = QtWidgets.QFrame()
    frame.setObjectName("HintBanner")
    frame.setStyleSheet(
        """
        QFrame#HintBanner {
            background-color: #fef5d8;
            border-radius: 16px;
            border: 1px solid #f7d88a;
        }
        """
    )
    layout = QtWidgets.QVBoxLayout(frame)
    layout.setContentsMargins(24, 24, 24, 24)
    layout.setSpacing(12)
    headline = QtWidgets.QLabel("Hold down Ctrl+Win to dictate in any app")
    headline.setStyleSheet("font-size: 18px; font-weight: 600; color: #3b2f09;")
    body = QtWidgets.QLabel(
        "Dictate into email, documents, or messages. Keep holding the shortcut to capture your thoughts instantly."
    )
    body.setWordWrap(True)
    body.setStyleSheet("color: #6d5723; font-size: 13px;")
    layout.addWidget(headline)
    layout.addWidget(body)
    return frame


def _friendly_username() -> str:
    try:
        return getpass.getuser().split("\\")[-1].capitalize()
    except Exception:  # pragma: no cover - fallback
        return ""


def _asset_path(name: str) -> Path:
    base = Path(__file__).resolve().parent.parent / "assets"
    return base / name
