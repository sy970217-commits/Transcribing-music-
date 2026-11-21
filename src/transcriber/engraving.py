"""악보 기호가 서로 겹치지 않게 자리를 정하는 모듈 (마디로 나눈 뒤에 쓴다).

피아노 두 단은 C4 덧줄을 같이 쓰도록 2칸만 떨어져 있어서, 두 단 사이에는 기호를 둘 자리가 없다.
그래서 기호는 바깥쪽으로 보낸다.
- 멜로디 단: 아래에는 가사가 있으므로 셋잇단 숫자·셈여림·글자 표시는 위에
- 피아노 위 단(높은음자리표): 위에. 기둥(stem)은 성부와 상관없이 모두 위로
- 피아노 아래 단(낮은음자리표): 아래에. 기둥은 성부와 상관없이 모두 아래로
- 빈 마디: 음이 하나도 없는 마디(단마다)는 온쉼표(마디 전체 쉼표) 하나만 둔다
- 쉼표: 성부가 몇 개든 표준 위치에 고정한다(standard_rest_positions). 위치를 적지 않으면
  Finale가 성부마다 쉼표를 위아래로 옮긴다.
"""

import re

from music21 import dynamics, expressions, harmony, note, stream

from transcriber.stem_lengths import shorten_blocking_stems

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
        current_clef = None
        for measure in part.getElementsByClass(stream.Measure):
            current_clef = measure.clef or current_clef  # 마디에 적힌 음자리표, 없으면 앞 마디 것
            shorten_blocking_stems(measure, stem, current_clef)  # 같은 방향 기둥이 다른 성부 음표를 가리지 않게



# 쉼표 표준 위치(MusicXML display-step/octave). 온쉼표는 넷째 줄에 매달리고, 나머지는 가운데 줄 기준
# (2분쉼표는 가운데 줄 위에 얹히고, 4·8·16·32분쉼표는 가운데에 걸친다)
REST_POSITIONS = {
    "treble": {"whole": ("D", 5), "other": ("B", 4)},
    "bass": {"whole": ("F", 3), "other": ("D", 3)},
}


def standard_rest_positions(xml: str) -> str:
    """보이는 쉼표마다 표준 위치를 적는다. 멜로디·피아노 위 단은 높은음자리표, 피아노 아래 단(staff 2)은 낮은음자리표."""
    return re.sub(r"<note\b[^>]*>.*?</note>", _fix_rest, xml, flags=re.S)


def _fix_rest(match: re.Match) -> str:
    note_xml = match.group(0)
    rest = re.search(r"<rest( measure=\"yes\")? />", note_xml)
    if rest is None or 'print-object="no"' in note_xml.split(">", 1)[0]:
        return note_xml
    clef = "bass" if "<staff>2</staff>" in note_xml else "treble"
    whole = rest.group(1) is not None or "<type>whole</type>" in note_xml
    step, octave = REST_POSITIONS[clef]["whole" if whole else "other"]
    placed = (
        f"<rest{rest.group(1) or ''}>"
        f"<display-step>{step}</display-step><display-octave>{octave}</display-octave></rest>"
    )
    return note_xml.replace(rest.group(0), placed, 1)


def collapse_empty_measures(part: stream.Part) -> None:
    """음이 하나도 없는 마디는 쉼표를 모두 지우고 온쉼표(마디 전체 쉼표) 하나만 둔다.

    성부가 둘로 나뉜 마디는 성부마다 쉼표가 생겨 빈 마디에 쉼표가 겹쳐 보이므로 하나로 합친다.
    코드 기호·셈여림 같은 다른 기호는 그대로 둔다.
    """
    for measure in part.getElementsByClass(stream.Measure):
        if any(_is_sounding(e) for e in measure.recurse().notes):
            continue
        for voice in list(measure.voices):
            for element in list(voice):
                if not isinstance(element, note.Rest):
                    measure.insert(voice.offset + element.offset, element)
            measure.remove(voice)
        for rest in list(measure.getElementsByClass(note.Rest)):
            measure.remove(rest)
        whole = note.Rest(quarterLength=measure.barDuration.quarterLength)
        whole.fullMeasure = True
        measure.insert(0, whole)


def _is_sounding(element) -> bool:
    return not isinstance(element, harmony.ChordSymbol)
