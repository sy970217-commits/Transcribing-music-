"""악보(MusicXML)를 MIDI로 바꾸는 모듈과 실행 명령.

사용법: uv run render 악보.musicxml [--output-dir output]
Finale 파일(.musx)은 Finale에서 "파일 → 내보내기 → MusicXML"로 저장한 뒤 넣는다.
"""

import argparse
import sys
from pathlib import Path

from music21 import converter, stream

SCORE_EXTENSIONS = frozenset({".musicxml", ".xml", ".mxl"})
DEFAULT_OUTPUT_DIR = Path("output")
EXIT_OK = 0
EXIT_ERROR = 1


class ScoreLoadError(Exception):
    """악보 파일을 읽을 수 없을 때 발생하는 오류."""


def load_score(path: str | Path) -> stream.Score:
    """MusicXML 악보 파일을 읽는다."""
    file_path = Path(path)
    if not file_path.is_file():
        raise ScoreLoadError(f"파일을 찾을 수 없습니다: {file_path}")
    if file_path.suffix.lower() not in SCORE_EXTENSIONS:
        hint = " Finale 파일은 '파일 → 내보내기 → MusicXML'로 저장해 주세요." if file_path.suffix.lower() == ".musx" else ""
        supported = ", ".join(sorted(SCORE_EXTENSIONS))
        raise ScoreLoadError(f"지원하지 않는 악보 형식입니다: {file_path.suffix} (지원: {supported}).{hint}")
    try:
        parsed = converter.parse(str(file_path))
    except Exception as error:
        raise ScoreLoadError(f"악보를 읽을 수 없습니다: {file_path} ({error})") from error
    if not parsed.recurse().notes:
        raise ScoreLoadError(f"악보에 음표가 없습니다: {file_path}")
    return parsed


def score_to_midi(score_path: str | Path, output_dir: str | Path = DEFAULT_OUTPUT_DIR) -> Path:
    """악보 파일을 MIDI 파일로 바꿔 저장한다. 템포 표시(♩=90 등)도 반영된다."""
    source = Path(score_path)
    score = load_score(source)
    midi_path = Path(output_dir) / f"{source.stem}.mid"
    midi_path.parent.mkdir(parents=True, exist_ok=True)
    score.write("midi", fp=str(midi_path))
    return midi_path


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="render",
        description="악보(MusicXML)를 MIDI 파일로 바꿉니다.",
    )
    parser.add_argument("score", help="변환할 악보 파일 (.musicxml, .xml, .mxl)")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="결과 파일을 저장할 폴더 (기본: output)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"변환 중: {args.score}")
    try:
        midi_path = score_to_midi(args.score, args.output_dir)
    except ScoreLoadError as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(f"완료! MIDI: {midi_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
