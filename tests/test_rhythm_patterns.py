import itertools
import random

import pytest

from transcriber.rhythm_patterns import count, index_of, is_valid, iter_patterns, pattern_at

# 구글 시트 '음길이 3개 (21)'·'음길이 4개 (55)'의 내용
SHEET_FOUR = (
    "ㅅㅅㅅㅅ ㅇㅅㅅㅅ ㅡㅅㅅㅅ ㅅㅇㅅㅅ ㅅㅅㅇㅅ ㅅㅅㅅㅇ ㅇㅇㅅㅅ ㅡㅇㅅㅅ ㅇㅡㅅㅅ ㅡㅡㅅㅅ ㅇㅅㅇㅅ ㅡㅅㅇㅅ "
    "ㅇㅅㅅㅇ ㅡㅅㅅㅇ ㅅㅇㅇㅅ ㅅㅇㅡㅅ ㅅㅇㅅㅇ ㅅㅅㅇㅇ ㅅㅅㅇㅡ ㅇㅇㅇㅅ ㅡㅇㅇㅅ ㅇㅡㅇㅅ ㅇㅇㅡㅅ ㅡㅡㅇㅅ "
    "ㅡㅇㅡㅅ ㅇㅡㅡㅅ ㅡㅡㅡㅅ ㅇㅇㅅㅇ ㅡㅇㅅㅇ ㅇㅡㅅㅇ ㅡㅡㅅㅇ ㅇㅅㅇㅇ ㅇㅅㅇㅡ ㅡㅅㅇㅇ ㅡㅅㅇㅡ ㅅㅇㅇㅇ "
    "ㅅㅇㅡㅇ ㅅㅇㅇㅡ ㅅㅇㅡㅡ ㅇㅇㅇㅇ ㅡㅇㅇㅇ ㅇㅡㅇㅇ ㅇㅇㅡㅇ ㅇㅇㅇㅡ ㅡㅡㅇㅇ ㅡㅇㅡㅇ ㅡㅇㅇㅡ ㅇㅡㅡㅇ "
    "ㅇㅡㅇㅡ ㅇㅇㅡㅡ ㅡㅡㅡㅇ ㅡㅡㅇㅡ ㅡㅇㅡㅡ ㅇㅡㅡㅡ ㅡㅡㅡㅡ"
).split()


def brute_force(slots):
    """모든 경우를 만들어 규칙으로 거른 뒤 정해진 순서로 정렬(작은 칸 수 검증용)."""
    def key(p):
        sounding = tuple(i for i, s in enumerate(p) if s != "ㅅ")
        ties = tuple(i for i, s in enumerate(p) if s == "ㅡ")
        return (len(sounding), sounding, len(ties), ties)

    every = ("".join(t) for t in itertools.product("ㅅㅇㅡ", repeat=slots))
    return sorted((p for p in every if is_valid(p)), key=key)


def test_counts_follow_the_sheets_and_the_recurrence():
    assert [count(n) for n in range(1, 7)] == [3, 8, 21, 55, 144, 377]
    for n in range(3, 33):
        assert count(n) == 3 * count(n - 1) - count(n - 2)
    assert count(32) == 27_777_890_035_288


@pytest.mark.parametrize("slots", range(1, 9))
def test_numbers_match_full_list(slots):
    expected = brute_force(slots)

    assert list(iter_patterns(slots)) == expected
    assert [index_of(p) for p in expected] == list(range(len(expected)))


def test_order_matches_sheet_except_two_inconsistent_rows():
    mine = list(iter_patterns(4))
    differ = [i + 1 for i, (a, b) in enumerate(zip(mine, SHEET_FOUR)) if a != b]
    assert differ == [33, 34]  # 시트 원본에서 이 두 줄만 규칙과 순서가 뒤바뀌어 있음
    assert sorted(mine) == sorted(SHEET_FOUR)


def test_thirty_two_slots_round_trip():
    rng = random.Random(7)
    for index in [0, 1, count(32) - 1] + [rng.randrange(count(32)) for _ in range(200)]:
        pattern = pattern_at(32, index)
        assert len(pattern) == 32 and is_valid(pattern)
        assert index_of(pattern) == index


def test_rejects_bad_input():
    with pytest.raises(ValueError):
        pattern_at(4, 55)
    with pytest.raises(ValueError):
        index_of("ㅅㅡ")
    with pytest.raises(ValueError):
        count(0)
