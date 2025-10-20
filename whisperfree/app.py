"""Main application orchestration for WhisperFree."""

from __future__ import annotations

import signal
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional


from PyQt6 import QtCore, QtGui, QtWidgets

from whisperfree.audio import AudioRecorder
from whisperfree.config import AppConfig, load_config
from whisperfree.history import TranscriptionHistory
from whisperfree.hotkeys import HotkeyListener
from whisperfree.overlay import OverlayWindow
from whisperfree.paste import paste_text
from whisperfree.transcribe import TranscriptionRouter
from whisperfree.ui import ControlPanelWindow, TrayController
from whisperfree.utils.logger import get_logger, setup_logging


logger = get_logger(__name__)


class WhisperFreeController(QtCore.QObject):
    """Glue between input devices, transcription engines, and UI."""

    level_changed = QtCore.pyqtSignal(float)
    waveform_chunk = QtCore.pyqtSignal(object)
    toast_requested = QtCore.pyqtSignal(str, int)
    idle_requested = QtCore.pyqtSignal()
    recording_requested = QtCore.pyqtSignal()
    history_entry_added = QtCore.pyqtSignal(object)

    def __init__(self, app: QtWidgets.QApplication, config: AppConfig) -> None:
        super().__init__()
        self._app = app
        self._config = config
        self._overlay = OverlayWindow()
        if self._config.overlay_enabled:
            self._overlay.show_idle()
        else:
            self._overlay.hide_overlay()

        self.level_changed.connect(self._overlay.update_level)
        self.waveform_chunk.connect(self._overlay.ingest_waveform)
        self.toast_requested.connect(self._overlay.show_toast)
        self.idle_requested.connect(self._overlay.show_idle)
        self.recording_requested.connect(self._overlay.show_recording)

        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="whisperfree")
        self._transcriber = TranscriptionRouter(config)
        self._history = TranscriptionHistory()
        self._audio = AudioRecorder(
            config=config,
            level_callback=self._handle_level_update,
            waveform_callback=self._handle_waveform_update,
        )

        self._hotkeys = HotkeyListener(
            on_start=self._handle_push_to_talk_start,
            on_stop=self._handle_push_to_talk_stop,
            primary=config.hotkey_modifier_primary,
            secondary="windows" if config.hotkey_modifier_secondary == "win" else config.hotkey_modifier_secondary,
        )

        self._tray = TrayController(self.open_settings, self.quit)
        self._tray.show()

        self._panel_window: Optional[ControlPanelWindow] = None

    def start(self) -> None:
        """Start listeners and show overlay if required."""
        self._hotkeys.start()
        logger.info("Hotkey listener started (press and hold Ctrl+Win)")

    def quit(self) -> None:
        """Gracefully shut down."""
        logger.info("Shutting down WhisperFree.")
        self._hotkeys.stop()
        self._audio.stop()
        self._executor.shutdown(wait=False, cancel_futures=True)
        self._app.quit()

    def open_settings(self) -> None:
        """Display the settings dialog."""
        if self._panel_window and self._panel_window.isVisible():
            self._panel_window.raise_()
            self._panel_window.activateWindow()
            return
        self._panel_window = ControlPanelWindow(
            config=self._config,
            on_save=self._handle_config_saved,
            history=self._history,
        )
        self.history_entry_added.connect(self._panel_window.handle_history_entry)
        self._panel_window.show()

    def _handle_config_saved(self, config: AppConfig) -> None:
        logger.info("Configuration saved.")
        if config.overlay_enabled:
            self._overlay.show_idle()
        else:
            self._overlay.hide_overlay()

    def _handle_level_update(self, value: float) -> None:
        self.level_changed.emit(value)

    def _handle_waveform_update(self, samples, sample_rate: int) -> None:
        self.waveform_chunk.emit((samples, sample_rate))

    def _handle_push_to_talk_start(self) -> None:
        logger.info("Push-to-talk activated.")
        try:
            self._audio.start()
        except Exception as exc:
            logger.exception("Failed to start audio capture: %s", exc)
            self.toast_requested.emit("Audio input error", 2500)
            return
        if self._config.overlay_enabled:
            self.recording_requested.emit()

    def _handle_push_to_talk_stop(self) -> None:
        logger.info("Push-to-talk released.")
        self._audio.stop()
        audio_bytes = self._audio.get_wav_bytes()
        if not audio_bytes:
            self.toast_requested.emit("No speech detected", 2000)
            if self._config.overlay_enabled:
                self.idle_requested.emit()
            return
        # self.toast_requested.emit("Transcribing…", 1200)
        self._executor.submit(self._process_session, audio_bytes)

    def _process_session(self, audio_bytes: bytes) -> None:
        logger.info("Processing transcription payload of {} bytes", len(audio_bytes))
        try:
            result = self._transcriber.transcribe(audio_bytes)
        except Exception as exc:
            logger.exception("Transcription failed: %s", exc)
            self.toast_requested.emit("Transcription failed", 2500)
            self.idle_requested.emit()
            return

        transcribed_text = result.text

        if not transcribed_text.strip():
            self.toast_requested.emit("Nothing to paste", 2000)
            self.idle_requested.emit()
            return

        success = paste_text(
            transcribed_text,
            append_newline=self._config.append_newline,
            retries=self._config.paste_retries,
        )
        entry = self._history.add_entry(transcribed_text)
        self.history_entry_added.emit(entry)
        # if success:
        #     self.toast_requested.emit("Pasted!", 1500)
        # else:
        #     self.toast_requested.emit("Paste failed", 2500)
        self.idle_requested.emit()

    @property
    def history(self) -> TranscriptionHistory:
        """Expose the transcription history store for UI consumers."""
        return self._history


def _install_signal_handlers(controller: WhisperFreeController) -> None:
    signal.signal(signal.SIGINT, lambda *_: controller.quit())
    signal.signal(signal.SIGTERM, lambda *_: controller.quit())


def main() -> None:
    """Launch the WhisperFree desktop app."""
    setup_logging()
    config = load_config()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("WhisperFree")
    icon_path = Path(__file__).resolve().parent.parent / "assets" / "app_icon.ico"
    if icon_path.exists():
        app.setWindowIcon(QtGui.QIcon(str(icon_path)))  # type: ignore[name-defined]

    controller = WhisperFreeController(app, config)
    _install_signal_handlers(controller)
    controller.start()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
