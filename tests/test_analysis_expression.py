from fractions import Fraction

import numpy as np

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.expression import (
    NoteSound, analyze_expression, bar_marks, decay_check_time, main, measure_sounds,
)
from transcriber.analysis.harmony import ChordSegment, HarmonyResult
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.pitch import Note

BEATS = BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.0,), time_signature="4/4", beats_per_bar=4,
                     pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=0)


def rhythm(bars: int) -> RhythmResult:
    return RhythmResult(tuple(RhythmNote(60, Fraction(b * 4), Fraction(4), 70) for b in range(bars)), "4/4", Fraction(1))


def per_bar(bars: int) -> HarmonyResult:
    return HarmonyResult(tuple(ChordSegment(Fraction(b * 4), Fraction(b * 4 + 4), None) for b in range(bars)))


def sounds(velocities: list[float], decays: list[float | None]) -> tuple[NoteSound, ...]:
    """마디마다 8분음표 8개의 소리."""
    return tuple(NoteSound(bar * 4 + i / 2, v, d) for bar, (v, d) in enumerate(zip(velocities, decays)) for i in range(8))


def test_levels_from_loudness():
    result = analyze_expression(rhythm(4), per_bar(4), BEATS, sounds([48, 48, 92, 92], [None] * 4))
    assert [(s.start, s.end, s.mark) for s in result.dynamics] == [(0, 8, "p"), (8, 16, "f")]


def test_crescendo_and_diminuendo():
    assert bar_marks([48, 48, 60, 72, 84, 92, 92, 80, 68, 50]) == ["p", "p", "<", "<", "<", "f", "f", ">", ">", ">"]


def test_one_odd_bar_follows_neighbour():
    assert bar_marks([48, 48, 92, 48, 48]) == ["p"] * 5


def test_small_wobble_keeps_level():
    assert bar_marks([72, 67, 67, 75]) == ["mf"] * 4


def test_empty_bar_keeps_previous_loudness():
    assert bar_marks([92, None, 92]) == ["f", "f", "f"]


def test_pedal_when_notes_keep_ringing():
    result = analyze_expression(rhythm(3), per_bar(3), BEATS, sounds([70] * 3, [-12, -35, -15]))
    assert [(p.start, p.end) for p in result.pedals] == [(0, 4), (8, 12)]


def test_no_pedal_when_ringing_cannot_be_measured():
    assert analyze_expression(rhythm(1), per_bar(1), BEATS, sounds([70], [None])).pedals == ()


def test_decay_checked_just_before_second_next_note():
    notes = (Note(0.0, 0.3, 60, 80), Note(0.3, 0.6, 64, 80), Note(0.6, 0.9, 67, 80))
    assert abs(decay_check_time(notes[0], np.array([0.0, 0.3, 0.6]), notes) - 0.57) < 1e-9


def test_decay_not_checked_for_held_or_struck_again_note():
    held = (Note(0.0, 1.0, 60, 80), Note(0.3, 0.6, 64, 80), Note(0.6, 0.9, 67, 80))
    again = (Note(0.0, 0.3, 72, 80), Note(0.3, 0.6, 60, 80), Note(0.6, 0.9, 67, 80))
    onsets = np.array([0.0, 0.3, 0.6])
    assert decay_check_time(held[0], onsets, held) is None
    assert decay_check_time(again[0], onsets, again) is None  # 옥타브 아래 음을 쳐 배음이 겹친다


def test_measure_sounds_louder_note_gets_higher_velocity(tmp_path):
    import soundfile

    rate = 22050
    t = np.arange(rate) / rate
    tone = np.sin(2 * np.pi * 261.63 * t) * np.exp(-3 * t)
    soundfile.write(tmp_path / "two.wav", np.concatenate([0.05 * tone, 0.5 * tone]), rate)
    notes = (Note(0.0, 0.2, 60, 80), Note(1.0, 1.2, 60, 80))
    quiet, loud = measure_sounds(tmp_path / "two.wav", notes, BEATS)
    assert loud.velocity - quiet.velocity > 50
    assert quiet.position == 0.0 and loud.position == 2.0


def test_no_notes():
    result = analyze_expression(RhythmResult((), "4/4", Fraction(1)), HarmonyResult(()), BEATS, ())
    assert result.dynamics == () and result.pedals == ()


def test_cli_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err
