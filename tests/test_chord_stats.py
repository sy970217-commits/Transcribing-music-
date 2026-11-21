import csv
from fractions import Fraction

import pretty_midi

from transcriber.chord_stats import count_sets, main, sounding_sets
from transcriber.rhythm import QuantizedNote


def q(pitch, start, length):
    return QuantizedNote(pitch=pitch, velocity=80, start_beats=Fraction(start), duration_beats=Fraction(length))


def test_each_onset_takes_everything_still_sounding():
    # 낮은 도(48)를 2박 누른 채 미(64)·솔(67)이 차례로 들어옴
    notes = (q(48, 0, 2), q(64, 0, 1), q(67, 1, 1))

    assert sounding_sets(notes) == [(48, 64), (48, 67)]


def test_sets_are_counted_in_both_forms():
    chord = (q(48, 0, 1), q(64, 0, 1), q(67, 0, 1), q(60, 1, 1), q(64, 1, 1), q(67, 1, 1))

    assert count_sets(chord) == {((0, 16, 19), (0, 4, 7), 0, 30, "CM"): 1, ((0, 4, 7), (0, 4, 7), 0, 30, "CM"): 1}


def test_cli_writes_csv_with_sheet_column(tmp_path):
    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    for beat in range(2):  # 도·미·솔 화음 두 번
        piano.notes += [pretty_midi.Note(velocity=80, pitch=p, start=beat * 0.5, end=beat * 0.5 + 0.5) for p in (60, 64, 67)]
    midi.instruments.append(piano)
    path = tmp_path / "song.mid"
    midi.write(str(path))

    assert main([str(path), "--output-dir", str(tmp_path)]) == 0

    rows = list(csv.DictReader((tmp_path / "song_음높이묶음.csv").open(encoding="utf-8-sig")))
    # (0,4,7): 둘째 음이 1·2·3인 묶음(10+9+8=27개) 다음, (0,4,5)·(0,4,6) 다음 → 맨 아래 도(0) 블록의 30번
    assert rows == [
        {"파트": "피아노", "음개수": "3", "88건반_묶음": "0,4,7", "88건반_번호": "258", "12음_묶음": "0,4,7", "12음_맨아래": "0", "12음_시트번호": "30", "코드": "CM", "횟수": "2"}
    ]


def test_sheet_number_uses_the_lowest_note_block():
    d_major = (q(62, 0, 1), q(66, 0, 1), q(69, 0, 1))  # 레·파#·라 → 맨 아래 레(2) 블록

    assert count_sets(d_major) == {((0, 4, 7), (0, 4, 7), 2, 2 * 55 + 30, "DM"): 1}
