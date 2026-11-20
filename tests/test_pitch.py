import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from transcriber.audio_io import AudioLoadError
from transcriber.pitch import detect_notes, save_midi

SAMPLE_RATE = 22050
A4_MIDI = 69  # 라 음
C5_MIDI = 72  # 높은 도 음


def midi_to_hz(midi_number):
    return 440.0 * 2 ** ((midi_number - A4_MIDI) / 12)


def write_melody_wav(path, midi_numbers, seconds_each=0.5):
    t = np.linspace(0, seconds_each, int(SAMPLE_RATE * seconds_each), endpoint=False)
    tones = [0.5 * np.sin(2 * np.pi * midi_to_hz(n) * t) for n in midi_numbers]
    sf.write(path, np.concatenate(tones), SAMPLE_RATE)
    return path


@pytest.fixture(scope="module")
def melody_result(tmp_path_factory):
    wav = tmp_path_factory.mktemp("audio") / "melody.wav"
    return detect_notes(write_melody_wav(wav, [A4_MIDI, C5_MIDI]))


def test_detects_notes_in_order(melody_result):
    pitches = [note.pitch for note in melody_result.notes]

    assert pitches == [A4_MIDI, C5_MIDI]


def test_note_timing_matches_melody(melody_result):
    first, second = melody_result.notes

    assert first.start_seconds == pytest.approx(0.0, abs=0.1)
    assert second.start_seconds == pytest.approx(0.5, abs=0.1)


def test_saves_readable_midi_file(melody_result, tmp_path):
    midi_path = save_midi(melody_result, tmp_path / "out" / "melody.mid")

    loaded = pretty_midi.PrettyMIDI(str(midi_path))
    saved_pitches = sorted(n.pitch for inst in loaded.instruments for n in inst.notes)
    assert saved_pitches == [A4_MIDI, C5_MIDI]


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(AudioLoadError, match="찾을 수 없습니다"):
        detect_notes(tmp_path / "nope.wav")
