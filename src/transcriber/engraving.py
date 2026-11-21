"""악보 기호가 서로 겹치지 않게 자리를 정하는 모듈 (마디로 나눈 뒤에 쓴다).

피아노 두 단은 C4 덧줄을 같이 쓰도록 2칸만 떨어져 있어서, 두 단 사이에는 기호를 둘 자리가 없다.
그래서 기호는 바깥쪽으로 보낸다.
- 멜로디 단: 아래에는 가사가 있으므로 셋잇단 숫자·셈여림·글자 표시는 위에
- 피아노 위 단(높은음자리표): 위에. 기둥(stem)은 성부와 상관없이 모두 위로
- 피아노 아래 단(낮은음자리표): 아래에. 기둥은 성부와 상관없이 모두 아래로
"""

from music21 import dynamics, expressions, stream

ABOVE, BELOW = "above", "below"
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
    if stem is not None:
        for element in part.recurse().notes:  # 두 성부인 마디의 음까지 모두
            element.stemDirection = stem
