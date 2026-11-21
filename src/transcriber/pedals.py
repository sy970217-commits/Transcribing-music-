"""피아노 오른쪽 페달(댐퍼 페달)을 MIDI에서 읽어 악보에 Ped. ─ * 로 표시하는 모듈."""

from dataclasses import dataclass
from fractions import Fraction

import pretty_midi
from music21 import expressions, stream

SUSTAIN_PEDAL_CONTROLLER = 64  # MIDI에서 오른쪽 페달 번호
PEDAL_DOWN_THRESHOLD = 64  # 이 값 이상이면 밟은 것
PEDAL_GRID = 4  # 페달 위치를 16분음표 단위로 맞춤


@dataclass(frozen=True)
class PedalSpan:
    """페달을 밟고 있는 구간(박 단위)."""

    start_beats: Fraction
    end_beats: Fraction


def read_pedals(midi: pretty_midi.PrettyMIDI, tracks: list[pretty_midi.Instrument]) -> tuple[PedalSpan, ...]:
    """트랙들의 페달 정보를 읽어 밟은 구간 목록으로 만든다."""
    events = sorted(
        (c.time, c.value >= PEDAL_DOWN_THRESHOLD)
        for track in tracks
        for c in track.control_changes
        if c.number == SUSTAIN_PEDAL_CONTROLLER
    )
    spans: list[PedalSpan] = []
    down_at = None
    for time, is_down in events:
        beat = _snap(midi.time_to_tick(time) / midi.resolution)
        if is_down and down_at is None:
            down_at = beat
        elif not is_down and down_at is not None:
            if beat > down_at:
                spans.append(PedalSpan(start_beats=down_at, end_beats=beat))
            down_at = None
    if down_at is not None:
        end = _snap(midi.time_to_tick(midi.get_end_time()) / midi.resolution)
        if end > down_at:
            spans.append(PedalSpan(start_beats=down_at, end_beats=end))
    return tuple(spans)


def attach_pedals(part: stream.Part, spans: tuple[PedalSpan, ...]) -> int:
    """구간마다 그 안에서 시작하는 음들에 페달 표시를 붙인다. 붙인 페달 수를 돌려준다."""
    notes = list(part.flatten().notes)
    attached = 0
    for span in spans:
        covered = [n for n in notes if span.start_beats <= n.offset < span.end_beats]
        if not covered:
            continue
        part.insert(0, expressions.PedalMark(covered))
        attached += 1
    return attached


def _snap(beats: float) -> Fraction:
    return Fraction(round(beats * PEDAL_GRID), PEDAL_GRID)
