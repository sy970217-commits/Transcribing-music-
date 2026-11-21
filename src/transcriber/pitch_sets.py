"""음높이 묶음(같이 울리는 음들)을 목록 없이 규칙으로 다루는 모듈.

규칙(구글 시트 '음높이 N개' 파일과 같음):
- 가장 낮은 음을 0으로 두고 나머지 음을 그 위 몇 번째 음(반음 단위)인지로 적는다.
- 그래서 묶음에는 항상 0이 들어 있고, 순서는 작은 수부터 비교한다(사전 순서).
  예: 3개 묶음은 (0,1,2), (0,1,3), …, (0,1,11), (0,2,3), …

칸 수(keys):
- 12: 옥타브를 무시한 12음 (시트 '음높이 N개' 파일, N은 1~12). 0=도(C), 1=도#, …, 11=시
  시트는 맨 아래 음이 0인 블록 다음에 맨 아래 음이 1, 2, …, 11인 블록이 이어진다(12배).
- 88: 피아노 건반 전체 (N은 1~88, 경우의 수가 너무 커서 시트로 저장하지 않고 계산한다)

번호는 0부터 센다(시트의 열 번호 = 번호 + 1).
"""

from math import comb
from typing import Iterable, Iterator

PITCH_CLASSES = 12
PIANO_KEYS = 88
PIANO_LOWEST_MIDI = 21  # A0
PIANO_HIGHEST_MIDI = PIANO_LOWEST_MIDI + PIANO_KEYS - 1  # C8


def count(size: int, keys: int = PIANO_KEYS) -> int:
    """음 size개 묶음의 개수 = 0을 뺀 나머지 keys-1칸에서 size-1개를 고르는 경우의 수."""
    _check_size(size, keys)
    return comb(keys - 1, size - 1)


def set_at(size: int, index: int, keys: int = PIANO_KEYS) -> tuple[int, ...]:
    """음 size개 묶음 중 index번째(0부터)."""
    total = count(size, keys)
    if not 0 <= index < total:
        raise ValueError(f"{size}개 묶음 번호는 0 이상 {total - 1} 이하여야 합니다: {index}")
    chosen, start = [0], 1
    for left in range(size - 1, 0, -1):
        for value in range(start, keys):
            block = comb(keys - value - 1, left - 1)
            if index < block:
                chosen.append(value)
                start = value + 1
                break
            index -= block
    return tuple(chosen)


def index_of(pitch_set: Iterable[int], keys: int = PIANO_KEYS) -> int:
    """묶음의 번호(0부터). set_at의 반대. 묶음은 0을 포함하고 0~keys-1 안이어야 한다."""
    values = tuple(sorted(set(pitch_set)))
    if not values or values[0] != 0 or values[-1] >= keys:
        raise ValueError(f"0을 포함하고 0~{keys - 1} 사이인 묶음이어야 합니다: {values}")
    rank, start = 0, 1
    for order, value in enumerate(values[1:], start=1):
        left = len(values) - order
        rank += sum(comb(keys - v - 1, left - 1) for v in range(start, value))
        start = value + 1
    return rank


def iter_sets(size: int, keys: int = PIANO_KEYS) -> Iterator[tuple[int, ...]]:
    """음 size개 묶음을 순서대로 하나씩 만든다."""
    for index in range(count(size, keys)):
        yield set_at(size, index, keys)


def from_midi(pitches: Iterable[int]) -> tuple[int, ...]:
    """MIDI 음 번호들 → 가장 낮은 음을 0으로 둔 88건반 묶음. 피아노 범위(A0~C8) 밖이면 오류."""
    unique = sorted(set(pitches))
    if not unique:
        raise ValueError("음이 하나도 없습니다")
    if unique[0] < PIANO_LOWEST_MIDI or unique[-1] > PIANO_HIGHEST_MIDI:
        raise ValueError(f"피아노 건반 범위(MIDI 21~108) 밖의 음이 있습니다: {unique}")
    return tuple(p - unique[0] for p in unique)


def pitch_class_set(pitches: Iterable[int]) -> tuple[int, ...]:
    """MIDI 음 번호들 → 옥타브를 무시하고 가장 낮은 음의 음이름을 0으로 둔 12음 묶음."""
    unique = sorted(set(pitches))
    if not unique:
        raise ValueError("음이 하나도 없습니다")
    return tuple(sorted({(p - unique[0]) % PITCH_CLASSES for p in unique}))


def sheet_number(pitches: Iterable[int]) -> int:
    """MIDI 음 번호들 → 구글 시트 '음높이 N개' 파일에서의 번호(1부터, 맨 아래 음 블록까지 포함).

    맨 아래 음의 음이름(0=도 … 11=시) 블록 안에서, 그 음을 0으로 둔 모양의 순서를 센다.
    번호 = 맨 아래 음 × (블록 하나의 개수) + 모양 번호 + 1
    """
    shape = pitch_class_set(pitches)
    lowest = min(pitches) % PITCH_CLASSES
    return lowest * count(len(shape), PITCH_CLASSES) + index_of(shape, PITCH_CLASSES) + 1


def _check_size(size: int, keys: int) -> None:
    if not 1 <= size <= keys:
        raise ValueError(f"음 개수는 1 이상 {keys} 이하여야 합니다: {size}")
