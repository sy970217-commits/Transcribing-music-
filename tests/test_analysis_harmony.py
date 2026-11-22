from fractions import Fraction

import pytest

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.harmony import analyze_harmony, best_path, change_cost, main
from transcriber.analysis.rhythm import RhythmNote, RhythmResult


def beats(per_bar=4, pickup=0):
    return BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.0,), time_signature=f"{per_bar}/4",
                        beats_per_bar=per_bar, pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=pickup)


def block(bass, tones, start, length, step=1):
    """bass를 length 동안 누르고, 위 음들은 step마다 다시 누른다."""
    notes = [RhythmNote(bass, Fraction(start), Fraction(length), 80)]
    for beat in range(0, length, step):
        notes += [RhythmNote(p, Fraction(start + beat), Fraction(step), 70) for p in tones]
    return notes


def names(notes, **kwargs):
    rhythm = RhythmResult(tuple(sorted(notes, key=lambda n: (n.start, n.pitch))), "4/4", Fraction(1))
    return [(c.start, c.name) for c in analyze_harmony(rhythm, beats(**kwargs)).chords]


def test_one_chord_per_bar():
    notes = block(48, (60, 64, 67), 0, 4) + block(45, (60, 64, 69), 4, 4) + block(43, (59, 62, 65), 8, 4)

    assert names(notes) == [(0, "CM"), (4, "Am"), (8, "G7")]


def test_short_passing_note_does_not_change_the_chord():
    notes = block(48, (60, 64, 67), 0, 4) + [RhythmNote(81, Fraction(3, 2), Fraction(1, 2), 70)]

    assert names(notes) == [(0, "CM")]


def test_two_chords_in_a_bar_and_an_inversion():
    notes = block(50, (62, 65, 69), 0, 2) + block(41, (62, 65, 69), 2, 2)

    assert names(notes) == [(0, "Dm"), (2, "Dm/F")]


def test_triad_wins_over_seventh_when_the_seventh_is_missing():
    assert names(block(43, (55, 59, 62), 0, 4)) == [(0, "GM")]


def test_pickup_with_one_note_has_no_chord():
    notes = [RhythmNote(67, Fraction(0), Fraction(1), 80)] + block(48, (60, 64, 67), 1, 4)

    assert names(notes, pickup=1) == [(0, "N"), (1, "CM")]


def test_no_notes_gives_no_chords():
    assert analyze_harmony(RhythmResult((), "4/4", Fraction(1)), beats()).chords == ()


def test_changing_on_a_bar_line_is_cheapest():
    assert change_cost(4, 4, 0) < change_cost(2, 4, 0) < change_cost(1, 4, 0)
    assert change_cost(1, 4, 1) == change_cost(5, 4, 1)  # 못갖춘마디 다음 첫 박


def test_best_path_ignores_a_single_odd_beat():
    scores = [[1.0, 0.0], [1.0, 0.0], [0.0, 0.5], [1.0, 0.0]]

    assert best_path(__import__("numpy").array(scores), [0, 0.8, 0.8, 0.8]) == [0, 0, 0, 0]


def test_cli_reports_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_two_beat_bar_is_not_split_in_half():
    assert change_cost(1, 2, 0) == change_cost(1, 3, 0)
