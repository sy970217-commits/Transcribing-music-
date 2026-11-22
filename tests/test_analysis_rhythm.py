from fractions import Fraction

import numpy as np
import pytest

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.rhythm import RhythmError, fill_short_gaps, main, quantize_notes
from transcriber.pitch import Note


def beats_at(times, signature="4/4", pulses=2, downbeats=None, pickup=0):
    per_bar = {"4/4": 4, "3/4": 3, "6/8": 2}[signature]
    return BeatAnalysis(
        beats=tuple(times), downbeats=tuple(downbeats if downbeats is not None else times[::per_bar]),
        time_signature=signature, beats_per_bar=per_bar, pulses_per_beat=pulses, tempo_bpm=120.0,
        pickup_beats=pickup,
    )


def n(pitch, start, end):
    return Note(start, end, pitch, 80)


def placed(result):
    return [(x.pitch, x.start, x.length) for x in result.notes]


def test_slightly_off_eighth_notes_snap_to_the_grid():
    beats = beats_at([i * 0.5 for i in range(8)])  # 4분음표 = 0.5초
    notes = (n(60, 0.01, 0.24), n(62, 0.26, 0.5), n(64, 0.49, 0.99))

    assert placed(quantize_notes(notes, beats)) == [
        (60, Fraction(0), Fraction(1, 2)), (62, Fraction(1, 2), Fraction(1, 2)), (64, Fraction(1), Fraction(1)),
    ]


def test_each_beat_chooses_triplets_or_sixteenths_by_itself():
    beats = beats_at([i * 0.6 for i in range(8)])
    triplets = tuple(n(60 + k, k * 0.2, k * 0.2 + 0.2) for k in range(3))  # 첫 박: 셋잇단
    sixteenths = tuple(n(70 + k, 0.6 + k * 0.15, 0.6 + k * 0.15 + 0.15) for k in range(4))  # 둘째 박: 16분

    starts = [x.start for x in quantize_notes(triplets + sixteenths, beats).notes]

    assert starts == [0, Fraction(1, 3), Fraction(2, 3), 1, Fraction(5, 4), Fraction(3, 2), Fraction(7, 4)]


def test_three_evenly_spaced_notes_in_a_beat_stay_triplets_without_triplet_grid():
    beats = beats_at([i * 0.6 for i in range(8)])
    triplets = tuple(n(60 + k, k * 0.2, k * 0.2 + 0.2) for k in range(3))

    result = quantize_notes(triplets, beats, allow_triplets=False)

    assert placed(result) == [(60 + k, Fraction(k, 3), Fraction(1, 3)) for k in range(3)]


def test_without_triplet_grid_a_lone_off_note_snaps_to_sixteenths():
    beats = beats_at([i * 0.6 for i in range(8)])
    notes = (n(60, 0.0, 0.2), n(62, 0.2, 0.6))  # 박 안에 음 2개뿐: 셋잇단으로 보지 않는다

    result = quantize_notes(notes, beats, allow_triplets=False)

    assert all((x.start * 4).denominator == 1 and (x.length * 4).denominator == 1 for x in result.notes)


def test_compound_meter_keeps_its_eighths_without_triplets():
    beats = beats_at([i * 0.6 for i in range(6)], signature="6/8", pulses=3)
    eighths = tuple(n(60 + k, k * 0.2, k * 0.2 + 0.2) for k in range(3))

    with_triplets = placed(quantize_notes(eighths, beats))

    assert placed(quantize_notes(eighths, beats, allow_triplets=False)) == with_triplets


def test_compound_meter_counts_in_dotted_quarters():
    beats = beats_at([i * 0.9 for i in range(6)], signature="6/8", pulses=3)  # 점4분음표 = 0.9초
    notes = (n(60, 0.0, 0.3), n(62, 0.3, 0.6), n(64, 0.6, 0.9), n(65, 0.9, 1.8))

    result = quantize_notes(notes, beats)

    assert result.beat_quarters == Fraction(3, 2)
    assert placed(result)[1:3] == [(62, Fraction(1, 2), Fraction(1, 2)), (64, Fraction(1), Fraction(1, 2))]
    assert placed(result)[3] == (65, Fraction(3, 2), Fraction(3, 2))


def test_changing_tempo_follows_the_beats():
    times = [0.0, 0.5, 1.0, 1.6, 2.3, 3.1]  # 점점 느려짐
    notes = tuple(n(60, t, t + 0.1) for t in times[:-1])

    assert [x.start for x in quantize_notes(notes, beats_at(times)).notes] == [0, 1, 2, 3, 4]


def test_pickup_beat_is_position_zero():
    times = [i * 0.5 for i in range(9)]
    beats = beats_at(times, downbeats=times[1::4], pickup=1)

    assert quantize_notes((n(67, 0.0, 0.5), n(60, 0.5, 2.5)), beats).notes[1].start == 1


def test_short_gap_is_filled_but_long_rest_is_kept():
    pitches = np.array([60, 62, 64])
    starts = np.array([0.0, 1.0, 3.0])
    ends = np.array([0.6, 1.4, 4.0])  # 첫 음은 0.4박 틈, 둘째 음 뒤는 1.6박 쉼

    assert list(fill_short_gaps(pitches, starts, ends)) == [1.0, 1.4, 4.0]


def test_far_notes_do_not_fill_and_same_pitch_cuts():
    pitches = np.array([40, 80, 40])
    starts = np.array([0.0, 0.5, 1.0])
    ends = np.array([1.8, 0.7, 2.0])  # 첫 음은 같은 음이 다시 나오는 1박에서 끊김

    assert list(fill_short_gaps(pitches, starts, ends)) == [1.0, 0.7, 2.0]


def test_too_few_beats_is_an_error():
    with pytest.raises(RhythmError):
        quantize_notes((n(60, 0, 1),), beats_at([0.0]))


def test_no_notes_gives_empty_result():
    assert quantize_notes((), beats_at([0.0, 0.5])).notes == ()


def test_cli_reports_bad_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_extra_beat_only_affects_its_own_bar():
    # 두 번째 마디(2.0~4.0초)에서 박을 하나 더 찾음(5개). 세 번째 마디 첫 박은 그대로 8번째 박이어야 한다
    times = [0.0, 0.5, 1.0, 1.5, 2.0, 2.4, 2.8, 3.2, 3.6, 4.0, 4.5, 5.0, 5.5]
    beats = beats_at(times, downbeats=[0.0, 2.0, 4.0])

    starts = [x.start for x in quantize_notes((n(60, 4.0, 4.4), n(62, 5.0, 5.4)), beats).notes]

    assert starts == [8, 10]
