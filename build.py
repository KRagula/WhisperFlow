"""Build WhisperFree into a standalone Windows executable using PyInstaller."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
ENTRY = ROOT / "whisperfree" / "app.py"
ICON = ROOT / "assets" / "app_icon.ico"
ASSETS = ROOT / "assets"


def main() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onedir",
        "--windowed",
        f"--name=WhisperFree",
        f"--icon={ICON}",
        f"--add-data={ASSETS};assets",
        str(ENTRY),
    ]
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, check=True)
    print("\nDone! Executable is in dist/WhisperFree/")


if __name__ == "__main__":
    main()
