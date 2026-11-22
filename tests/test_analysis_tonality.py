from fractions import Fraction

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.harmony import analyze_harmony
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.analysis.tonality import KeySegment, analyze_key, main

BEATS = BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.0,), time_signature="4/4", beats_per_bar=4,
                     pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=0)
C, AM, F, G7 = (48, (60, 64, 67)), (45, (60, 64, 69)), (41, (60, 65, 69)), (43, (59, 62, 65))
DM, E7, D7, G = (50, (62, 65, 69)), (40, (59, 62, 68)), (50, (60, 62, 66)), (43, (59, 62, 67))


def song(chords):
    """한 마디에 코드 하나: 베이스 온음표 + 박마다 화음."""
    notes = []
    for bar, (bass, tones) in enumerate(chords):
        notes.append(RhythmNote(bass, Fraction(bar * 4), Fraction(4), 90))
        notes += [RhythmNote(p, Fraction(bar * 4 + b), Fraction(1), 70) for b in range(4) for p in tones]
    return RhythmResult(tuple(sorted(notes, key=lambda n: (n.start, n.pitch))), "4/4", Fraction(1))


def keys(chords):
    rhythm = song(chords)
    return [(k.start, k.name) for k in analyze_key(rhythm, analyze_harmony(rhythm, BEATS), BEATS).keys]


def test_major_song():
    assert keys([C, AM, F, G7, C]) == [(0, "C major")]


def test_minor_song_with_leading_tone():
    assert keys([AM, DM, E7, AM, F, DM, E7, AM]) == [(0, "A minor")]


def test_key_change_after_several_bars():
    assert keys([C, AM, F, G7, C, F, G7, C, AM, D7, G, D7, G, D7, G, G]) == [(0, "C major"), (32, "G major")]


def test_key_signatures():
    assert KeySegment(0, 4, 3, "major").name == "Eb major"
    assert KeySegment(0, 4, 3, "major").sharps == -3
    assert KeySegment(0, 4, 9, "minor").sharps == 0
    assert KeySegment(0, 4, 4, "minor").sharps == 1


def test_no_notes_gives_no_keys():
    assert analyze_key(RhythmResult((), "4/4", Fraction(1)), analyze_harmony(RhythmResult((), "4/4", Fraction(1)), BEATS), BEATS).keys == ()


def test_cli_reports_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err
