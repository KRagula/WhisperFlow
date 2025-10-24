"""Audio capture utilities."""

from __future__ import annotations

import io
import threading
import wave
from typing import Callable, List, Optional

import numpy as np
import sounddevice as sd

from whisperfree.config import AppConfig
from whisperfree.utils.levels_meter import LevelSmoother, rms_level
from whisperfree.utils.logger import get_logger


logger = get_logger(__name__)


def list_microphones() -> List[str]:
    """Return a list of input-capable device names."""
    try:
        devices = sd.query_devices()
    except sd.PortAudioError as exc:
        logger.bind(error=str(exc)).warning("Failed to query audio devices.")
        return []
    except Exception as exc:  # pragma: no cover - defensive
        logger.bind(error=str(exc)).exception("Unexpected error while querying audio devices.")
        return []
    names: List[str] = []
    for device in devices:
        if device.get("max_input_channels", 0) > 0:
            names.append(device["name"])
    return names


def resolve_device(device_name: Optional[str]) -> Optional[int]:
    """Translate a device name to a sounddevice index."""
    if device_name is None:
        return None
    try:
        devices = sd.query_devices()
    except sd.PortAudioError as exc:
        logger.bind(error=str(exc)).warning("Failed to query audio devices while resolving %s", device_name)
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.bind(error=str(exc)).exception("Unexpected error while resolving audio device %s", device_name)
        return None
    for idx, device in enumerate(devices):
        if device.get("name") == device_name and device.get("max_input_channels", 0) > 0:
            return idx
    return None


LevelCallback = Callable[[float], None]
WaveformCallback = Callable[[np.ndarray, int], None]


class AudioRecorder:
    """Capture PCM audio using sounddevice."""

    def __init__(
        self,
        config: AppConfig,
        level_callback: Optional[LevelCallback] = None,
        waveform_callback: Optional[WaveformCallback] = None,
        block_duration_ms: int = 20,
        keep_last_path: Optional[str] = None,
    ) -> None:
        self._config = config
        self._level_callback = level_callback
        self._waveform_callback = waveform_callback
        self._block_duration_ms = block_duration_ms
        self._keep_last_path = keep_last_path
        self._buffer: List[np.ndarray] = []
        self._lock = threading.RLock()
        self._stream: Optional[sd.InputStream] = None
        self._frames_recorded = 0
        self._smoother = LevelSmoother()

    @property
    def gain_multiplier(self) -> float:
        """Return the linear multiplier derived from the configured gain in dB."""
        return float(10 ** (self._config.input_gain_db / 20.0))

    def start(self) -> None:
        """Begin streaming audio from the configured device."""
        with self._lock:
            if self._stream:
                logger.warning("AudioRecorder.start called while already running.")
                return
            self._buffer.clear()
            self._frames_recorded = 0

            device_index = resolve_device(self._config.mic_device_name)
            blocksize = max(int(self._config.sample_rate * self._block_duration_ms / 1000), 80)
            logger.info(
                "Starting audio stream device={} index={} sample_rate={} blocksize={}",
                self._config.mic_device_name or "default",
                device_index,
                self._config.sample_rate,
                blocksize,
            )
            try:
                self._stream = sd.InputStream(
                    device=device_index,
                    channels=1,
                    samplerate=self._config.sample_rate,
                    blocksize=blocksize,
                    dtype="int16",
                    callback=self._callback,
                )
                self._stream.start()
            except Exception as exc:  # pragma: no cover - runtime safeguard
                logger.bind(error=str(exc)).exception("Failed to start audio stream")
                self._stream = None
                raise

    def stop(self) -> None:
        """Stop streaming and close resources."""
        with self._lock:
            if not self._stream:
                return
            try:
                self._stream.stop()
            finally:
                self._stream.close()
                self._stream = None
            logger.info("Audio stream stopped after %s frames", self._frames_recorded)

    def reset(self) -> None:
        """Clear buffered audio without stopping the stream."""
        with self._lock:
            self._buffer.clear()
            self._frames_recorded = 0

    def _callback(self, indata, frames, time_info, status) -> None:
        if status:
            logger.warning("Audio stream status: %s", status)
        frame = indata.copy()
        if self.gain_multiplier != 1.0:
            frame = np.clip(frame * self.gain_multiplier, -32768, 32767).astype(np.int16)
        with self._lock:
            self._buffer.append(frame)
            self._frames_recorded += frames
        if self._level_callback:
            level = self._smoother.push(rms_level(frame.tobytes()))
            self._level_callback(level)
        if self._waveform_callback:
            waveform = frame.astype(np.float32).reshape(-1) / 32768.0
            self._waveform_callback(waveform, self._config.sample_rate)

    def get_wav_bytes(self) -> bytes:
        """Return the captured audio as a WAV byte sequence."""
        with self._lock:
            if not self._buffer:
                return b""
            data = np.concatenate(self._buffer)
        wav_buffer = io.BytesIO()
        with wave.open(wav_buffer, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(self._config.sample_rate)
            wav_file.writeframes(data.tobytes())
        payload = wav_buffer.getvalue()
        if self._keep_last_path:
            try:
                with open(self._keep_last_path, "wb") as fh:
                    fh.write(payload)
            except OSError:
                logger.exception("Unable to write debug audio to %s", self._keep_last_path)
        return payload
