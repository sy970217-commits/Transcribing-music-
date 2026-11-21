"""반주에서 코드를 찾아 악보 위에 적을 코드 기호(CM, Am7, G/B …)를 정하는 모듈.

음높이와 음길이를 함께 본다.
- 구간(기본: 반 마디)마다 그 안에서 울린 음들을 모은다(분산화음처럼 차례로 친 음도 함께).
- 음이름마다 울린 길이를 더한다. 오래 울린 음일수록 코드 음일 가능성이 크다.
- 모든 음으로 코드 이름이 나오면 그대로 쓰고, 아니면 짧게 스친 음(경과음 등)을 빼 가며
  오래 울린 음 4개 또는 3개로 이루어진 코드를 찾는다.
- 베이스는 그 구간에서 가장 낮은 코드 음.
- 앞 구간과 같은 코드면 다시 적지 않는다.
"""

from dataclasses import dataclass
from fractions import Fraction
from itertools import combinations

from music21 import harmony, stream

from transcriber.chord_names import NOTE_NAMES, PITCH_CLASSES, Chord, identify
from transcriber.rhythm import QuantizedNote

MIN_CHORD_TONES = 3  # 음이름이 3개 이상일 때만 코드로 본다
MAX_CANDIDATE_TONES = 6  # 오래 울린 음 6개 안에서 코드를 찾는다


@dataclass(frozen=True)
class ChordMark:
    """beat 위치에 적을 코드."""

    beat: Fraction
    chord: Chord


def plan_chords(
    notes: tuple[QuantizedNote, ...], total_beats: Fraction, window_beats: Fraction
) -> tuple[ChordMark, ...]:
    """구간마다 코드를 찾아, 바뀌는 곳에만 코드 표시를 둔다."""
    marks: list[ChordMark] = []
    previous: Chord | None = None
    start = Fraction(0)
    while start < total_beats:
        chord = chord_in_window(notes, start, start + window_beats)
        if chord is not None and chord != previous:
            marks.append(ChordMark(beat=start, chord=chord))
            previous = chord
        start += window_beats
    return tuple(marks)


def chord_in_window(notes: tuple[QuantizedNote, ...], start: Fraction, end: Fraction) -> Chord | None:
    """start~end 사이에 울린 음들로 코드를 찾는다. 못 찾으면 None."""
    weights: dict[int, Fraction] = {}
    lowest: dict[int, int] = {}  # 음이름별로 가장 낮게 울린 음(베이스를 정하려고)
    for n in notes:
        overlap = min(end, n.start_beats + n.duration_beats) - max(start, n.start_beats)
        if overlap <= 0:
            continue
        pitch_class = n.pitch % PITCH_CLASSES
        weights[pitch_class] = weights.get(pitch_class, Fraction(0)) + overlap
        lowest[pitch_class] = min(lowest.get(pitch_class, n.pitch), n.pitch)
    if len(weights) < MIN_CHORD_TONES:
        return None
    strongest = sorted(weights, key=lambda pc: (-weights[pc], lowest[pc]))[:MAX_CANDIDATE_TONES]
    candidates = [tuple(weights)] + [
        group
        for size in (4, 3)
        for group in sorted(combinations(strongest, size), key=lambda g: -sum(weights[pc] for pc in g))
    ]
    for group in candidates:
        chord = identify(sorted(lowest[pc] for pc in group))
        if chord is not None:
            return chord
    return None


# 우리 코드 종류 → MusicXML 코드 종류(music21 이름)
MUSICXML_KINDS = {
    "M": "major",
    "m": "minor",
    "dim": "diminished",
    "aug": "augmented",
    "7": "dominant-seventh",
    "M7": "major-seventh",
    "m7": "minor-seventh",
    "m7b5": "half-diminished-seventh",
    "dim7": "diminished-seventh",
}


def chord_window(bar_beats: Fraction) -> Fraction:
    """코드를 찾는 구간 길이: 짝수 박 마디(4/4 등)는 반 마디, 아니면(3/4 등) 한 마디."""
    return bar_beats / 2 if bar_beats.numerator % 2 == 0 and bar_beats.denominator == 1 else bar_beats


def attach_chord_symbols(
    part: stream.Part, notes: tuple[QuantizedNote, ...], total_beats: Fraction, bar_beats: Fraction
) -> None:
    """찾은 코드를 part(맨 위 단) 위에 코드 기호로 넣는다. 글자는 CM·Am7처럼 우리 이름 그대로."""
    for mark in plan_chords(notes, total_beats, chord_window(bar_beats)):
        chord = mark.chord
        symbol = harmony.ChordSymbol(
            root=NOTE_NAMES[chord.root], bass=NOTE_NAMES[chord.bass], kind=MUSICXML_KINDS[chord.kind]
        )
        symbol.chordKindStr = chord.kind  # 악보에 보이는 글자(M, m, dim, 7 …)
        part.insert(mark.beat, symbol)
