from fractions import Fraction

from transcriber.rhythm import QuantizedNote
from transcriber.voices import split_voices


def q(pitch, start, length):
    return QuantizedNote(pitch=pitch, velocity=80, start_beats=Fraction(start), duration_beats=Fraction(length))


def summary(chords):
    return [(c.start, c.duration, sorted(n.pitch for n in c.notes)) for c in chords]


def test_held_note_under_moving_notes_gets_second_voice():
    # 도를 4박 누르고, 그 위로 미·솔·도가 1박씩 움직임
    notes = (q(48, 0, 4), q(64, 0, 1), q(67, 1, 1), q(72, 2, 2))

    upper, lower = split_voices(notes)

    assert summary(lower) == [(0, 4, [48])]
    assert summary(upper) == [(0, 1, [64]), (1, 1, [67]), (2, 2, [72])]


def test_held_note_alone_then_moving_notes():
    notes = (q(48, 0, 4), q(64, 1, 1), q(67, 2, 1))

    upper, lower = split_voices(notes)

    assert summary(lower) == [(0, 4, [48])]
    assert summary(upper) == [(1, 1, [64]), (2, 1, [67])]


def test_short_overlap_is_trimmed_not_split():
    # 다음 음보다 반 박만 더 울리면 그냥 끊는다(성부를 나누지 않음)
    notes = (q(60, 0, 1.5), q(64, 1, 1))

    upper, lower = split_voices(notes)

    assert lower == ()
    assert summary(upper) == [(0, 1, [60]), (1, 1, [64])]


def test_plain_chords_stay_in_one_voice():
    notes = (q(60, 0, 1), q(64, 0, 1), q(67, 1, 1), q(72, 1, 1))

    upper, lower = split_voices(notes)

    assert lower == ()
    assert summary(upper) == [(0, 1, [60, 64]), (1, 1, [67, 72])]


def test_new_held_note_cuts_previous_held_note():
    notes = (q(48, 0, 8), q(64, 0, 1), q(43, 4, 4), q(67, 4, 1), q(65, 5, 1))

    upper, lower = split_voices(notes)

    assert summary(lower) == [(0, 4, [48]), (4, 4, [43])]
