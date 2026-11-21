"""한 단(오른손 또는 왼손) 안의 음을 두 성부로 나누는 모듈.

피아노 악보에서는 길게 누른 음 위로 다른 음이 움직이면, 길게 누른 음을 아래 성부(2성부)로
따로 적는다. 1성부에는 움직이는 음을, 2성부에는 길게 이어지는 음을 둔다.
"""

from dataclasses import dataclass
from fractions import Fraction

from transcriber.rhythm import QuantizedNote

MIN_SUSTAIN_FOR_VOICE = Fraction(1)  # 다음 음보다 1박 이상 더 울려야 2성부로 뺀다


@dataclass(frozen=True)
class VoicedChord:
    """한 성부 안의 음 묶음(화음 또는 한 음)."""

    start: Fraction
    duration: Fraction
    notes: tuple[QuantizedNote, ...]


def split_voices(
    hand_notes: tuple[QuantizedNote, ...],
) -> tuple[tuple[VoicedChord, ...], tuple[VoicedChord, ...]]:
    """(1성부, 2성부)로 나눈다. 2성부가 필요 없으면 2성부는 빈 묶음."""
    starts = sorted({n.start_beats for n in hand_notes})
    next_onset = dict(zip(starts, starts[1:] + [None]))
    upper: list[VoicedChord] = []
    lower: list[VoicedChord] = []
    for start in starts:
        at_start = [n for n in hand_notes if n.start_beats == start]
        gap = next_onset[start] - start if next_onset[start] is not None else None
        sustained = [n for n in at_start if gap is not None and n.duration_beats - gap >= MIN_SUSTAIN_FOR_VOICE]
        moving = [n for n in at_start if n not in sustained]
        if sustained:
            lower.append(_chord(start, sustained))
        if moving:
            upper.append(_chord(start, moving))
    return _trim_overlaps(upper), _trim_overlaps(lower)


def _chord(start: Fraction, notes: list[QuantizedNote]) -> VoicedChord:
    # 같이 시작한 음들은 가장 짧은 음 길이로 한 화음이 된다
    return VoicedChord(start=start, duration=min(n.duration_beats for n in notes), notes=tuple(notes))


def _trim_overlaps(chords: list[VoicedChord]) -> tuple[VoicedChord, ...]:
    """한 성부 안에서는 다음 음이 시작할 때 앞 음을 끊는다."""
    trimmed = []
    for current, following in zip(chords, chords[1:] + [None]):
        duration = current.duration
        if following is not None:
            duration = min(duration, following.start - current.start)
        trimmed.append(VoicedChord(start=current.start, duration=duration, notes=current.notes))
    return tuple(trimmed)
