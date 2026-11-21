import csv
from fractions import Fraction

import pretty_midi

from transcriber.rhythm import QuantizedNote
from transcriber.rhythm_stats import beat_patterns, count_patterns, main


def q(start, length, pitch=60):
    return QuantizedNote(pitch=pitch, velocity=80, start_beats=Fraction(start), duration_beats=Fraction(length))


def test_sixteenths_rests_and_ties_in_one_beat():
    # 1박: 8분음표 + 16분쉼표 + 16분음표가 다음 박까지 이어짐 / 2박: 이어진 음 뒤 쉼
    notes = (q(0, Fraction(1, 2)), q(Fraction(3, 4), Fraction(1, 2)))

    assert beat_patterns(notes) == ["ㅇㅡㅅㅇ", "ㅡㅅㅅㅅ"]


def test_triplets_use_three_slots_and_mixed_beats_use_twelve():
    triplet = tuple(q(Fraction(i, 3), Fraction(1, 3)) for i in range(3))
    mixed = (q(1, Fraction(1, 3)), q(Fraction(3, 2), Fraction(1, 2)))

    assert beat_patterns(triplet + mixed) == ["ㅇㅇㅇ", "ㅇㅡㅡㅡㅅㅅㅇㅡㅡㅡㅡㅡ"]


def test_chord_counts_as_one_line_and_patterns_are_counted():
    chord = (q(0, 1, 60), q(0, 1, 64), q(1, 1, 60))

    assert count_patterns(chord) == {"ㅇㅡㅡㅡ": 2}


def test_cli_writes_csv_with_sheet_row(tmp_path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    piano.notes += [pretty_midi.Note(velocity=80, pitch=60, start=i * 0.5, end=i * 0.5 + 0.5) for i in range(4)]
    midi.instruments.append(piano)
    path = tmp_path / "song.mid"
    midi.write(str(path))

    assert main([str(path), "--output-dir", str(tmp_path)]) == 0

    rows = list(csv.DictReader((tmp_path / "song_리듬패턴.csv").open(encoding="utf-8-sig")))
    assert rows == [{"파트": "피아노", "칸수": "4", "패턴": "ㅇㅡㅡㅡ", "시트_행": "54", "횟수": "4"}]
