"""명령어 하나로 음원을 악보로 바꾸는 실행 파일.

사용법: uv run transcribe 노래.mp3 [--tempo 90] [--output-dir output]
"""

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from transcriber.audio_io import AudioLoadError
from transcriber.pitch import PitchDetectionError, detect_notes, save_midi
from transcriber.rhythm import estimate_tempo, quantize_notes
from transcriber.score import build_score, save_musicxml

DEFAULT_OUTPUT_DIR = Path("output")
EXIT_OK = 0
EXIT_ERROR = 1


@dataclass(frozen=True)
class TranscriptionResult:
    """변환 결과 요약."""

    musicxml_path: Path
    midi_path: Path
    tempo_bpm: float
    note_count: int


def transcribe_file(
    audio_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    tempo_bpm: float | None = None,
) -> TranscriptionResult:
    """음원 → 음 찾기 → 박자 정리 → 악보 저장을 차례로 실행한다."""
    if tempo_bpm is not None and tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")

    source = Path(audio_path)
    target_dir = Path(output_dir)

    pitch_result = detect_notes(source)
    if not pitch_result.notes:
        raise ValueError(f"음원에서 음을 찾지 못했습니다: {source}")

    tempo = tempo_bpm if tempo_bpm is not None else estimate_tempo(source)
    quantized = quantize_notes(pitch_result.notes, tempo)
    score = build_score(quantized, tempo)

    midi_path = save_midi(pitch_result, target_dir / f"{source.stem}.mid")
    musicxml_path = save_musicxml(score, target_dir / f"{source.stem}.musicxml")
    return TranscriptionResult(
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        tempo_bpm=tempo,
        note_count=len(pitch_result.notes),
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="음원(mp3, wav 등)을 피아노 악보(MusicXML)로 바꿉니다.",
    )
    parser.add_argument("audio", help="변환할 음원 파일")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="결과 파일을 저장할 폴더 (기본: output)",
    )
    parser.add_argument(
        "--tempo",
        type=float,
        default=None,
        help="템포(BPM)를 직접 지정. 지정하지 않으면 자동으로 찾음",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"변환 중: {args.audio} (처음 실행은 조금 오래 걸릴 수 있어요)")
    try:
        result = transcribe_file(args.audio, args.output_dir, args.tempo)
    except (AudioLoadError, PitchDetectionError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(f"완료! 찾은 음 {result.note_count}개, 템포 {result.tempo_bpm:.0f} BPM")
    print(f"  악보: {result.musicxml_path}")
    print(f"  MIDI: {result.midi_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
