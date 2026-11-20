"""빠르기 변화를 악보에 어떻게 표시할지 정하는 모듈.

Finale에서 내보낸 MIDI에는 빠르기 변화가 아주 많다(가을꽃은 123번).
- 악보에 적힌 것: ♩=76 같은 새 빠르기, rit.(점점 느리게)
- Finale가 스스로 넣은 것: 프레이즈 끝의 아주 작은 늦춤, 늘임표의 멈춤
악보에는 앞의 것만 보이게 적고, 나머지는 '숨은 빠르기'로 넣어 연주에만 쓰이게 한다.
"""

from dataclasses import dataclass
from fractions import Fraction

MIN_SHOWN_TEMPO_DIFF = 3.0  # 지금 적힌 빠르기와 이만큼(BPM) 이상 다르면 새로 적는다
MIN_RAMP_CHANGE = 0.10  # 점점 빨라지거나 느려지는 폭이 10% 이상이면 rit./accel.로 적는다


@dataclass(frozen=True)
class TempoChange:
    """빠르기 변화 하나: 몇 박째부터 몇 BPM인지."""

    beat: Fraction
    bpm: float


@dataclass(frozen=True)
class TempoMark:
    """악보에 넣을 표시 하나.

    kind: "shown"(♩=76처럼 보이게), "hidden"(연주에만 쓰임), "text"(rit./accel.)
    """

    beat: Fraction
    kind: str
    bpm: float | None = None
    text: str | None = None


def plan_tempo_marks(
    changes: tuple[TempoChange, ...], total_beats: Fraction, bar_beats: Fraction
) -> tuple[TempoMark, ...]:
    """첫 빠르기(0박) 다음의 변화들을 보이는 표시/숨은 표시/rit. 글자로 나눈다."""
    ordered = sorted(changes, key=lambda c: c.beat)
    if len(ordered) < 2:
        return ()

    marks: list[TempoMark] = []
    shown_bpm = ordered[0].bpm
    index = 1
    while index < len(ordered):
        end = _run_end(ordered, index, bar_beats)
        run = ordered[index : end + 1]
        start_bpm = ordered[index - 1].bpm
        if len(run) >= 2 and abs(run[-1].bpm - start_bpm) / start_bpm >= MIN_RAMP_CHANGE:
            text = "rit." if run[-1].bpm < start_bpm else "accel."
            marks.append(TempoMark(beat=Fraction(int(run[0].beat)), kind="text", text=text))
            marks.extend(TempoMark(beat=c.beat, kind="hidden", bpm=c.bpm) for c in run)
        else:
            for position, change in enumerate(run, start=index):
                next_beat = ordered[position + 1].beat if position + 1 < len(ordered) else total_beats
                held = next_beat - change.beat >= bar_beats
                if held and abs(change.bpm - shown_bpm) >= MIN_SHOWN_TEMPO_DIFF:
                    marks.append(TempoMark(beat=change.beat, kind="shown", bpm=change.bpm))
                    shown_bpm = change.bpm
                else:
                    marks.append(TempoMark(beat=change.beat, kind="hidden", bpm=change.bpm))
        index = end + 1
    return tuple(marks)


def _run_end(ordered: list[TempoChange], start: int, bar_beats: Fraction) -> int:
    """start부터 같은 방향(계속 느려짐/빨라짐)으로 촘촘히 이어지는 변화의 마지막 번호."""
    direction = _sign(ordered[start].bpm - ordered[start - 1].bpm)
    end = start
    while end + 1 < len(ordered):
        following = ordered[end + 1]
        same_direction = _sign(following.bpm - ordered[end].bpm) == direction
        close = following.beat - ordered[end].beat < bar_beats
        if not (same_direction and close):
            break
        end += 1
    return end


def _sign(value: float) -> int:
    return (value > 0) - (value < 0)
