import re
from fractions import Fraction

import pretty_midi

from transcriber.chord_names import Chord
from transcriber.harmony_marks import chord_in_window, chord_window, plan_chords
from transcriber.rhythm import QuantizedNote
from transcriber.score import build_score, save_musicxml


def q(pitch, start, length=Fraction(1, 2)):
    return QuantizedNote(pitch=pitch, velocity=80, start_beats=Fraction(start), duration_beats=Fraction(length))


def broken(pitches, start):
    """8분음표로 차례로 치는 분산화음(반 마디 = 2박)"""
    return tuple(q(p, Fraction(start) + Fraction(i, 2)) for i, p in enumerate(pitches))


def test_broken_chord_is_recognised_from_notes_played_one_by_one():
    notes = broken((48, 55, 64, 67), 0)  # 도3·솔3·미4·솔4

    assert chord_in_window(notes, Fraction(0), Fraction(2)).name == "CM"


def test_short_passing_note_is_left_out_by_length():
    # 도·미·솔을 길게, 레(경과음)를 16분음표로 짧게
    notes = (q(48, 0, 2), q(64, 0, 1), q(67, 1, 1), q(62, Fraction(3, 2), Fraction(1, 4)))

    assert chord_in_window(notes, Fraction(0), Fraction(2)).name == "CM"


def test_inversion_uses_lowest_chord_tone_as_bass():
    notes = broken((52, 60, 67, 72), 0)  # 미3·도4·솔4·도5

    assert chord_in_window(notes, Fraction(0), Fraction(2)) == Chord(root=0, kind="M", bass=4)


def test_marks_only_where_the_chord_changes():
    notes = broken((48, 55, 64, 67), 0) + broken((48, 55, 64, 67), 2) + broken((45, 52, 60, 64), 4)

    marks = plan_chords(notes, Fraction(6), Fraction(2))

    assert [(m.beat, m.chord.name) for m in marks] == [(0, "CM"), (4, "Am")]


def test_window_is_half_bar_for_even_meters_and_whole_bar_otherwise():
    assert chord_window(Fraction(4)) == 2
    assert chord_window(Fraction(3)) == 3
    assert chord_window(Fraction(3, 2)) == Fraction(3, 2)


def test_chord_symbols_are_written_above_the_top_staff(tmp_path):
    melody = (q(72, 0, 4), q(69, 4, 4))
    piano = broken((48, 55, 64, 67), 0) + broken((48, 55, 64, 67), 2) + broken((45, 52, 60, 64), 4)
    path = save_musicxml(build_score(piano, tempo_bpm=90, melody=melody), tmp_path / "s.musicxml")

    melody_part = re.findall(r"<part id=.*?</part>", path.read_text(encoding="utf-8"), re.S)[0]
    harmonies = re.findall(r"<harmony.*?</harmony>", melody_part, re.S)
    assert len(harmonies) == 2
    assert "<root-step>C</root-step>" in harmonies[0] and 'text="M"' in harmonies[0]
    assert "<root-step>A</root-step>" in harmonies[1] and 'text="m"' in harmonies[1]


def test_chord_symbols_do_not_add_sound(tmp_path):
    from transcriber.render import score_to_midi

    piano = broken((48, 55, 64, 67), 0)
    path = save_musicxml(build_score(piano, tempo_bpm=120), tmp_path / "s.musicxml")
    midi = pretty_midi.PrettyMIDI(str(score_to_midi(path, tmp_path)))

    assert sum(len(i.notes) for i in midi.instruments) == 4
