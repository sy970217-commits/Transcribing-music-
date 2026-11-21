import itertools
import random

import pytest

from transcriber.pitch_sets import count, from_midi, index_of, iter_sets, pitch_class_set, set_at, sheet_number


def test_twelve_tone_counts_match_the_sheets():
    # 시트 '음높이 N개 (개수)'의 개수
    assert [count(n, keys=12) for n in range(1, 13)] == [1, 11, 55, 165, 330, 462, 462, 330, 165, 55, 11, 1]


def test_twelve_tone_order_matches_sheet_columns():
    # 시트 '음높이 3개 (55)'의 1·2·10·11·55번째 열
    sets = list(iter_sets(3, keys=12))
    assert [sets[i] for i in (0, 1, 9, 10, 54)] == [(0, 1, 2), (0, 1, 3), (0, 1, 11), (0, 2, 3), (0, 10, 11)]


@pytest.mark.parametrize("size", range(1, 6))
def test_order_is_combinations_order(size):
    expected = [(0,) + c for c in itertools.combinations(range(1, 20), size - 1)]

    assert list(iter_sets(size, keys=20)) == expected
    assert [index_of(s, keys=20) for s in expected] == list(range(len(expected)))


def test_piano_88_keys_round_trip():
    assert count(8) == 5_843_355_957
    assert sum(count(n) for n in range(1, 89)) == 2**87
    rng = random.Random(3)
    for size in (1, 2, 8, 44, 87, 88):
        for index in [0, count(size) - 1] + [rng.randrange(count(size)) for _ in range(30)]:
            pitch_set = set_at(size, index)
            assert len(pitch_set) == size and pitch_set[0] == 0 and pitch_set[-1] <= 87
            assert index_of(pitch_set) == index


def test_from_midi_and_pitch_classes():
    c_major_spread = (48, 64, 67, 72)  # 도(C3)·미(E4)·솔(G4)·도(C5)

    assert from_midi(c_major_spread) == (0, 16, 19, 24)
    assert pitch_class_set(c_major_spread) == (0, 4, 7)


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        index_of((1, 2))  # 0이 없음
    with pytest.raises(ValueError):
        set_at(3, count(3))
    with pytest.raises(ValueError):
        from_midi((20, 60))  # 피아노 범위 밖
    with pytest.raises(ValueError):
        count(13, keys=12)


def test_sheet_number_includes_the_lowest_note_block():
    # 시트 '음높이 3개 (660)': 맨 아래 0 블록 1~55, 맨 아래 1 블록 56~110 …
    assert sheet_number((60, 61, 62)) == 1  # 도·도#·레 → (0,1,2), 맨 아래 0
    assert sheet_number((61, 62, 63)) == 56  # 도#·레·레# → 맨 아래 1 블록의 첫 번째
    assert sheet_number((47, 52, 55)) == 11 * 55 + index_of((0, 5, 8), keys=12) + 1  # 시(B2)가 맨 아래
    # 1개·2개 파일도 같은 규칙: 1개는 음이름+1, 2개는 맨 아래 블록 × 11 + 간격
    assert sheet_number((64,)) == 5
    assert sheet_number((62, 66)) == 2 * 11 + 4
    assert sheet_number(tuple(range(60, 72))) == 1 and sheet_number(tuple(range(61, 73))) == 2
