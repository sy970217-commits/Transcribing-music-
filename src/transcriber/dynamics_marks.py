"""음의 세기(MIDI velocity)로 셈여림(pp~ff)과 크레셴도(<)·디크레셴도(>)를 정하는 모듈.

Finale 같은 프로그램은 같은 셈여림에서도 세기를 조금씩 바꿔 연주하므로,
새 세기가 몇 마디 이상 이어질 때만 셈여림을 바꿔 적는다.
"""

from dataclasses import dataclass
from fractions import Fraction
from statistics import mean, median

from transcriber.rhythm import QuantizedNote

# (셈여림, 이 세기 미만까지) — 일반적인 MIDI 세기 구간
LEVELS = (
    ("ppp", 24), ("pp", 40), ("p", 56), ("mp", 70),
    ("mf", 85), ("f", 100), ("ff", 115), ("fff", 128),
)
MIN_STABLE_MEASURES = 4  # 새 셈여림이 이만큼 이어져야 바꿔 적는다
HAIRPIN_MEASURES = 2  # 바뀌기 직전 이만큼 꾸준히 커지거나 작아지면 < 또는 >를 적는다


@dataclass(frozen=True)
class DynamicMark:
    """kind: "level"(pp~ff 글자), "crescendo"(<), "diminuendo"(>)"""

    beat: Fraction
    kind: str
    text: str | None = None
    end_beat: Fraction | None = None


def level_for(velocity: float) -> str:
    return next(name for name, upper in LEVELS if velocity < upper)


def plan_dynamics(notes: tuple[QuantizedNote, ...], bar_beats: Fraction) -> tuple[DynamicMark, ...]:
    """마디별 평균 세기로 셈여림 표시 위치를 정한다."""
    by_measure: dict[int, list[int]] = {}
    for n in notes:
        by_measure.setdefault(int(n.start_beats // bar_beats), []).append(n.velocity)
    if not by_measure:
        return ()

    measures = sorted(by_measure)
    loudness = {m: mean(by_measure[m]) for m in measures}
    first_beat = min(n.start_beats for n in notes)
    # 여러 마디를 묶어 볼 때는 중앙값을 쓴다: 한 마디만 튀어도 흔들리지 않게
    current = level_for(median(loudness[m] for m in measures[:MIN_STABLE_MEASURES]))
    marks = [DynamicMark(beat=first_beat, kind="level", text=current)]

    for position, measure in enumerate(measures):
        candidate = level_for(loudness[measure])
        window = measures[position : position + MIN_STABLE_MEASURES]
        if candidate == current or len(window) < MIN_STABLE_MEASURES:
            continue
        if level_for(median(loudness[m] for m in window)) != candidate:
            continue
        start = Fraction(measure) * bar_beats
        hairpin = _hairpin_before(measures[:position], loudness, current, candidate, bar_beats, start)
        if hairpin is not None:
            marks.append(hairpin)
        marks.append(DynamicMark(beat=start, kind="level", text=candidate))
        current = candidate
    return tuple(marks)


def _hairpin_before(previous, loudness, old_level, new_level, bar_beats, change_beat):
    recent = previous[-HAIRPIN_MEASURES:]
    if len(recent) < HAIRPIN_MEASURES:
        return None
    values = [loudness[m] for m in recent]
    louder = _rank(new_level) > _rank(old_level)
    steadily = all(b > a for a, b in zip(values, values[1:])) if louder else all(
        b < a for a, b in zip(values, values[1:])
    )
    if not steadily:
        return None
    return DynamicMark(
        beat=Fraction(recent[0]) * bar_beats,
        kind="crescendo" if louder else "diminuendo",
        end_beat=change_beat,
    )


def _rank(level: str) -> int:
    return [name for name, _ in LEVELS].index(level)
