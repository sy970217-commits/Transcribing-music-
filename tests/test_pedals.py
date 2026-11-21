from fractions import Fraction

import pretty_midi
from music21 import expressions, note, stream

from transcriber.pedals import PedalSpan, attach_pedals, read_pedals

TEMPO = 120  # 1박 = 0.5초


def piano_with_pedal(pedal_events, length_seconds=4.0):
    midi = pretty_midi.PrettyMIDI(initial_tempo=TEMPO)
    piano = pretty_midi.Instrument(program=0)
    piano.notes.append(pretty_midi.Note(velocity=80, pitch=48, start=0, end=length_seconds))
    for time, value in pedal_events:
        piano.control_changes.append(pretty_midi.ControlChange(number=64, value=value, time=time))
    midi.instruments.append(piano)
    return midi, piano


def test_reads_pedal_down_and_up_as_beats():
    midi, piano = piano_with_pedal([(0.0, 127), (1.0, 0), (1.0, 127), (2.0, 0)])

    assert read_pedals(midi, [piano]) == (
        PedalSpan(Fraction(0), Fraction(2)),
        PedalSpan(Fraction(2), Fraction(4)),
    )


def test_pedal_still_down_at_end_lasts_to_the_end():
    midi, piano = piano_with_pedal([(0.5, 100)], length_seconds=2.0)

    assert read_pedals(midi, [piano]) == (PedalSpan(Fraction(1), Fraction(4)),)


def test_no_pedal_events_means_no_pedals():
    midi, piano = piano_with_pedal([])

    assert read_pedals(midi, [piano]) == ()


def test_attaches_pedal_marks_to_notes_in_span():
    part = stream.Part()
    for beat in range(8):
        part.insert(beat, note.Note(48 + beat))

    attached = attach_pedals(part, (PedalSpan(Fraction(0), Fraction(4)), PedalSpan(Fraction(4), Fraction(8))))

    marks = list(part.getElementsByClass(expressions.PedalMark))
    assert attached == 2
    assert [len(m.getSpannedElements()) for m in marks] == [4, 4]


def test_span_without_notes_is_skipped():
    part = stream.Part()
    part.insert(0, note.Note(48))

    assert attach_pedals(part, (PedalSpan(Fraction(4), Fraction(8)),)) == 0
