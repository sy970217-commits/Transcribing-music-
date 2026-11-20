import numpy as np
import pytest
import soundfile as sf

from transcriber.audio_io import AudioLoadError, load_audio

ORIGINAL_RATE = 44100
TARGET_RATE = 22050


def write_sine_wav(path, seconds=1.0, channels=1):
    t = np.linspace(0, seconds, int(ORIGINAL_RATE * seconds), endpoint=False)
    tone = 0.5 * np.sin(2 * np.pi * 440 * t)  # 라(A4) 음
    data = np.column_stack([tone] * channels) if channels > 1 else tone
    sf.write(path, data, ORIGINAL_RATE)
    return path


def test_loads_wav_and_resamples(tmp_path):
    audio = load_audio(write_sine_wav(tmp_path / "a4.wav"), sample_rate=TARGET_RATE)

    assert audio.sample_rate == TARGET_RATE
    assert audio.duration_seconds == pytest.approx(1.0, abs=0.01)


def test_converts_stereo_to_mono(tmp_path):
    audio = load_audio(write_sine_wav(tmp_path / "stereo.wav", channels=2))

    assert audio.samples.ndim == 1


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(AudioLoadError, match="찾을 수 없습니다"):
        load_audio(tmp_path / "nope.wav")


def test_unsupported_extension_raises_clear_error(tmp_path):
    text_file = tmp_path / "notes.txt"
    text_file.write_text("not audio")

    with pytest.raises(AudioLoadError, match="지원하지 않는 형식"):
        load_audio(text_file)


def test_broken_audio_file_raises_clear_error(tmp_path):
    broken = tmp_path / "broken.wav"
    broken.write_bytes(b"not really a wav")

    with pytest.raises(AudioLoadError, match="읽을 수 없습니다"):
        load_audio(broken)
