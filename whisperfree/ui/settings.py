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
        self.sound_toggle = ToggleSwitch()
        general.body.addWidget(
            SettingRow(
                "Play sounds",
                "Chime when you press and release the dictation hotkey.",
                self.sound_toggle,
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
        self.mic_combo.setMaximumWidth(320)
        self.mic_combo.setSizeAdjustPolicy(
            QtWidgets.QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        self.mic_combo.setMinimumContentsLength(20)
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
        self.sound_toggle.toggled.connect(lambda checked: self._update(sound_enabled=checked))
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

        app = QtWidgets.QApplication.instance()
        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

    # ------------------------------------------------------------------ loading

    def _apply_config(self) -> None:
        if startup.is_supported():
            self.startup_toggle.setChecked(startup.is_enabled())
        self.overlay_toggle.setChecked(self._config.overlay_enabled)
        self.sound_toggle.setChecked(self._config.sound_enabled)
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

    def shutdown(self) -> None:
        """Wait briefly for an in-flight API test so Qt never destroys a running thread."""
        thread = self._api_test_thread
        if thread is not None and thread.isRunning():
            thread.quit()
            thread.wait(3000)
