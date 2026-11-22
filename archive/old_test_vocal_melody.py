"""(보관) 예전 vocal_melody 테스트. 파일 이름이 test_로 시작하지 않아 pytest가 돌리지 않는다."""

import numpy as np
import soundfile as sf

from transcriber import vocal_melody
from transcriber.pitch import Note
from transcriber.vocal_melody import extract_vocal_parts, has_voice

SAMPLE_RATE = 22050
A4_MIDI, C5_MIDI = 69, 72


def n(start, end, pitch, velocity=80):
    return Note(start_seconds=start, end_seconds=end, pitch=pitch, velocity=velocity)


def test_detects_voice_by_relative_energy():
    mix = np.ones(1000)

    assert has_voice(np.full(1000, 0.5), mix, window=100)
    assert not has_voice(np.full(1000, 0.001), mix, window=100)
    assert not has_voice(np.zeros(1000), np.zeros(1000), window=100)


def test_one_loud_glitch_is_not_a_voice():
    # 가을꽃.wav에서 실제로 본 경우: 10구간 중 1구간만 크게 튐
    vocals = np.zeros(1000)
    vocals[300:400] = 0.8

    assert not has_voice(vocals, np.ones(1000), window=100)


def write_melody(path, midi_numbers, volume=0.5, seconds_each=0.5):
    t = np.linspace(0, seconds_each, int(SAMPLE_RATE * seconds_each), endpoint=False)
    tones = [volume * np.sin(2 * np.pi * 440 * 2 ** ((m - A4_MIDI) / 12) * t) for m in midi_numbers]
    sf.write(path, np.concatenate(tones), SAMPLE_RATE)
    return path


def fake_separation(vocal_volume):
    """Demucs 대신: 원본과 같은 멜로디를 지정한 크기로 '목소리'로 돌려준다."""

    def separate(audio_path, work_dir):
        work_dir.mkdir(parents=True, exist_ok=True)
        vocals = write_melody(work_dir / "vocals.wav", [A4_MIDI, C5_MIDI], volume=vocal_volume)
        rest = write_melody(work_dir / "no_vocals.wav", [48], volume=0.3, seconds_each=1.0)
        return vocals, rest

    return separate


def test_extracts_melody_from_separated_voice(tmp_path, monkeypatch):
    monkeypatch.setattr(vocal_melody, "separate_stems", fake_separation(vocal_volume=0.5))
    song = write_melody(tmp_path / "song.wav", [A4_MIDI, C5_MIDI])

    parts = extract_vocal_parts(song, tmp_path / "stems")

    assert parts.has_voice
    assert [x.pitch for x in parts.melody] == [A4_MIDI, C5_MIDI]
    assert parts.accompaniment_path.name == "no_vocals.wav"


def test_no_melody_when_voice_is_missing(tmp_path, monkeypatch):
    monkeypatch.setattr(vocal_melody, "separate_stems", fake_separation(vocal_volume=0.001))
    song = write_melody(tmp_path / "song.wav", [A4_MIDI, C5_MIDI])

    parts = extract_vocal_parts(song, tmp_path / "stems")

    assert not parts.has_voice
    assert parts.melody == ()
    assert parts.accompaniment_path == song
