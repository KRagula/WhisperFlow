"""Short two-note chimes played when push-to-talk starts and stops."""

from __future__ import annotations

import io
import sys
import tempfile
import wave
from pathlib import Path
from typing import Callable, Optional, Tuple

import numpy as np

from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)

SAMPLE_RATE = 44100
START_NOTES: Tuple[float, float] = (587.33, 880.0)  # D5 -> A5: rising "bud-duh"
STOP_NOTES: Tuple[float, float] = (880.0, 587.33)  # A5 -> D5: falling "duh-bud"
FIRST_NOTE_SECONDS = 0.11
GAP_SECONDS = 0.015
SECOND_NOTE_SECONDS = 0.13
PEAK_VOLUME = 0.35
ATTACK_SECONDS = 0.005
RELEASE_SECONDS = 0.012
DECAY_RATE = 14.0  # per second; gives a soft "bell" tail

SOUNDS_DIR = Path(tempfile.gettempdir()) / "whisperfree-sounds"


def _note(frequency: float, seconds: float) -> np.ndarray:
    count = int(SAMPLE_RATE * seconds)
    t = np.arange(count) / SAMPLE_RATE
    # A quiet octave overtone makes the sine sound less like a test tone.
    tone = np.sin(2 * np.pi * frequency * t) + 0.25 * np.sin(4 * np.pi * frequency * t)
    envelope = np.minimum(1.0, t / ATTACK_SECONDS) * np.exp(-DECAY_RATE * t)
    release = min(count, int(SAMPLE_RATE * RELEASE_SECONDS))
    envelope[count - release:] *= np.linspace(1.0, 0.0, release)
    return tone * envelope


def chime_samples(notes: Tuple[float, float]) -> np.ndarray:
    """Float samples in [-PEAK_VOLUME, PEAK_VOLUME] for a two-note chime."""
    gap = np.zeros(int(SAMPLE_RATE * GAP_SECONDS))
    samples = np.concatenate([_note(notes[0], FIRST_NOTE_SECONDS), gap, _note(notes[1], SECOND_NOTE_SECONDS)])
    return samples * (PEAK_VOLUME / np.max(np.abs(samples)))


def chime_wav_bytes(notes: Tuple[float, float]) -> bytes:
    """The chime as a mono 16-bit PCM WAV file."""
    pcm = (chime_samples(notes) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(SAMPLE_RATE)
        wav.writeframes(pcm.tobytes())
    return buffer.getvalue()


def _play_with_winsound(path: Path) -> None:
    if sys.platform != "win32":
        return
    import winsound

    # SND_ASYNC returns immediately, so the keyboard hook thread is never blocked.
    winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_ASYNC | winsound.SND_NODEFAULT)


class ChimePlayer:
    """Plays the start/stop chimes without blocking and without ever raising."""

    def __init__(
        self,
        directory: Path = SOUNDS_DIR,
        play_file: Callable[[Path], None] = _play_with_winsound,
    ) -> None:
        self._play_file = play_file
        self._start_path: Optional[Path] = None
        self._stop_path: Optional[Path] = None
        try:
            directory.mkdir(parents=True, exist_ok=True)
            start_path, stop_path = directory / "start.wav", directory / "stop.wav"
            start_path.write_bytes(chime_wav_bytes(START_NOTES))
            stop_path.write_bytes(chime_wav_bytes(STOP_NOTES))
        except OSError as exc:
            logger.warning("Dictation sounds disabled; could not write chime files: {}", exc)
            return
        self._start_path, self._stop_path = start_path, stop_path

    def play_start(self) -> None:
        self._play(self._start_path)

    def play_stop(self) -> None:
        self._play(self._stop_path)

    def _play(self, path: Optional[Path]) -> None:
        if path is None:
            return
        try:
            self._play_file(path)
        except Exception as exc:  # sound is a nicety; never break dictation over it
            logger.warning("Could not play dictation sound: {}", exc)
