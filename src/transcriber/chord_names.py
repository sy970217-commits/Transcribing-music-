"""같이 울리는 음들을 코드 이름(CM, Cm, Cdim, Caug …)으로 바꾸는 모듈.

음이름 번호: 0=C, 1=C#, 2=D, 3=D#, 4=E, 5=F, 6=F#, 7=G, 8=G#, 9=A, 10=A#, 11=B
쌓는 간격으로 적으면(반음 수, 아래 음부터):
- 0 4 3 = CM   (도·미·솔)
- 0 3 4 = Cm   (도·미♭·솔)
- 0 3 3 = Cdim (도·미♭·솔♭)
- 0 4 4 = Caug (도·미·솔#)
7화음(네 음):
- 0 4 3 3 = C7     (도·미·솔·시♭)
- 0 4 3 4 = CM7    (도·미·솔·시)
- 0 3 4 3 = Cm7    (도·미♭·솔·시♭)
- 0 3 3 4 = Cm7b5  (도·미♭·솔♭·시♭)
- 0 3 3 3 = Cdim7  (도·미♭·솔♭·시𝄫)
맨 아래 음이 근음(코드 이름의 음)이 아니면 자리바꿈 코드로 보고 '/맨 아래 음'을 붙인다.
예: 미·솔·도 → CM/E,  도·미♭·라♭(0 3 5) → G#M/C

실행: uv run chord-name 0 4 3  →  CM
"""

import argparse
import sys
from typing import Iterable

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
PITCH_CLASSES = 12

# 근음을 0으로 둔 구성음 → 코드 종류
CHORD_TYPES: dict[frozenset[int], str] = {
    frozenset({0, 4, 7}): "M",
    frozenset({0, 3, 7}): "m",
    frozenset({0, 3, 6}): "dim",
    frozenset({0, 4, 8}): "aug",
    frozenset({0, 4, 7, 10}): "7",
    frozenset({0, 4, 7, 11}): "M7",
    frozenset({0, 3, 7, 10}): "m7",
    frozenset({0, 3, 6, 10}): "m7b5",
    frozenset({0, 3, 6, 9}): "dim7",
}


def chord_name(pitches: Iterable[int]) -> str | None:
    """음 번호들(MIDI 번호 또는 0~11, 낮은 음이 맨 아래) → 코드 이름. 맞는 코드가 없으면 None."""
    notes = list(pitches)
    if not notes:
        return None
    bass = min(notes) % PITCH_CLASSES
    classes = {p % PITCH_CLASSES for p in notes}
    # 맨 아래 음을 근음으로 보는 경우를 먼저 본다
    # (증3화음·감7화음처럼 어느 음을 근음으로 봐도 맞는 코드, Cm7=E♭6처럼 두 이름이 가능한 코드 때문)
    for root in [bass] + sorted(classes - {bass}):
        kind = CHORD_TYPES.get(frozenset((p - root) % PITCH_CLASSES for p in classes))
        if kind is not None:
            name = NOTE_NAMES[root] + kind
            return name if root == bass else f"{name}/{NOTE_NAMES[bass]}"
    return None


def pitches_from_intervals(intervals: Iterable[int], bass: int = 0) -> tuple[int, ...]:
    """쌓는 간격(첫 값은 맨 아래 음과의 거리, 보통 0) → 음 번호들. 예: 0 4 3 → 0, 4, 7"""
    pitches, current = [], bass
    for step in intervals:
        if step < 0:
            raise ValueError(f"간격은 0 이상이어야 합니다: {step}")
        current += step
        pitches.append(current)
    return tuple(pitches)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="쌓는 간격(반음 수)을 코드 이름으로 바꾼다. 예: chord-name 0 4 3 → CM")
    parser.add_argument("intervals", nargs="+", type=int, help="아래 음부터 쌓는 간격. 첫 값은 보통 0")
    parser.add_argument("--bass", type=int, default=0, help="맨 아래 음 번호 0~11 (기본 0=C)")
    args = parser.parse_args(argv)
    try:
        name = chord_name(pitches_from_intervals(args.intervals, args.bass % PITCH_CLASSES))
    except ValueError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(name or "알 수 없는 코드")
    return 0


if __name__ == "__main__":
    sys.exit(main())
