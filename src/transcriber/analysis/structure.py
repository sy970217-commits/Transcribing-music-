"""분석기 G단계: 구조. D단계에서 박에 맞춘 음을 보고 곡이 어떤 부분(A, B …)으로 되풀이되는지 찾는다.

1. 곡을 4마디씩 '구절'로 나눈다(못갖춘마디는 첫 구절에 붙인다).
2. 구절끼리 닮은 정도를 잰다. 마디마다 (음 높이, 마디 안 위치)가 얼마나 겹치는지 보는데,
   모든 음과 맨 위 음(선율)을 따로 재서 평균한다. 코드가 같아도 선율이 다르면 다른 구절이 된다.
3. 앞에 나온 구절과 충분히 닮으면 같은 이름(x), 아니면 새 이름(y, z …)을 붙인다.
4. 이름 줄(예: x y x y z w x y)에서 두 번 넘게 되풀이되는 짧은 묶음(x y)을 한 부분으로 묶고,
   한 번만 나오는 구절이 이어지면(z w) 한 부분으로 묶는다. → A A B A
5. 부분에 나온 순서대로 A, B, C … 를 붙인다.

실행: uv run structure 곡.wav
"""

import argparse
import string
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.analysis.tonality import bar_starts

PHRASE_BARS = 4  # 구절 하나의 마디 수
GRID = Fraction(1, 4)  # 음 시작 위치를 이 칸(4분음표 단위)에 맞춰 비교한다
SAME_PHRASE = 0.6  # 구절 닮음 점수(0~1)가 이 이상이면 같은 구절


@dataclass(frozen=True)
class Section:
    """start~end(4분음표 단위)의 부분. 같은 label이면 같은 내용이 되풀이된 것."""

    start: Fraction
    end: Fraction
    label: str


@dataclass(frozen=True)
class StructureResult:
    sections: tuple[Section, ...]


def bar_fingerprint(notes: tuple[RhythmNote, ...], start: Fraction, end: Fraction) -> tuple[frozenset, frozenset]:
    """마디 안에서 시작하는 (음 높이, 위치)들: 모든 음, 그리고 위치마다 맨 위 음."""
    inside = [(n.pitch, round((n.start - start) / GRID)) for n in notes if start <= n.start < end]
    tops: dict[int, int] = {}
    for pitch, position in inside:
        tops[position] = max(tops.get(position, pitch), pitch)
    return frozenset(inside), frozenset((pitch, position) for position, pitch in tops.items())


def overlap(a: frozenset, b: frozenset) -> float:
    union = a | b
    return len(a & b) / len(union) if union else 0.0


def phrase_similarity(first: list, second: list) -> float:
    """마디 지문 목록 두 개의 닮음(0~1). 길이가 다르면 0."""
    if len(first) != len(second):
        return 0.0
    scores = [(overlap(x[0], y[0]) + overlap(x[1], y[1])) / 2 for x, y in zip(first, second)]
    return sum(scores) / len(scores)


def phrase_groups(bar_count: int, has_pickup: bool) -> list[range]:
    """마디 번호들을 4마디 구절로 나눈다. 못갖춘마디는 첫 구절에 붙인다."""
    first = 1 if has_pickup else 0
    groups = [range(i, min(i + PHRASE_BARS, bar_count)) for i in range(first, bar_count, PHRASE_BARS)]
    if has_pickup:
        groups = [range(0, groups[0].stop)] + groups[1:] if groups else [range(0, bar_count)]
    return groups


def name_phrases(prints: list[list]) -> list[int]:
    """구절마다 이름 번호. 앞 구절 중 가장 닮은 것이 충분히 닮으면 그 이름을 쓴다."""
    names: list[int] = []
    for i, phrase in enumerate(prints):
        scores = [(phrase_similarity(prints[j], phrase), j) for j in range(i)]
        best = max(scores, default=(0.0, -1))
        names.append(names[best[1]] if best[0] >= SAME_PHRASE else max(names, default=-1) + 1)
    return names


def find_repeat(units: list[tuple]) -> tuple | None:
    """두 번 넘게 나오는 묶음 중 구절 수가 가장 적은 것. 단위 2개 이상, 서로 다른 구절 2개 이상,
    아직 묶이지 않은 구절을 하나 이상 담아야 한다(이미 만든 부분끼리 더 큰 부분으로 묶지 않는다)."""
    found = []
    for length in range(2, len(units) // 2 + 1):
        for start in range(len(units) - length + 1):
            pattern = units[start:start + length]
            flat = tuple(name for unit in pattern for name in unit)
            if len(set(flat)) >= 2 and any(len(u) == 1 for u in pattern) and len(occurrences(units, pattern)) >= 2:
                found.append((len(flat), start, flat))
    return min(found)[2] if found else None


def occurrences(units: list[tuple], pattern: list[tuple]) -> list[int]:
    """pattern이 겹치지 않게 나오는 위치들(왼쪽부터)."""
    found, i = [], 0
    while i <= len(units) - len(pattern):
        if units[i:i + len(pattern)] == pattern:
            found.append(i)
            i += len(pattern)
        else:
            i += 1
    return found


def merge_units(units: list[tuple], merged: tuple) -> list[tuple]:
    """units에서 merged를 이루는 연속 단위들을 하나로 합친 새 목록."""
    result, i = [], 0
    while i < len(units):
        for length in range(1, len(units) - i + 1):
            if tuple(name for unit in units[i:i + length] for name in unit) == merged:
                result.append(merged)
                i += length
                break
        else:
            result.append(units[i])
            i += 1
    return result


def group_phrases(names: list[int]) -> list[tuple]:
    """구절 이름 줄 → 부분 목록(부분마다 구절 이름 묶음)."""
    units = [(name,) for name in names]
    while (repeat := find_repeat(units)) is not None:
        units = merge_units(units, repeat)
    grouped: list[tuple] = []
    for unit in units:
        if grouped and units.count(unit) == 1 and units.count(grouped[-1]) == 1:
            grouped[-1] = grouped[-1] + unit
        else:
            grouped.append(unit)
    return grouped


def label_of(index: int) -> str:
    letters = string.ascii_uppercase
    return letters[index % len(letters)] + (str(index // len(letters)) if index >= len(letters) else "")


def analyze_structure(rhythm: RhythmResult, beats: BeatAnalysis) -> StructureResult:
    """박에 맞춘 음 → 부분(A, B …) 구간들."""
    if not rhythm.notes:
        return StructureResult(())
    end = max(n.start + n.length for n in rhythm.notes)
    starts = bar_starts(beats, rhythm.beat_quarters, end)
    bounds = list(zip(starts, starts[1:] + [end]))
    if len(bounds) > 1 and bounds[-1][1] - bounds[-1][0] < beats.beats_per_bar * rhythm.beat_quarters / 2:
        bounds = bounds[:-2] + [(bounds[-2][0], end)]  # 끝의 짧은 꼬리(남은 울림)는 앞 마디에 붙인다
    has_pickup = beats.pickup_beats > 0
    groups = phrase_groups(len(bounds), has_pickup)
    # 못갖춘마디는 비교에서 뺀다(첫 구절도 다른 구절처럼 4마디로 비교)
    prints = [[bar_fingerprint(rhythm.notes, *bounds[b]) for b in group if not (has_pickup and b == 0)]
              for group in groups]
    sections, kinds, phrase = [], [], 0
    for unit in group_phrases(name_phrases(prints)):
        if unit not in kinds:
            kinds.append(unit)
        first, last = groups[phrase], groups[phrase + len(unit) - 1]
        sections.append(Section(bounds[first.start][0], bounds[last.stop - 1][1], label_of(kinds.index(unit))))
        phrase += len(unit)
    return StructureResult(tuple(sections))


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import RhythmError, quantize_notes
    from transcriber.audio_io import AudioLoadError
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원에서 되풀이되는 부분(A, B …)을 찾는다 (분석기 G단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        beats = analyze_beats(args.audio)
        result = analyze_structure(quantize_notes(recognize_notes(Path(args.audio))["mix"], beats), beats)
    except (AudioLoadError, PitchDetectionError, RhythmError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"부분 {len(result.sections)}개 (위치는 4분음표 단위): {' '.join(s.label for s in result.sections)}")
    for section in result.sections:
        print(f"  {section.start}~{section.end}: {section.label}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
