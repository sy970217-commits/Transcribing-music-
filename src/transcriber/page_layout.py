"""악보 쪽 배치(용지·줄 바꿈·마디 폭·단 간격)를 MusicXML에 적는 모듈. music21은 이 값들을 쓰지 않아서 저장 뒤에 고친다.

- 용지: A4(세로). 1칸(줄 사이) = 10 tenths, 7mm = 40 tenths 비율이므로 A4 폭 210mm = 1200 tenths.
- 줄 바꿈: measures_per_line 마디마다 새 줄. Finale는 줄이 바뀌는 표시가 있는 마디의 간격만 쓴다.
- 마디 폭: 한 줄 폭을 마디 수로 똑같이 나눠 모든 마디에 적는다. 음표가 많은 마디가 있어도
  Finale가 마디를 다음 줄로 넘기지 않고 정해진 수만큼 한 줄에 둔다.
- 단 간격: 피아노 두 단 사이(C4 위치가 같도록 2칸)와 멜로디·피아노 사이.
  공통 설정(<defaults>)에 단 번호 1을 넣으면 Finale가 모든 단에 똑같이 써서, 단 번호 2만 넣고
  나머지는 줄이 시작하는 마디의 <print>에 적는다.
"""

import re
from pathlib import Path

# 피아노 두 단 사이 간격(1칸 = 10). 높은음자리표의 C4(아래 덧줄 1개)와 낮은음자리표의 C4(위 덧줄 1개)가
# 같은 높이에 오도록: 위 단 아래로 1칸 + 아래 단 위로 1칸 = 2칸
GRAND_STAFF_DISTANCE_TENTHS = 20
# 멜로디 단과 피아노 위 단 사이: 가사·셈여림·셋잇단 숫자가 들어갈 자리로 12칸
MELODY_TO_PIANO_DISTANCE_TENTHS = 120

PAGE_WIDTH_TENTHS = 1200  # A4 폭
PAGE_HEIGHT_TENTHS = 1697  # A4 높이
PAGE_MARGIN_TENTHS = 70  # 위·아래·왼쪽·오른쪽 여백(약 12mm)
FIRST_SYSTEM_INDENT_TENTHS = 100  # 첫 줄은 악기 이름을 쓰느라 왼쪽을 더 비운다
SYSTEM_WIDTH_TENTHS = PAGE_WIDTH_TENTHS - 2 * PAGE_MARGIN_TENTHS

# <defaults> 안에서 staff-layout보다 뒤에 와야 하는 요소들(MusicXML 순서 규칙)
DEFAULTS_ORDER_AFTER_STAFF_LAYOUT = ("<appearance", "<music-font", "<word-font", "<lyric-font", "<lyric-language")


def apply_page_layout(path: Path, measures_per_line: int) -> None:
    """저장된 MusicXML 파일에 용지·줄 바꿈·마디 폭·단 간격을 적는다."""
    text = path.read_text(encoding="utf-8")
    text = _insert_into_defaults(text, _defaults_xml())
    text = _insert_measure_layout(text, measures_per_line)
    path.write_text(text, encoding="utf-8")


def measure_widths(measures_per_line: int) -> tuple[int, int]:
    """(첫 줄 마디 폭, 나머지 줄 마디 폭). 한 줄 폭을 마디 수로 똑같이 나눈다."""
    first = (SYSTEM_WIDTH_TENTHS - FIRST_SYSTEM_INDENT_TENTHS) // measures_per_line
    return first, SYSTEM_WIDTH_TENTHS // measures_per_line


def _defaults_xml() -> str:
    margins = "".join(
        f"        <{side}-margin>{PAGE_MARGIN_TENTHS}</{side}-margin>\n" for side in ("left", "right", "top", "bottom")
    )
    return (
        "    <page-layout>\n"
        f"      <page-height>{PAGE_HEIGHT_TENTHS}</page-height>\n"
        f"      <page-width>{PAGE_WIDTH_TENTHS}</page-width>\n"
        '      <page-margins type="both">\n'
        f"{margins}"
        "      </page-margins>\n"
        "    </page-layout>\n"
        "    <system-layout>\n"
        "      <system-margins>\n"
        "        <left-margin>0</left-margin>\n"
        "        <right-margin>0</right-margin>\n"
        "      </system-margins>\n"
        "    </system-layout>\n"
        + _staff_layout_xml(2, GRAND_STAFF_DISTANCE_TENTHS, indent=4)
    )


def _staff_layout_xml(number: int, distance: int, indent: int) -> str:
    pad = " " * indent
    return (
        f'{pad}<staff-layout number="{number}">\n'
        f"{pad}  <staff-distance>{distance}</staff-distance>\n"
        f"{pad}</staff-layout>\n"
    )


def _first_system_indent_xml() -> str:
    return (
        "        <system-layout>\n"
        "          <system-margins>\n"
        f"            <left-margin>{FIRST_SYSTEM_INDENT_TENTHS}</left-margin>\n"
        "            <right-margin>0</right-margin>\n"
        "          </system-margins>\n"
        "        </system-layout>\n"
    )


def _insert_into_defaults(text: str, xml: str) -> str:
    defaults_end = text.find("</defaults>")
    if defaults_end == -1:
        return text
    defaults_start = text.find("<defaults>")
    later = [text.find(tag, defaults_start, defaults_end) for tag in DEFAULTS_ORDER_AFTER_STAFF_LAYOUT]
    insert_at = min([i for i in later if i != -1], default=defaults_end)
    line_start = text.rfind("\n", 0, insert_at) + 1
    return text[:line_start] + xml + text[line_start:]


def _insert_measure_layout(text: str, measures_per_line: int) -> str:
    """파트마다 마디 폭과 줄 바꿈을 적고, 피아노(두 단 악기)에는 줄마다 단 간격을 적는다."""
    parts = list(re.finditer(r"<part id=[^>]*>", text))
    pieces, last = [], 0
    for order, part in enumerate(parts):
        body = _part_body(text, part)
        layouts = ""
        if "<staves>2</staves>" in body:
            if order > 0:  # 위에 다른 파트(멜로디)가 있을 때만 그 사이 간격을 적는다
                layouts += _staff_layout_xml(1, MELODY_TO_PIANO_DISTANCE_TENTHS, indent=8)
            layouts += _staff_layout_xml(2, GRAND_STAFF_DISTANCE_TENTHS, indent=8)
        first_print = (_first_system_indent_xml() if order == 0 else "") + layouts
        pieces += [text[last : part.end()], _layout_measures(body, layouts, first_print, measures_per_line)]
        last = part.end() + len(body)
    return "".join(pieces) + text[last:]


def _part_body(text: str, part: re.Match) -> str:
    return text[part.end() : text.find("</part>", part.end())]


def _layout_measures(body: str, layouts: str, first_print: str, measures_per_line: int) -> str:
    """마디마다 폭을 적고, 줄 첫 마디 맨 앞에 줄 바꿈 표시와 단 간격을 넣는다."""
    first_width, width = measure_widths(measures_per_line)
    counter = iter(range(len(body)))

    def add(match: re.Match) -> str:
        index = next(counter)
        tag = match.group(1).replace("<measure ", f'<measure width="{first_width if index < measures_per_line else width}" ', 1)
        if index == 0:
            return tag + (f"      <print>\n{first_print}      </print>\n" if first_print else "")
        if index % measures_per_line:
            return tag
        if not layouts:
            return tag + '      <print new-system="yes" />\n'
        return tag + f'      <print new-system="yes">\n{layouts}      </print>\n'

    return re.sub(r"(<measure[^>]*>\n)", add, body)
