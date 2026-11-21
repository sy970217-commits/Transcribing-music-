"""곡에서 실제로 같이 울린 음 묶음을 모아 세는 모듈.

어떤 음이든 새로 시작하는 순간마다, 그때 울리고 있는 음들을 하나의 묶음으로 본다.
묶음은 두 가지로 적는다(pitch_sets와 같은 규칙).
- 88건반 묶음: 가장 낮은 음을 0으로 두고 반음 단위 거리 (예: 도3·미4·솔4 → 0,16,19)
- 12음 묶음: 옥타브를 무시하고 맨 아래 음을 0으로 둔 모양 (예: 0,4,7)
  + 맨 아래 음 이름(0=도 … 11=시)과 구글 시트 '음높이 N개' 파일에서의 번호(맨 아래 음 블록 포함)

실행: uv run chord-stats 곡.mid  →  output/곡_음높이묶음.csv
"""

import argparse
import csv
import sys
from collections import Counter
from pathlib import Path

from transcriber.midi_input import MidiLoadError, read_midi
from transcriber.pitch_sets import PITCH_CLASSES, from_midi, index_of, pitch_class_set, sheet_number
from transcriber.rhythm import QuantizedNote

DEFAULT_OUTPUT_DIR = Path("output")


def sounding_sets(notes: tuple[QuantizedNote, ...]) -> list[tuple[int, ...]]:
    """음이 새로 시작하는 순간마다 울리고 있는 MIDI 음 번호 묶음(낮은 음부터)."""
    onsets = sorted({n.start_beats for n in notes})
    return [
        tuple(sorted({n.pitch for n in notes if n.start_beats <= t < n.start_beats + n.duration_beats}))
        for t in onsets
    ]


def count_sets(notes: tuple[QuantizedNote, ...]) -> Counter:
    """88건반 묶음별로 몇 번 나왔는지 센다. 피아노 범위 밖 음이 섞인 묶음은 뺀다."""
    counter: Counter = Counter()
    for pitches in sounding_sets(notes):
        try:
            key = (from_midi(pitches), pitch_class_set(pitches), pitches[0] % PITCH_CLASSES, sheet_number(pitches))
            counter[key] += 1
        except ValueError:
            continue
    return counter


def write_csv(rows: list[tuple[str, Counter]], path: Path) -> Path:
    """파트별 묶음 횟수를 CSV로 저장한다."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(
            ["파트", "음개수", "88건반_묶음", "88건반_번호", "12음_묶음", "12음_맨아래", "12음_시트번호", "횟수"]
        )
        for part, counter in rows:
            for (keys_set, class_set, lowest, number), times in sorted(counter.items(), key=lambda item: (-item[1], item[0])):
                writer.writerow(
                    [
                        part,
                        len(keys_set),
                        ",".join(map(str, keys_set)),
                        index_of(keys_set) + 1,
                        ",".join(map(str, class_set)),
                        lowest,
                        number,
                        times,
                    ]
                )
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="MIDI 곡에서 같이 울린 음 묶음을 세어 CSV로 저장")
    parser.add_argument("midi", help="MIDI 파일(.mid, .midi)")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="결과 폴더 (기본: output)")
    args = parser.parse_args(argv)
    try:
        song = read_midi(args.midi)
    except MidiLoadError as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    parts = (("멜로디", song.melody), ("피아노", song.accompaniment))
    rows = [(name, count_sets(notes)) for name, notes in parts]
    rows = [(name, counter) for name, counter in rows if counter]
    path = write_csv(rows, Path(args.output_dir) / f"{Path(args.midi).stem}_음높이묶음.csv")
    for name, counter in rows:
        print(f"{name}: {sum(counter.values())}번, 서로 다른 묶음 {len(counter)}개")
    print(f"  저장: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
