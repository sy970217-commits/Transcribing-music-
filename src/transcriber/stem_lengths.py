"""한 단에 두 성부가 있고 기둥 방향이 같을 때, 기둥이 다른 성부의 음표를 가리지 않게 기둥 길이를 줄이는 모듈.

예: 낮은음자리표 단에서 위 성부 화음(미♭·솔·시♭)의 기둥이 아래로 내려가면 아래 성부의 낮은 미♭을 덮는다.
그러면 기둥 끝을 낮은 음표보다 STEM_CLEARANCE 만큼 위에서 멈추게 한다(MusicXML <stem default-y>).

위치 단위는 1/10칸(tenths). 0은 단의 맨 윗줄, 아래로 갈수록 음수. 한 음(줄↔칸) 차이는 5.
"""

from music21 import clef, note, stream, style

STEP_TENTHS = 5  # 줄과 칸 하나 차이
DEFAULT_STEM_TENTHS = 35  # 보통 기둥 길이(3.5칸)
STEM_CLEARANCE = 10  # 가려지면 안 되는 음표와 기둥 끝 사이 여유(1칸)
MIN_STEM_TENTHS = 10  # 이보다 짧게는 줄이지 않는다(1칸)


def shorten_blocking_stems(measure: stream.Measure, direction: str, current_clef: clef.Clef | None) -> None:
    """두 성부 마디에서 다른 성부 음표 위로 지나가는 기둥을 줄인다. direction: "up" 또는 "down"."""
    voices = list(measure.voices)
    if len(voices) < 2:
        return
    top_line = (current_clef or clef.TrebleClef()).lowestLine + 8  # 맨 윗줄의 음 높이
    spans = [(voice, _spans(voice)) for voice in voices]
    for voice, elements in spans:
        others = [item for other, items in spans if other is not voice for item in items]
        for start, end, element in elements:
            blockers = [e for s, f, e in others if s < end and start < f]
            _shorten(element, blockers, direction, top_line)


def _spans(voice: stream.Voice) -> list[tuple[float, float, note.NotRest]]:
    return [
        (voice.offset + e.offset, voice.offset + e.offset + e.quarterLength, e)
        for e in voice.notes
        if e.quarterLength > 0
    ]


def _y(pitch_obj, top_line: int) -> int:
    return (pitch_obj.diatonicNoteNum - top_line) * STEP_TENTHS


def _shorten(element: note.NotRest, blockers: list[note.NotRest], direction: str, top_line: int) -> None:
    if direction == "down":
        stem_start = min(_y(p, top_line) for p in element.pitches)
        below = [_y(p, top_line) for b in blockers for p in b.pitches if _y(p, top_line) < stem_start]
        if not below:
            return
        stop = max(below) + STEM_CLEARANCE  # 가장 높은 가려질 음표보다 위
        end = min(stop, stem_start - MIN_STEM_TENTHS)
        if end <= stem_start - DEFAULT_STEM_TENTHS:
            return  # 보통 길이로도 닿지 않음
    else:
        stem_start = max(_y(p, top_line) for p in element.pitches)
        above = [_y(p, top_line) for b in blockers for p in b.pitches if _y(p, top_line) > stem_start]
        if not above:
            return
        stop = min(above) - STEM_CLEARANCE
        end = max(stop, stem_start + MIN_STEM_TENTHS)
        if end >= stem_start + DEFAULT_STEM_TENTHS:
            return
    stem_style = style.Style()
    stem_style.absoluteY = end
    element.style.stemStyle = stem_style
