"""Global push-to-talk hotkey handling for WhisperFree."""

from __future__ import annotations

import time
from typing import Callable, Optional, Set

import keyboard

from whisperfree.utils.logger import get_logger


Handler = Callable[[], None]

logger = get_logger(__name__)


def _normalise_key(name: str) -> str:
    """Normalise key names so comparisons stay consistent."""
    normalised = keyboard.normalize_name(name or "")
    lower = normalised.replace("_", " ").strip().lower()
    for prefix in ("left ", "right "):
        if lower.startswith(prefix):
            lower = lower[len(prefix) :]
            break
    replacements = {
        "win": "windows",
        "menu": "alt",
        "control": "ctrl",
    }
    return replacements.get(lower, lower)


class HotkeyListener:
    """Listen for Ctrl+Win (or configured) push-to-talk gesture."""

    def __init__(
        self,
        on_start: Handler,
        on_stop: Handler,
        primary: str = "ctrl",
        secondary: str = "windows",
        debounce_ms: int = 150,
    ) -> None:
        self._on_start = on_start
        self._on_stop = on_stop
        self._required_keys = {_normalise_key(primary), _normalise_key(secondary)}
        self._debounce = debounce_ms / 1000.0
        self._pressed: Set[str] = set()
        self._active = False
        self._last_event_ts = 0.0
        self._hook: Optional[Callable] = None

    def start(self) -> None:
        """Begin listening for keyboard events."""
        if self._hook is not None:
            return
        self._hook = keyboard.hook(self._handle_event, suppress=False)

    def stop(self) -> None:
        """Stop listening for keyboard events."""
        if self._hook is not None:
            keyboard.unhook(self._hook)
            self._hook = None
        self._pressed.clear()
        self._active = False

    def update_hotkey(self, primary: str, secondary: str) -> None:
        """Change the required key combination on the fly."""
        self._required_keys = {_normalise_key(primary), _normalise_key(secondary)}
        self._pressed.clear()
        self._active = False

    def _handle_event(self, event: keyboard.KeyboardEvent) -> None:
        if event.event_type not in ("down", "up"):
            return
        key = _normalise_key(event.name or "")
        if not key:
            return

        if event.event_type == "down":
            if key not in self._required_keys:
                return
            self._pressed.add(key)
            logger.debug("Hotkey press raw=%s normalised=%s pressed=%s", event.name, key, sorted(self._pressed))
            if self._required_keys.issubset(self._pressed) and not self._active:
                now = time.monotonic()
                if (now - self._last_event_ts) < self._debounce:
                    return
                self._last_event_ts = now
                self._active = True
                self._safe_call(self._on_start)
        else:  # event_type == "up"
            if key in self._pressed:
                self._pressed.remove(key)
            logger.debug("Hotkey release raw=%s normalised=%s pressed=%s", event.name, key, sorted(self._pressed))
            if self._active and not self._required_keys.issubset(self._pressed):
                self._last_event_ts = time.monotonic()
                self._active = False
                self._safe_call(self._on_stop)

    @staticmethod
    def _safe_call(handler: Handler) -> None:
        try:
            handler()
        except Exception:  # pragma: no cover - defensive
            import traceback

            traceback.print_exc()
