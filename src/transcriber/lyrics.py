"""가사 글을 음절로 나누고, 멜로디 음표에 한 글자씩 붙이는 모듈.

가사 파일 쓰는 법:
- 한글은 한 글자가 한 음표에 붙는다. 띄어쓰기와 줄바꿈은 자유롭게 해도 된다.
- 한 글자를 여러 음표에 걸쳐 길게 부르는 곳에는 "-"(또는 "ㅡ")를 음표 수만큼 넣는다.
  예: "흔들리는- 순간" → 는을 두 음표에 걸쳐 부름
- 마침표, 쉼표 같은 문장 부호는 무시한다.
"""

from pathlib import Path

from music21 import stream

MELISMA_MARKS = frozenset({"-", "_", "—", "–", "ㅡ"})  # 앞 글자를 이어서 부르는 표시
HOLD = ""  # 음표는 있지만 새 글자가 없는 자리


class LyricsError(Exception):
    """가사 파일을 읽을 수 없을 때 발생하는 오류."""


def parse_lyrics(text: str) -> tuple[str, ...]:
    """가사 글을 음표 하나에 붙일 단위(음절)로 나눈다. HOLD는 '앞 글자 이어 부르기'."""
    syllables: list[str] = []
    for word in text.split():
        latin_run = ""
        for char in word:
            if _is_hangul(char):
                syllables.extend(_flush(latin_run))
                latin_run = ""
                syllables.append(char)
            elif char in MELISMA_MARKS:
                syllables.extend(_flush(latin_run))
                latin_run = ""
                syllables.append(HOLD)
            elif char.isalnum():
                latin_run += char
        syllables.extend(_flush(latin_run))
    return tuple(syllables)


def read_lyrics_file(path: str | Path) -> tuple[str, ...]:
    file_path = Path(path)
    if not file_path.is_file():
        raise LyricsError(f"가사 파일을 찾을 수 없습니다: {file_path}")
    try:
        text = file_path.read_text(encoding="utf-8")
    except UnicodeDecodeError as error:
        raise LyricsError(f"가사 파일은 UTF-8 글자로 저장해 주세요: {file_path}") from error
    syllables = parse_lyrics(text)
    if not any(syllables):
        raise LyricsError(f"가사 파일에 글자가 없습니다: {file_path}")
    return syllables


def attach_lyrics(part: stream.Part, syllables: tuple[str, ...]) -> int:
    """멜로디 음표에 앞에서부터 차례로 음절을 붙인다. 붙인 자리(이어 부르기 포함) 수를 돌려준다."""
    notes = list(part.recurse().notes)
    for element, syllable in zip(notes, syllables):
        if syllable != HOLD:
            element.lyric = syllable
    return min(len(notes), len(syllables))


def _is_hangul(char: str) -> bool:
    return "가" <= char <= "힣"


def _flush(latin_run: str) -> list[str]:
    return [latin_run] if latin_run else []
