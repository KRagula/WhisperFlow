"""Launch-on-startup support via the per-user Windows Run registry key."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
VALUE_NAME = "WhisperFree"
PROJECT_ROOT = Path(__file__).resolve().parent.parent
LAUNCHER_SCRIPT = PROJECT_ROOT / "run_whisperfree.pyw"


def is_supported() -> bool:
    """Launch on startup is only implemented for Windows."""
    return sys.platform == "win32"


def launch_command() -> str:
    """Return the command Windows should run at sign-in."""
    if getattr(sys, "frozen", False):
        return f'"{Path(sys.executable)}"'
    interpreter = Path(sys.executable)
    pythonw = interpreter.parent / "pythonw.exe"
    if pythonw.exists():
        interpreter = pythonw
    return f'"{interpreter}" "{LAUNCHER_SCRIPT}"'


def read_command(value_name: str = VALUE_NAME) -> Optional[str]:
    """Return the registered command, or None when not registered."""
    if not is_supported():
        return None
    import winreg

    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY) as key:
            value, _ = winreg.QueryValueEx(key, value_name)
    except FileNotFoundError:
        return None
    return str(value)


def is_enabled(value_name: str = VALUE_NAME) -> bool:
    """Whether WhisperFree is registered to launch at sign-in."""
    try:
        return read_command(value_name) is not None
    except OSError as exc:
        logger.warning("Could not read startup registry value: {}", exc)
        return False


def set_enabled(enabled: bool, value_name: str = VALUE_NAME) -> None:
    """Register or unregister launch at sign-in. Raises OSError on registry failure."""
    if not is_supported():
        return
    import winreg

    with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, value_name, 0, winreg.REG_SZ, launch_command())
        else:
            try:
                winreg.DeleteValue(key, value_name)
            except FileNotFoundError:
                pass
    logger.info("Launch on startup {}", "enabled" if enabled else "disabled")


def refresh_if_stale(value_name: str = VALUE_NAME) -> bool:
    """Rewrite the registered command if the app moved. Returns True when rewritten."""
    current = read_command(value_name)
    if current is None or current == launch_command():
        return False
    set_enabled(True, value_name)
    logger.info("Updated stale startup command: {}", current)
    return True
