from fractions import Fraction

import numpy as np
import pytest
import soundfile as sf

from transcriber.pitch import Note
from transcriber.rhythm import DEFAULT_TEMPO_BPM, estimate_tempo, quantize_notes

SAMPLE_RATE = 22050
TEMPO_120 = 120.0  # 1박 = 0.5초


def make_note(start, end, pitch=60):
    return Note(start_seconds=start, end_seconds=end, pitch=pitch, velocity=80)


def test_snaps_slightly_off_notes_to_beats():
    notes = (make_note(0.02, 0.49), make_note(0.51, 1.03, pitch=62))

    result = quantize_notes(notes, TEMPO_120)

    assert [n.start_beats for n in result] == [Fraction(0), Fraction(1)]
    assert [n.duration_beats for n in result] == [Fraction(1), Fraction(1)]


def test_eighth_note_length_is_half_beat():
    result = quantize_notes((make_note(0.0, 0.26),), TEMPO_120)

    assert result[0].duration_beats == Fraction(1, 2)


def test_very_short_note_keeps_smallest_length():
    result = quantize_notes((make_note(0.0, 0.01),), TEMPO_120)

    assert result[0].duration_beats == Fraction(1, 4)


def test_result_is_sorted_by_start_time():
    notes = (make_note(1.0, 1.5, pitch=64), make_note(0.0, 0.5, pitch=60))

    result = quantize_notes(notes, TEMPO_120)

    assert [n.pitch for n in result] == [60, 64]


def test_triplet_eighths_snap_to_thirds_of_a_beat():
    # 120 BPM에서 1박 = 0.5초, 셋잇단음표 간격 = 1/6초
    third = 0.5 / 3
    notes = tuple(make_note(i * third + 0.005, (i + 1) * third, pitch=60 + i) for i in range(3))

    result = quantize_notes(notes, TEMPO_120)

    assert [n.start_beats for n in result] == [0, Fraction(1, 3), Fraction(2, 3)]
    assert all(n.duration_beats == Fraction(1, 3) for n in result)


def test_sixteenths_stay_sixteenths():
    quarter_of_beat = 0.5 / 4
    notes = tuple(make_note(i * quarter_of_beat, (i + 1) * quarter_of_beat, pitch=60 + i) for i in range(4))

    result = quantize_notes(notes, TEMPO_120)

    assert [n.start_beats for n in result] == [0, Fraction(1, 4), Fraction(1, 2), Fraction(3, 4)]


def test_triplets_and_sixteenths_in_different_beats():
    third, sixteenth = 0.5 / 3, 0.5 / 4
    triplets = tuple(make_note(i * third, (i + 1) * third) for i in range(3))
    sixteenths = tuple(make_note(0.5 + i * sixteenth, 0.5 + (i + 1) * sixteenth) for i in range(4))

    starts = [n.start_beats for n in quantize_notes(triplets + sixteenths, TEMPO_120)]

    assert starts == [0, Fraction(1, 3), Fraction(2, 3), 1, Fraction(5, 4), Fraction(3, 2), Fraction(7, 4)]


def test_rejects_zero_tempo():
    with pytest.raises(ValueError, match="템포"):
        quantize_notes((make_note(0.0, 0.5),), 0)


def write_click_track(path, bpm, seconds=8.0):
    audio = np.zeros(int(SAMPLE_RATE * seconds))
    click = np.hanning(200)
    for beat_time in np.arange(0, seconds, 60.0 / bpm):
        start = int(beat_time * SAMPLE_RATE)
        audio[start:start + len(click)] += click
    sf.write(path, audio, SAMPLE_RATE)
    return path


def test_estimates_tempo_of_click_track(tmp_path):
    bpm = estimate_tempo(write_click_track(tmp_path / "clicks.wav", TEMPO_120))

    assert bpm == pytest.approx(TEMPO_120, rel=0.05)


def test_silence_falls_back_to_default_tempo(tmp_path):
    silent = tmp_path / "silence.wav"
    sf.write(silent, np.zeros(SAMPLE_RATE * 2), SAMPLE_RATE)

    assert estimate_tempo(silent) == DEFAULT_TEMPO_BPM
