import numpy as np

from whisperfree.audio import AudioRecorder
from whisperfree.config import AppConfig


def test_last_duration_counts_captured_frames():
    recorder = AudioRecorder(AppConfig(sample_rate=16000))
    assert recorder.last_duration == 0.0
    block = np.zeros((1600, 1), dtype=np.int16)
    recorder._callback(block, 1600, None, None)
    recorder._callback(block, 1600, None, None)
    assert recorder.last_duration == 0.2
