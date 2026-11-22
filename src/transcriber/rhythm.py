"""박 단위로 잰 음의 시작과 길이를 악보용 박자 칸에 맞추는(퀀타이즈) 모듈."""

import math
from dataclasses import dataclass
from fractions import Fraction


from transcriber.rolls import mark_rolled_chords

DEFAULT_TEMPO_BPM = 120.0
DEFAULT_SUBDIVISION = 4  # 한 박을 4칸으로 나눔 = 16분음표 단위
TRIPLET_DIVISION = 3  # 한 박을 3칸으로 나눔 = 8분음표 셋잇단음표
# 셋잇단음표 칸의 어긋남이 16분음표 칸의 절반보다 작을 때만 셋잇단음표로 본다
# (헷갈리면 더 흔한 16분음표 쪽을 고른다)
TRIPLET_PREFERENCE = 0.5
ONSET_DECIMALS = 3  # 시작 위치를 이 자리까지 같으면 같은 순간(화음)으로 본다
MIDDLE_C = 60  # 가운데 도. 이 음 이상은 오른손(높은음자리표), 아래는 왼손(낮은음자리표)


@dataclass(frozen=True)
class QuantizedNote:
    """박자 단위로 정리된 음. 1박 = 4분음표 하나."""

    pitch: int
    velocity: int
    start_beats: Fraction
    duration_beats: Fraction
    rolled: bool = False  # 아르페지오(펼친 화음)로 친 음


@dataclass(frozen=True)
class BeatNote:
    """박 단위로 잰, 아직 칸에 맞추지 않은 음."""

    pitch: int
    velocity: int
    start_beats: float
    end_beats: float
    rolled: bool = False


def quantize_beat_notes(
    notes: tuple[BeatNote, ...], subdivision: int = DEFAULT_SUBDIVISION, split_pitch: int | None = None
) -> tuple[QuantizedNote, ...]:
    """음을 박자 칸에 맞춘다. 박마다 16분음표 칸과 셋잇단음표 칸 중 더 잘 맞는 쪽을 고른다.

    split_pitch를 주면(피아노: 가운데 도) 그 음 이상(오른손)과 아래(왼손)를 따로 판단한다.
    한 박 안에서 왼손은 셋잇단음표, 오른손은 8분음표처럼 손마다 리듬이 다를 수 있기 때문이다.
    아르페지오로 친 화음은 먼저 찾아서 첫 음 시작에 맞춘다.
    """
    notes = mark_rolled_chords(notes)

    def hand(n: BeatNote) -> bool:
        return split_pitch is not None and n.pitch >= split_pitch

    divisions = {
        side: _choose_divisions(tuple(n.start_beats for n in notes if hand(n) == side), subdivision)
        for side in (False, True)
    }

    quantized = []
    for n in notes:
        grid = divisions[hand(n)]

        def division_at(beat: float) -> int:
            return grid.get(math.floor(beat), subdivision)

        start = _snap_to(n.start_beats, division_at(n.start_beats))
        end = _snap_to(n.end_beats, division_at(n.end_beats))
        shortest = Fraction(1, division_at(float(start)))
        quantized.append(
            QuantizedNote(
                pitch=n.pitch,
                velocity=n.velocity,
                start_beats=start,
                duration_beats=max(end - start, shortest),
                rolled=n.rolled,
            )
        )
    return tuple(sorted(quantized, key=lambda q: (q.start_beats, q.pitch)))


def _choose_divisions(starts: tuple[float, ...], subdivision: int) -> dict[int, int]:
    """박마다 쓸 칸 나누기 수를 정한다. 셋잇단음표 칸이 훨씬 잘 맞을 때만 3을 쓴다.

    같은 순간에 시작하는 음(화음)은 한 번만 센다. 화음 음 수만큼 여러 번 세면, 살짝 늦게 친 화음의
    어긋남이 부풀어 셋잇단음표인데도 16분음표로 판단할 수 있다.
    """
    by_beat: dict[int, set[float]] = {}
    for start in starts:
        by_beat.setdefault(math.floor(start), set()).add(round(start, ONSET_DECIMALS))

    divisions = {}
    for beat, onsets in by_beat.items():
        binary_error = sum(_snap_error(x, subdivision) for x in onsets)
        triplet_error = sum(_snap_error(x, TRIPLET_DIVISION) for x in onsets)
        use_triplet = triplet_error < binary_error * TRIPLET_PREFERENCE
        divisions[beat] = TRIPLET_DIVISION if use_triplet else subdivision
    return divisions


def _snap_to(beats: float, division: int) -> Fraction:
    return Fraction(round(beats * division), division)


def _snap_error(beats: float, division: int) -> float:
    return abs(beats - float(_snap_to(beats, division)))
