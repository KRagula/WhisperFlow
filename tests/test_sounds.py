import io
import wave

import numpy as np

from whisperfree.sounds import (
    SAMPLE_RATE,
    START_NOTES,
    STOP_NOTES,
    ChimePlayer,
    chime_samples,
    chime_wav_bytes,
)


def dominant_frequency(samples):
    spectrum = np.abs(np.fft.rfft(samples))
    freqs = np.fft.rfftfreq(len(samples), 1 / SAMPLE_RATE)
    return freqs[int(np.argmax(spectrum))]


def test_start_chime_rises_and_stop_chime_falls():
    for notes, rising in ((START_NOTES, True), (STOP_NOTES, False)):
        samples = chime_samples(notes)
        half = len(samples) // 2
        first, second = dominant_frequency(samples[:half]), dominant_frequency(samples[half:])
        assert abs(first - notes[0]) < 20
        assert abs(second - notes[1]) < 20
        assert bool(second > first) is rising


def test_chime_is_short_and_not_clipped():
    samples = chime_samples(START_NOTES)
    assert 0.15 <= len(samples) / SAMPLE_RATE <= 0.35
    assert np.max(np.abs(samples)) <= 0.5
    assert abs(samples[0]) < 0.01 and abs(samples[-1]) < 0.01  # no click at either end


def test_chime_wav_bytes_is_valid_mono_pcm():
    with wave.open(io.BytesIO(chime_wav_bytes(START_NOTES)), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getsampwidth() == 2
        assert wav.getframerate() == SAMPLE_RATE
        assert wav.getnframes() == len(chime_samples(START_NOTES))


def test_player_writes_files_and_plays_them(tmp_path):
    played = []
    player = ChimePlayer(directory=tmp_path, play_file=played.append)
    player.play_start()
    player.play_stop()
    assert [p.name for p in played] == ["start.wav", "stop.wav"]
    assert all(p.exists() and p.stat().st_size > 1000 for p in played)


def test_player_survives_unwritable_directory(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("file, not a directory", encoding="utf-8")
    played = []
    player = ChimePlayer(directory=blocker / "sounds", play_file=played.append)
    player.play_start()  # must not raise
    assert played == []


def test_player_swallows_playback_errors(tmp_path):
    def boom(path):
        raise RuntimeError("audio device busy")

    ChimePlayer(directory=tmp_path, play_file=boom).play_start()  # must not raise
