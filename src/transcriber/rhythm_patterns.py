"""음길이 패턴(리듬 모양)을 목록 없이 규칙으로 다루는 모듈.

칸마다 기호 하나:
- ㅅ: 쉼
- ㅇ: 음이 시작됨
- ㅡ: 앞 음이 이어짐 (맨 앞 칸의 ㅡ는 앞 마디에서 이어진 음)
규칙: ㅡ는 ㅅ 바로 뒤에 올 수 없다.

순서(구글 시트 '음길이 N개' 파일과 같음):
1. 소리 나는 칸(ㅇ·ㅡ)이 적은 것부터
2. 소리 나는 칸의 위치를 작은 번호부터 비교 (예: 1·3번 칸 < 1·4번 칸 < 2·3번 칸)
3. 그 안에서 ㅡ가 적은 것부터
4. ㅡ의 위치를 작은 번호부터 비교

32칸이면 패턴이 약 27조 개라 목록으로 저장할 수 없으므로, 번호 ↔ 패턴을 바로 계산한다.
번호는 0부터 센다(시트의 행 번호 = 번호 + 1).
"""

from functools import lru_cache
from math import comb
from typing import Iterator

REST, ONSET, TIE = "ㅅ", "ㅇ", "ㅡ"
SYMBOLS = (REST, ONSET, TIE)


def count(slots: int) -> int:
    """칸 수가 slots인 패턴의 개수. 1칸 3개, 2칸 8개, 3칸 21개 …"""
    _check_slots(slots)
    return sum(_weighted_sets(slots, 0, sounding, True) for sounding in range(slots + 1))


def is_valid(pattern: str) -> bool:
    """규칙에 맞는 패턴인지: ㅅ·ㅇ·ㅡ만 쓰고, ㅅ 바로 뒤에 ㅡ가 없어야 한다."""
    return bool(pattern) and set(pattern) <= set(SYMBOLS) and REST + TIE not in pattern


def pattern_at(slots: int, index: int) -> str:
    """slots칸 패턴 중 index번째(0부터) 패턴."""
    _check_slots(slots)
    if not 0 <= index < count(slots):
        raise ValueError(f"{slots}칸 패턴 번호는 0 이상 {count(slots) - 1} 이하여야 합니다: {index}")
    for sounding_count in range(slots + 1):
        group = _weighted_sets(slots, 0, sounding_count, True)
        if index < group:
            return _pattern_in_group(slots, sounding_count, index)
        index -= group
    raise AssertionError("도달할 수 없음")


def index_of(pattern: str) -> int:
    """패턴의 번호(0부터). pattern_at의 반대."""
    if not is_valid(pattern):
        raise ValueError(f"규칙에 맞지 않는 패턴입니다: {pattern!r}")
    slots = len(pattern)
    sounding = tuple(i for i, s in enumerate(pattern) if s != REST)
    index = sum(_weighted_sets(slots, 0, k, True) for k in range(len(sounding)))
    index += _sets_before(slots, sounding)
    candidates = _tie_candidates(sounding)
    ties = tuple(position for position, i in enumerate(candidates) if pattern[i] == TIE)
    index += sum(comb(len(candidates), m) for m in range(len(ties)))
    return index + _combination_rank(len(candidates), ties)


def iter_patterns(slots: int) -> Iterator[str]:
    """slots칸 패턴을 순서대로 하나씩 만든다(전부 메모리에 올리지 않음)."""
    for index in range(count(slots)):
        yield pattern_at(slots, index)


def _check_slots(slots: int) -> None:
    if slots < 1:
        raise ValueError(f"칸 수는 1 이상이어야 합니다: {slots}")


@lru_cache(maxsize=None)
def _weighted_sets(slots: int, start: int, remaining: int, previous_sounds: bool) -> int:
    """start번 칸부터 remaining개 칸을 소리 나게 고르는 방법을, 각 방법의 ㅇ/ㅡ 경우 수까지 곱해 센 값.

    소리 나는 칸이 맨 앞이거나 바로 앞 칸도 소리 나면 ㅇ·ㅡ 둘 다 가능(2배), 아니면 ㅇ만 가능.
    previous_sounds: start-1번 칸이 소리 나는지(start가 0이면 '맨 앞'이라 True로 둔다).
    """
    if remaining == 0:
        return 1
    if slots - start < remaining:
        return 0
    take = (2 if previous_sounds else 1) * _weighted_sets(slots, start + 1, remaining - 1, True)
    skip = _weighted_sets(slots, start + 1, remaining, False)
    return take + skip


def _pattern_in_group(slots: int, sounding_count: int, index: int) -> str:
    """소리 나는 칸이 sounding_count개인 묶음 안에서 index번째 패턴."""
    sounding: list[int] = []
    start, previous_sounds = 0, True
    variants = 1  # 지금까지 고른 칸들의 ㅇ/ㅡ 경우 수. 같은 칸 묶음의 경우들이 한데 모여 있도록 곱해 둔다
    while len(sounding) < sounding_count:
        remaining = sounding_count - len(sounding)
        for position in range(start, slots):
            weight = 2 if (previous_sounds if position == start else False) else 1
            block = variants * weight * _weighted_sets(slots, position + 1, remaining - 1, True)
            if index < block:
                sounding.append(position)
                start, previous_sounds, variants = position + 1, True, variants * weight
                break
            index -= block
    candidates = _tie_candidates(tuple(sounding))
    tie_set = _variant_at(len(candidates), index)
    ties = {candidates[i] for i in tie_set}
    return "".join(REST if i not in sounding else (TIE if i in ties else ONSET) for i in range(slots))


def _sets_before(slots: int, sounding: tuple[int, ...]) -> int:
    """같은 개수의 소리 나는 칸 묶음 중 sounding보다 앞에 오는 것들의 경우 수 합."""
    total, start, previous_sounds, variants = 0, 0, True, 1
    for order, chosen in enumerate(sounding):
        remaining = len(sounding) - order
        for position in range(start, chosen):
            weight = 2 if (previous_sounds if position == start else False) else 1
            total += variants * weight * _weighted_sets(slots, position + 1, remaining - 1, True)
        variants *= 2 if (previous_sounds if chosen == start else False) else 1
        start, previous_sounds = chosen + 1, True
    return total


def _tie_candidates(sounding: tuple[int, ...]) -> tuple[int, ...]:
    """ㅡ가 올 수 있는 칸: 소리 나는 칸 중 맨 앞(0번)이거나 바로 앞 칸도 소리 나는 칸."""
    chosen = set(sounding)
    return tuple(i for i in sounding if i == 0 or i - 1 in chosen)


def _variant_at(size: int, index: int) -> tuple[int, ...]:
    """ㅡ 개수가 적은 것부터, 같은 개수면 위치 순서로 index번째 ㅡ 위치 묶음."""
    for m in range(size + 1):
        if index < comb(size, m):
            return _combination_at(size, m, index)
        index -= comb(size, m)
    raise AssertionError("도달할 수 없음")


def _combination_at(size: int, pick: int, index: int) -> tuple[int, ...]:
    """0..size-1에서 pick개를 고르는 조합 중 사전 순서 index번째."""
    chosen, start = [], 0
    for left in range(pick, 0, -1):
        for value in range(start, size):
            block = comb(size - value - 1, left - 1)
            if index < block:
                chosen.append(value)
                start = value + 1
                break
            index -= block
    return tuple(chosen)


def _combination_rank(size: int, chosen: tuple[int, ...]) -> int:
    """_combination_at의 반대."""
    rank, start = 0, 0
    for order, value in enumerate(chosen):
        left = len(chosen) - order
        rank += sum(comb(size - v - 1, left - 1) for v in range(start, value))
        start = value + 1
    return rank
