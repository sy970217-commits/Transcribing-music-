from fractions import Fraction

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.analysis.structure import analyze_structure, group_phrases, main

BEATS = BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.0,), time_signature="4/4", beats_per_bar=4,
                     pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=0)
# 4마디 구절: 마디마다 (베이스, 선율 4음)
X = [(48, (72, 74, 76, 77)), (45, (76, 74, 72, 71)), (41, (69, 72, 77, 76)), (43, (74, 71, 67, 71))]
Y = [(41, (77, 76, 74, 72)), (43, (71, 74, 79, 77)), (48, (76, 79, 84, 79)), (48, (72, 72, 72, 72))]
Z = [(45, (81, 79, 77, 76)), (50, (77, 74, 77, 81)), (43, (79, 77, 74, 71)), (43, (67, 71, 74, 77))]
W = [(41, (84, 81, 77, 72)), (40, (71, 68, 64, 68)), (45, (69, 72, 76, 81)), (45, (81, 76, 72, 69))]
# Y와 코드는 같고 선율만 다른 구절
Y2 = [(bass, tuple(p - 5 for p in melody[::-1])) for bass, melody in Y]


def song(phrases):
    notes = []
    for bar, (bass, melody) in enumerate(b for phrase in phrases for b in phrase):
        notes.append(RhythmNote(bass, Fraction(bar * 4), Fraction(4), 90))
        notes += [RhythmNote(bass + 12, Fraction(bar * 4 + i), Fraction(1), 70) for i in range(4)]
        notes += [RhythmNote(p, Fraction(bar * 4 + i), Fraction(1), 80) for i, p in enumerate(melody)]
    return RhythmResult(tuple(sorted(notes, key=lambda n: (n.start, n.pitch))), "4/4", Fraction(1))


def form(phrases):
    return [(s.start, s.end, s.label) for s in analyze_structure(song(phrases), BEATS).sections]


def test_aaba_with_eight_bar_sections():
    assert form([X, Y, X, Y, Z, W, X, Y]) == [(0, 32, "A"), (32, 64, "A"), (64, 96, "B"), (96, 128, "A")]


def test_verse_chorus_alternating():
    assert [s[2] for s in form([X, Y, Z, W, X, Y, Z, W])] == ["A", "B", "A", "B"]


def test_intro_and_outro_are_separate():
    assert [s[2] for s in form([W, X, Y, X, Y, Z])] == ["A", "B", "B", "C"]


def test_same_chords_different_melody_is_different_part():
    assert [s[2] for s in form([X, Y, X, Y2])] == ["A", "B", "A", "C"]


def test_same_phrase_over_and_over():
    assert [s[2] for s in form([X, X, X])] == ["A", "A", "A"]


def test_group_phrases_merges_unique_run():
    assert group_phrases([0, 1, 0, 1, 2, 3, 0, 1]) == [(0, 1), (0, 1), (2, 3), (0, 1)]


def test_no_notes_gives_no_sections():
    assert analyze_structure(RhythmResult((), "4/4", Fraction(1)), BEATS).sections == ()


def test_cli_reports_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_pickup_bar_does_not_hide_first_phrase():
    beats = BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.5,), time_signature="4/4", beats_per_bar=4,
                         pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=1)
    base = song([X, X, Y, X])
    notes = (RhythmNote(67, Fraction(0), Fraction(1), 80),) + tuple(
        RhythmNote(n.pitch, n.start + 1, n.length, n.velocity) for n in base.notes)
    sections = analyze_structure(RhythmResult(notes, "4/4", Fraction(1)), beats).sections
    assert [(s.start, s.label) for s in sections] == [(0, "A"), (17, "A"), (33, "B"), (49, "A")]


def test_short_tail_joins_last_bar():
    base = song([X, Y, X, Y])
    tail = RhythmNote(36, Fraction(64) + Fraction(1, 2), Fraction(1, 4), 30)
    sections = analyze_structure(RhythmResult(base.notes + (tail,), "4/4", Fraction(1)), BEATS).sections
    assert [s.label for s in sections] == ["A", "A"] and sections[-1].end == Fraction(259, 4)
