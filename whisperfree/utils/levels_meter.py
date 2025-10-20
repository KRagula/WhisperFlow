"""Audio level metering helpers."""

from __future__ import annotations

from collections import deque
from typing import Deque, Iterable

import numpy as np


def rms_level(frame: bytes, dtype: np.dtype = np.int16) -> float:
    """Return root-mean-square amplitude in linear scale."""
    if not frame:
        return 0.0
    samples = np.frombuffer(frame, dtype=dtype).astype(np.float32)
    if samples.size == 0:
        return 0.0
    rms = np.sqrt(np.mean(np.square(samples)))
    max_val = np.iinfo(dtype).max
    return float(rms / max_val)


class LevelSmoother:
    """Smooth RMS levels for responsive UI animation."""

    def __init__(self, window: int = 6) -> None:
        self._values: Deque[float] = deque(maxlen=window)

    def push(self, value: float) -> float:
        """Add a new sample and return the smoothed value."""
        self._values.append(value)
        if not self._values:
            return 0.0
        arr = np.array(self._values, dtype=np.float32)
        return float(np.mean(arr))

    def bulk_push(self, iterable: Iterable[float]) -> float:
        """Push multiple samples and return the latest smoothed level."""
        smoothed = 0.0
        for value in iterable:
            smoothed = self.push(value)
        return smoothed
