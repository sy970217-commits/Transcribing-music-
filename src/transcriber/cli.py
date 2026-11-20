"""명령어 하나로 음원을 악보로 바꾸는 실행 파일.

사용법: uv run transcribe 노래.mp3 [--tempo 90] [--output-dir output]
"""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from transcriber.audio_io import AudioLoadError
from transcriber.midi_input import MidiLoadError, is_midi_file, read_midi
from transcriber.pitch import PitchDetectionError, detect_notes, save_midi
from transcriber.rhythm import estimate_tempo, quantize_notes
from transcriber.score import ScoreInfo, build_score, key_name_of, save_musicxml

DEFAULT_OUTPUT_DIR = Path("output")
EXIT_OK = 0
EXIT_ERROR = 1


@dataclass(frozen=True)
class TranscriptionResult:
    """변환 결과 요약."""

    musicxml_path: Path
    midi_path: Path | None  # MIDI 파일을 넣었을 때는 새로 만들지 않음
    tempo_bpm: float
    note_count: int
    key_name: str


def transcribe_file(
    audio_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    tempo_bpm: float | None = None,
    info: ScoreInfo = ScoreInfo(),
) -> TranscriptionResult:
    """음원 또는 MIDI 파일을 악보로 바꾼다."""
    if tempo_bpm is not None and tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")

    source = Path(audio_path)
    score_info = info if info.title else replace(info, title=source.stem)
    if is_midi_file(source):
        return _transcribe_midi(source, Path(output_dir), tempo_bpm, score_info)
    return _transcribe_audio(source, Path(output_dir), tempo_bpm, score_info)


def _transcribe_midi(
    source: Path, target_dir: Path, tempo_bpm: float | None, info: ScoreInfo
) -> TranscriptionResult:
    """MIDI → 악보. 멜로디 트랙이 있으면 맨 위 단으로 만든다."""
    song = read_midi(source)
    tempo = tempo_bpm if tempo_bpm is not None else song.tempo_bpm
    score = build_score(song.accompaniment, tempo, info, melody=song.melody)
    musicxml_path = save_musicxml(score, target_dir / f"{source.stem}.musicxml")
    return TranscriptionResult(
        musicxml_path=musicxml_path,
        midi_path=None,
        tempo_bpm=tempo,
        note_count=len(song.accompaniment) + len(song.melody),
        key_name=key_name_of(score),
    )


def _transcribe_audio(
    source: Path, target_dir: Path, tempo_bpm: float | None, info: ScoreInfo
) -> TranscriptionResult:
    """음원 → 음 찾기 → 박자 정리 → 악보 저장."""
    pitch_result = detect_notes(source)
    if not pitch_result.notes:
        raise ValueError(f"음원에서 음을 찾지 못했습니다: {source}")

    tempo = tempo_bpm if tempo_bpm is not None else estimate_tempo(source)
    quantized = quantize_notes(pitch_result.notes, tempo)
    score = build_score(quantized, tempo, info)

    midi_path = save_midi(pitch_result, target_dir / f"{source.stem}.mid")
    musicxml_path = save_musicxml(score, target_dir / f"{source.stem}.musicxml")
    return TranscriptionResult(
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        tempo_bpm=tempo,
        note_count=len(pitch_result.notes),
        key_name=key_name_of(score),
    )


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="transcribe",
        description="음원(mp3, wav 등)을 피아노 악보(MusicXML)로 바꿉니다.",
    )
    parser.add_argument("audio", help="변환할 음원 파일 또는 MIDI 파일(.mid, .midi)")
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
    parser.add_argument("--title", default="", help="악보 제목 (기본: 파일 이름)")
    parser.add_argument("--composer", default="", help="작곡가 이름")
    parser.add_argument("--lyricist", default="", help="작사가 이름")
    parser.add_argument(
        "--key",
        default=None,
        help="조성 직접 지정 (예: G, D, e). 지정하지 않으면 자동으로 찾음",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"변환 중: {args.audio} (처음 실행은 조금 오래 걸릴 수 있어요)")
    try:
        info = ScoreInfo(
            title=args.title,
            composer=args.composer,
            lyricist=args.lyricist,
            key_name=args.key,
        )
        result = transcribe_file(args.audio, args.output_dir, args.tempo, info)
    except (AudioLoadError, MidiLoadError, PitchDetectionError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_ERROR

    print(
        f"완료! 찾은 음 {result.note_count}개, 템포 {result.tempo_bpm:.0f} BPM, "
        f"조성 {result.key_name}"
    )
    print(f"  악보: {result.musicxml_path}")
    if result.midi_path is not None:
        print(f"  MIDI: {result.midi_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
