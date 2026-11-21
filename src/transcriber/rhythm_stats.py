"""곡에 실제로 나온 리듬 패턴(한 박 단위)을 모아 세는 모듈.

한 박을 칸으로 나눠 ㅅ(쉼)·ㅇ(시작)·ㅡ(이어짐)으로 적는다(rhythm_patterns와 같은 기호).
- 16분음표로 나뉘는 박: 4칸 / 셋잇단음표 박: 3칸 / 둘이 섞인 박: 12칸
- 여러 음이 겹치면(화음·반주) 한 줄로 합친다: 그 칸에서 시작하는 음이 있으면 ㅇ, 이어지는 음만 있으면 ㅡ.

실행: uv run rhythm-stats 곡.mid  →  output/곡_리듬패턴.csv
"""

import argparse
import csv
import math
import sys
from collections import Counter
from fractions import Fraction
from pathlib import Path

from transcriber.midi_input import MidiLoadError, read_midi
from transcriber.rhythm import QuantizedNote
from transcriber.rhythm_patterns import ONSET, REST, TIE, index_of

SLOT_CHOICES = (4, 3, 12)  # 앞에서부터 맞는 것을 쓴다
DEFAULT_OUTPUT_DIR = Path("output")


def beat_patterns(notes: tuple[QuantizedNote, ...]) -> list[str]:
    """박마다 리듬 패턴을 만든다. 첫 박부터 마지막 음이 끝나는 박까지."""
    if not notes:
        return []
    last_beat = math.ceil(max(n.start_beats + n.duration_beats for n in notes))
    return [_pattern_of_beat(notes, beat) for beat in range(last_beat)]


def count_patterns(notes: tuple[QuantizedNote, ...]) -> Counter:
    """패턴별로 몇 번 나왔는지 센다."""
    return Counter(beat_patterns(notes))


def _pattern_of_beat(notes: tuple[QuantizedNote, ...], beat: int) -> str:
    start, end = Fraction(beat), Fraction(beat + 1)
    inside = [n for n in notes if n.start_beats < end and n.start_beats + n.duration_beats > start]
    slots = _slots_for(inside, start)
    cells = []
    for i in range(slots):
        at = start + Fraction(i, slots)
        if any(n.start_beats == at for n in inside):
            cells.append(ONSET)
        elif any(n.start_beats < at < n.start_beats + n.duration_beats for n in inside):
            cells.append(TIE)
        else:
            cells.append(REST)
    return "".join(cells)


def _slots_for(notes: list[QuantizedNote], beat_start: Fraction) -> int:
    """이 박 안의 시작·끝 위치가 모두 칸 경계에 오는 가장 앞의 칸 수."""
    points = {p - beat_start for n in notes for p in (n.start_beats, n.start_beats + n.duration_beats)}
    inside = [p for p in points if 0 < p < 1]
    for slots in SLOT_CHOICES:
        if all((p * slots).denominator == 1 for p in inside):
            return slots
    return SLOT_CHOICES[-1]  # 더 잘게 나뉜 박은 12칸으로 둔다(칸 경계가 아닌 위치는 가까운 칸에 들어가지 않고 빠짐)


def write_csv(rows: list[tuple[str, Counter]], path: Path) -> Path:
    """파트별 패턴 횟수를 CSV로 저장한다. 시트_행 = 구글 시트 '음길이 N개' 파일의 행 번호."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["파트", "칸수", "패턴", "시트_행", "횟수"])
        for part, counter in rows:
            for pattern, times in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
                writer.writerow([part, len(pattern), pattern, index_of(pattern) + 1, times])
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIDI 곡에 나온 한 박 리듬 패턴을 세어 CSV로 저장")
    parser.add_argument("midi", help="MIDI 파일(.mid, .midi)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="결과 폴더 (기본: output)")
    args = parser.parse_args(argv)
    try:
        song = read_midi(args.midi)
    except MidiLoadError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    rows = [(name, count_patterns(notes)) for name, notes in (("멜로디", song.melody), ("피아노", song.accompaniment))]
    rows = [(name, counter) for name, counter in rows if counter]
    path = write_csv(rows, Path(args.output_dir) / f"{Path(args.midi).stem}_리듬패턴.csv")
    for name, counter in rows:
        print(f"{name}: {sum(counter.values())}박, 서로 다른 패턴 {len(counter)}개")
    print(f"  저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
