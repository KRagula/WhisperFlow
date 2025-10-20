"""Clipboard and paste helpers."""

from __future__ import annotations

import threading
import time
from typing import Optional

import keyboard
import pyperclip

from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)


def paste_text(
    text: str,
    append_newline: bool = True,
    retries: int = 1,
    retry_delay: float = 0.15,
    restore_clipboard: bool = True,
    restore_delay: float = 0.25,
) -> bool:
    """Copy text to the clipboard and simulate Ctrl+V into the focused field."""
    sanitised = text.rstrip("\r\n")
    payload = sanitised + ("\n" if append_newline else "")
    original: Optional[str] = None

    try:
        if restore_clipboard:
            try:
                original = pyperclip.paste()
            except pyperclip.PyperclipException:
                logger.warning("Could not read clipboard to save state.")
        pyperclip.copy(payload)
    except pyperclip.PyperclipException as exc:
        logger.bind(error=str(exc)).error("Clipboard copy failed.")
        return False

    for attempt in range(retries + 1):
        try:
            keyboard.send("ctrl+v")
            logger.info("Paste attempt %s successful", attempt + 1)
            break
        except Exception as exc:  # pragma: no cover - system-level failure
            logger.bind(error=str(exc)).exception("Paste attempt failed")
            if attempt >= retries:
                return False
            time.sleep(retry_delay)

    if restore_clipboard and original is not None:
        # Delay restoration so the target app finishes reading the clipboard before we revert.
        def _restore_clipboard(value: str) -> None:
            try:
                pyperclip.copy(value)
            except pyperclip.PyperclipException:
                logger.warning("Failed to restore original clipboard contents.")

        timer = threading.Timer(restore_delay, _restore_clipboard, args=(original,))
        timer.daemon = True
        timer.start()

    return True
