from fractions import Fraction as F

from transcriber.analysis.melody import analyze_melody, main
from transcriber.analysis.rhythm import RhythmNote, RhythmResult


def rhythm(*notes: tuple) -> RhythmResult:
    return RhythmResult(tuple(RhythmNote(p, F(s), F(l), 70) for p, s, l in notes), "4/4", F(1))


def line(result) -> list[tuple]:
    return [(n.pitch, n.start, n.length) for n in result.notes]


def test_top_note_of_chord_is_melody():
    result = analyze_melody(rhythm((60, 0, 1), (64, 0, 1), (72, 0, 1), (60, 1, 1), (74, 1, 1)))
    assert line(result) == [(72, 0, 1), (74, 1, 1)]


def test_arpeggio_under_held_melody_is_skipped():
    notes = [(79, 0, 2)] + [(55 + i, F(i, 2), F(1, 2)) for i in range(4)] + [(77, 2, 2)]
    assert line(analyze_melody(rhythm(*notes))) == [(79, 0, 2), (77, 2, 2)]


def test_overlapping_melody_note_is_cut():
    assert line(analyze_melody(rhythm((72, 0, 2), (76, 1, 1)))) == [(72, 0, 1), (76, 1, 1)]


def test_low_accompaniment_during_rest_is_skipped():
    notes = [(76, 0, 1), (77, 1, 1), (79, 2, 1), (60, 3, 1), (64, 3, 1), (76, 4, 1)]
    assert [n.pitch for n in analyze_melody(rhythm(*notes)).notes] == [76, 77, 79, 76]


def test_phrases_split_at_rest():
    result = analyze_melody(rhythm((72, 0, 1), (74, 1, 2), (76, 4, 1), (77, 5, 1)))
    assert result.phrase_starts == (0, 4)


def test_lyrics_line_starts_at_next_phrase():
    notes = [(72, 0, 1), (74, 1, 1), (76, 2, 1), (77, 4, 1), (79, 5, 1)]
    result = analyze_melody(rhythm(*notes), "나비\n날아라")
    assert [n.lyric for n in result.notes] == ["나", "비", None, "날", "아"]


def test_long_lyrics_line_spills_into_next_phrase():
    notes = [(72, 0, 1), (74, 2, 1), (76, 4, 1)]
    result = analyze_melody(rhythm(*notes), "하나둘\n셋")
    assert [n.lyric for n in result.notes] == ["하", "나", "둘"]


def test_melisma_mark_holds_previous_syllable():
    result = analyze_melody(rhythm((72, 0, 1), (74, 1, 1), (76, 2, 1)), "아- 이")
    assert [n.lyric for n in result.notes] == ["아", "", "이"]


def test_no_notes():
    assert analyze_melody(rhythm(), "가사").notes == ()


def test_cli_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err
