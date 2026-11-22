from dataclasses import replace
from fractions import Fraction

from music21 import expressions, key

from test_analysis_sheet import small_sheet
from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.melody import MelodyNote, MelodyResult
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
