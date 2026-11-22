from dataclasses import replace
from fractions import Fraction

from music21 import expressions, key

from test_analysis_sheet import small_sheet
from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.melody import MelodyNote, MelodyResult
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.analysis.tonality import KeySegment
from transcriber.sheet_score import key_name_of, pickup_shift, score_from_sheet


def test_piano_score_uses_sheet_key_and_pedal():
    score = score_from_sheet(replace(small_sheet(), melody=MelodyResult((), ())))
    assert len(score.parts) == 2  # 가사가 없으면 피아노 두 단만
    assert score.parts[0].recurse().getElementsByClass(key.Key).first().sharps == 0
    assert score.recurse().getElementsByClass(expressions.PedalMark)


def test_lyrics_add_melody_staff():
    score = score_from_sheet(small_sheet())
    assert len(score.parts) == 3
    assert score.parts[0].recurse().notes.first().lyric == "아"


def test_key_names():
    assert key_name_of(KeySegment(Fraction(0), Fraction(4), 10, "major")) == "B-"
    assert key_name_of(KeySegment(Fraction(0), Fraction(4), 1, "minor")) == "c#"


def test_pickup_moves_notes_to_end_of_first_bar():
    beats = BeatAnalysis((0.0, 0.5), (0.5,), "4/4", 4, 2, 120.0, 1)
    sheet = replace(small_sheet(), beats=beats)
    assert pickup_shift(sheet) == 3
    first = score_from_sheet(replace(sheet, melody=MelodyResult((MelodyNote(60, Fraction(0), Fraction(1)),), ())))
    assert first.parts[0].recurse().notes.first().getOffsetInHierarchy(first.parts[0]) == 3


def test_separated_voice_is_not_repeated_in_piano_staff():
    backing = RhythmResult((RhythmNote(48, Fraction(0), Fraction(2), 60),), "4/4", Fraction(1))
    score = score_from_sheet(replace(small_sheet(), accompaniment=backing))
    piano_pitches = [p.midi for part in score.parts[1:] for n in part.recurse().notes for p in n.pitches]
    assert piano_pitches == [48]  # 멜로디 단의 60은 피아노 단에 다시 적지 않는다


def test_without_melody_staff_piano_keeps_all_notes():
    backing = RhythmResult((), "4/4", Fraction(1))
    sheet = replace(small_sheet(), accompaniment=backing, melody=MelodyResult((), ()))
    score = score_from_sheet(sheet)
    assert [p.midi for n in score.recurse().notes for p in n.pitches] == [60]


def test_separated_voice_gets_melody_staff_without_lyrics():
    backing = RhythmResult((RhythmNote(48, Fraction(0), Fraction(2), 60),), "4/4", Fraction(1))
    tune = MelodyResult((MelodyNote(67, Fraction(0), Fraction(1)),), ())
    score = score_from_sheet(replace(small_sheet(), accompaniment=backing, melody=tune))
    assert len(score.parts) == 3
    assert score.parts[0].recurse().notes.first().pitch.midi == 67
    assert score.parts[0].recurse().notes.first().lyric is None
