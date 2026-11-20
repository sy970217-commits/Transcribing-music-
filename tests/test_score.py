from fractions import Fraction

import pytest
from music21 import chord, converter, note, tempo

from transcriber.rhythm import QuantizedNote
from transcriber.score import build_score, save_musicxml

C4, E4, G4, C3 = 60, 64, 67, 48


def q(pitch, start, length=1):
    return QuantizedNote(
        pitch=pitch,
        velocity=80,
        start_beats=Fraction(start),
        duration_beats=Fraction(length),
    )


def pitches_in(part):
    found = []
    for element in part.recurse().notes:
        if isinstance(element, chord.Chord) and len(element.pitches) > 1:
            found.append(tuple(sorted(p.midi for p in element.pitches)))
        elif isinstance(element, chord.Chord):
            found.append(element.pitches[0].midi)
        elif isinstance(element, note.Note):
            found.append(element.pitch.midi)
    return found


def test_splits_notes_into_right_and_left_hand():
    score = build_score((q(C4, 0), q(C3, 0)), tempo_bpm=120)
    treble, bass = score.parts

    assert pitches_in(treble) == [C4]
    assert pitches_in(bass) == [C3]


def test_notes_at_same_time_become_a_chord():
    score = build_score((q(C4, 0), q(E4, 0), q(G4, 0)), tempo_bpm=120)

    assert pitches_in(score.parts[0]) == [(C4, E4, G4)]


def test_saved_musicxml_can_be_read_back(tmp_path):
    melody = (q(C4, 0), q(E4, 1), q(G4, 2, length=Fraction(1, 2)))
    path = save_musicxml(build_score(melody, tempo_bpm=90), tmp_path / "out" / "song.musicxml")

    loaded = converter.parse(str(path))
    marks = list(loaded.recurse().getElementsByClass(tempo.MetronomeMark))
    assert pitches_in(loaded.parts[0]) == [C4, E4, G4]
    assert marks[0].number == 90


def test_empty_notes_raise_clear_error():
    with pytest.raises(ValueError, match="음이 없습니다"):
        build_score((), tempo_bpm=120)
