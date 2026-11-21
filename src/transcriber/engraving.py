"""악보 기호가 서로 겹치지 않게 자리를 정하는 모듈 (마디로 나눈 뒤에 쓴다).

피아노 두 단은 C4 덧줄을 같이 쓰도록 2칸만 떨어져 있어서, 두 단 사이에는 기호를 둘 자리가 없다.
그래서 기호는 바깥쪽으로 보낸다.
- 멜로디 단: 아래에는 가사가 있으므로 셋잇단 숫자·셈여림·글자 표시는 위에
- 피아노 위 단(높은음자리표): 위에. 기둥(stem)은 성부와 상관없이 모두 위로
- 피아노 아래 단(낮은음자리표): 아래에. 기둥은 성부와 상관없이 모두 아래로
- 8분쉼표: 한 성부인 마디에서는 둥근 머리가 아래에서 4번째 칸에 오게 두 단계 올린다
  (높은음자리표 미(E5) 칸, 낮은음자리표 솔(G3) 칸)
"""

from music21 import dynamics, expressions, note, stream

from transcriber.stem_lengths import shorten_blocking_stems

ABOVE, BELOW = "above", "below"
EIGHTH_REST_STEP_SHIFT = 2  # 기본(가운데 줄 기준) 위치에서 두 단계 위: 머리가 3번째 칸 → 4번째 칸
UP, DOWN = "up", "down"


def place_marks(score: stream.Score) -> None:
    """악보의 각 단에 맞게 기호 위치와 기둥 방향을 정한다."""
    piano_staves = [p for p in score.parts if isinstance(p, stream.PartStaff)]
    for part in score.parts:
        if part not in piano_staves:
            _place_part(part, marks_side=ABOVE, stem=None)
        elif part is piano_staves[0]:
            _place_part(part, marks_side=ABOVE, stem=UP)
        else:
            _place_part(part, marks_side=BELOW, stem=DOWN)


def _place_part(part: stream.Part, marks_side: str, stem: str | None) -> None:
    for element in part.recurse().getElementsByClass((dynamics.Dynamic, expressions.TextExpression)):
        element.placement = marks_side
    for wedge in part.spannerBundle.getByClass(dynamics.DynamicWedge):
        wedge.placement = marks_side
    for element in part.recurse().notes:
        for tuplet in element.duration.tuplets:
            tuplet.placement = marks_side
    _raise_eighth_rests(part)
    if stem is not None:
        for element in part.recurse().notes:  # 두 성부인 마디의 음까지 모두
            element.stemDirection = stem
        current_clef = None
        for measure in part.getElementsByClass(stream.Measure):
            current_clef = measure.clef or current_clef  # 마디에 적힌 음자리표, 없으면 앞 마디 것
            shorten_blocking_stems(measure, stem, current_clef)  # 같은 방향 기둥이 다른 성부 음표를 가리지 않게


def _raise_eighth_rests(part: stream.Part) -> None:
    """한 성부인 마디의 8분쉼표를 머리가 4번째 칸에 오게 올린다. 두 성부 마디는 성부끼리 피하는 위치를 그대로 둔다."""
    for measure in part.getElementsByClass(stream.Measure):
        if measure.voices:
            continue
        for rest in measure.getElementsByClass(note.Rest):
            if rest.duration.type == "eighth":
                rest.stepShift = EIGHTH_REST_STEP_SHIFT
