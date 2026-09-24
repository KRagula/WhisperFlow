from types import SimpleNamespace

from whisperfree.app import WhisperFreeController
from whisperfree.config import AppConfig


class _Signal:
    def __init__(self):
        self.calls = []

    def emit(self, *args):
        self.calls.append(args)


class _Chimes:
    def __init__(self):
        self.played = []

    def play_start(self):
        self.played.append("start")

    def play_stop(self):
        self.played.append("stop")


class _Audio:
    def __init__(self, fail_start=False, wav=b""):
        self.fail_start = fail_start
        self.wav = wav
        self.last_duration = 1.0

    def start(self):
        if self.fail_start:
            raise OSError("no microphone")

    def stop(self):
        pass

    def get_wav_bytes(self):
        return self.wav


def _controller(sound_enabled=True, audio=None):
    return SimpleNamespace(
        _config=AppConfig(sound_enabled=sound_enabled),
        _audio=audio or _Audio(),
        _chimes=_Chimes(),
        _executor=SimpleNamespace(submit=lambda *a, **k: None),
        _process_session=lambda *a, **k: None,
        toast_requested=_Signal(),
        recording_requested=_Signal(),
        idle_requested=_Signal(),
    )


def test_press_and_release_play_start_then_stop():
    fake = _controller(audio=_Audio(wav=b"RIFF"))
    WhisperFreeController._handle_push_to_talk_start(fake)
    WhisperFreeController._handle_push_to_talk_stop(fake)
    assert fake._chimes.played == ["start", "stop"]


def test_release_chime_plays_even_when_nothing_was_recorded():
    fake = _controller(audio=_Audio(wav=b""))
    WhisperFreeController._handle_push_to_talk_start(fake)
    WhisperFreeController._handle_push_to_talk_stop(fake)
    assert fake._chimes.played == ["start", "stop"]


def test_no_sounds_when_disabled():
    fake = _controller(sound_enabled=False, audio=_Audio(wav=b"RIFF"))
    WhisperFreeController._handle_push_to_talk_start(fake)
    WhisperFreeController._handle_push_to_talk_stop(fake)
    assert fake._chimes.played == []


def test_no_start_chime_when_microphone_fails():
    fake = _controller(audio=_Audio(fail_start=True))
    WhisperFreeController._handle_push_to_talk_start(fake)
    assert fake._chimes.played == []
    assert fake.toast_requested.calls == [("Audio input error", 2500)]


def test_sound_enabled_defaults_on_for_old_configs():
    assert AppConfig.from_dict({"overlay_enabled": False}).sound_enabled is True
