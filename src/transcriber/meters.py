"""박자표(4/4, 3/4, 6/8 …)와 박자표가 바뀌는 위치를 다루는 모듈."""

from dataclasses import dataclass
from fractions import Fraction

from music21 import meter

DEFAULT_TIME_SIGNATURE = "4/4"


@dataclass(frozen=True)
class TimeSignatureChange:
    """몇 박째(4분음표 = 1박)부터 어떤 박자표인지."""

    beat: Fraction
    text: str


def parse_time_signature(text: str) -> meter.TimeSignature:
    """"3/4" 같은 글자를 박자표로 바꾼다. 잘못된 글자면 쉬운 말로 알려 준다."""
    try:
        signature = meter.TimeSignature(text)
    except Exception as error:
        raise ValueError(f"알 수 없는 박자표입니다: {text} (예: 4/4, 3/4, 6/8)") from error
    if signature.barDuration.quarterLength <= 0:
        raise ValueError(f"알 수 없는 박자표입니다: {text} (예: 4/4, 3/4, 6/8)")
    return signature


def bar_length(text: str) -> Fraction:
    """한 마디가 몇 박(4분음표 기준)인지. 3/4 → 3, 6/8 → 3, 4/4 → 4."""
    return Fraction(parse_time_signature(text).barDuration.quarterLength)


def normalize_changes(changes: tuple[TimeSignatureChange, ...]) -> tuple[TimeSignatureChange, ...]:
    """0박에 박자표가 꼭 있게 하고, 같은 박자표가 반복되면 뺀다."""
    ordered = sorted(changes, key=lambda c: c.beat)
    if not ordered or ordered[0].beat > 0:
        ordered.insert(0, TimeSignatureChange(beat=Fraction(0), text=DEFAULT_TIME_SIGNATURE))
    result: list[TimeSignatureChange] = []
    for change in ordered:
        parse_time_signature(change.text)
        if result and result[-1].beat == change.beat:
            result[-1] = change
        elif not result or result[-1].text != change.text:
            result.append(change)
    return tuple(result)


def measure_number_at(beat, changes: tuple[TimeSignatureChange, ...]) -> int:
    """몇 박째가 몇 번째 마디인지(1부터). 박자표가 바뀌어도 맞게 센다."""
    position = Fraction(beat)
    ordered = normalize_changes(changes)
    measure = 1
    for change, following in zip(ordered, ordered[1:] + (None,)):
        length = bar_length(change.text)
        segment_end = following.beat if following is not None else None
        if segment_end is not None and position >= segment_end:
            measure += (segment_end - change.beat) // length
            continue
        return measure + int((position - change.beat) // length)
    return measure
