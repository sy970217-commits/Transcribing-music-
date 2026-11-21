"""명령어 하나로 음원을 악보로 바꾸는 실행 파일.

사용법: uv run transcribe 노래.mp3 [--tempo 90] [--output-dir output]
"""

import argparse
import sys
from dataclasses import dataclass, replace
from pathlib import Path

from transcriber.audio_io import AudioLoadError, validate_audio_path
from transcriber.midi_input import MidiLoadError, is_midi_file, read_midi
from transcriber.pitch import Note, PitchDetectionError, detect_notes, save_midi
from transcriber.lyrics import LyricsError, read_lyrics_file
from transcriber.rhythm import QuantizedNote, estimate_tempo, quantize_notes
from transcriber.score import ScoreInfo, build_score, key_name_of, save_musicxml
from transcriber.vocal_melody import extract_vocal_parts

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
    voice_found: bool | None = None  # --vocals를 쓴 경우에만 True/False
    melody_note_count: int = 0
    lyrics_left_over: int = 0  # 멜로디 음표보다 가사 음절이 많아 남은 수


def transcribe_file(
    audio_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    tempo_bpm: float | None = None,
    info: ScoreInfo = ScoreInfo(),
    vocals: bool = False,
) -> TranscriptionResult:
    """음원 또는 MIDI 파일을 악보로 바꾼다. vocals=True면 노래 멜로디 단을 따로 만든다."""
    if tempo_bpm is not None and tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")

    source = Path(audio_path)
    score_info = info if info.title else replace(info, title=source.stem)
    if is_midi_file(source):
        result = _transcribe_midi(source, Path(output_dir), tempo_bpm, score_info)
    else:
        result = _transcribe_audio(source, Path(output_dir), tempo_bpm, score_info, vocals)
    return _with_lyrics_summary(result, score_info)


def _with_lyrics_summary(result: TranscriptionResult, info: ScoreInfo) -> TranscriptionResult:
    """음표가 모자라 붙이지 못한 가사 음절 수를 결과에 적는다."""
    left_over = max(0, len(info.lyrics) - result.melody_note_count)
    return replace(result, lyrics_left_over=left_over)


def _melody_note_count(melody: tuple[QuantizedNote, ...]) -> int:
    """악보에 그려질 멜로디 음표 수(같은 박에 시작하는 음은 한 음표로 묶임)."""
    return len({n.start_beats for n in melody})


def _transcribe_midi(
    source: Path, target_dir: Path, tempo_bpm: float | None, info: ScoreInfo
) -> TranscriptionResult:
    """MIDI → 악보. 멜로디 트랙이 있으면 맨 위 단으로 만든다."""
    song = read_midi(source)
    tempo = tempo_bpm if tempo_bpm is not None else song.tempo_bpm
    # --tempo로 빠르기를 직접 정하면 곡 전체를 그 빠르기 하나로 쓴다
    tempo_changes = song.tempo_changes if tempo_bpm is None else ()
    score = build_score(
        song.accompaniment,
        tempo,
        info,
        time_signatures=song.time_signatures,
        melody=song.melody,
        tempo_changes=tempo_changes,
        pedals=song.pedals,
    )
    musicxml_path = save_musicxml(score, target_dir / f"{source.stem}.musicxml")
    return TranscriptionResult(
        musicxml_path=musicxml_path,
        midi_path=None,
        tempo_bpm=tempo,
        note_count=len(song.accompaniment) + len(song.melody),
        key_name=key_name_of(score),
        melody_note_count=_melody_note_count(song.melody),
    )


def _transcribe_audio(
    source: Path, target_dir: Path, tempo_bpm: float | None, info: ScoreInfo, vocals: bool
) -> TranscriptionResult:
    """음원 → (목소리 분리) → 음 찾기 → 박자 정리 → 악보 저장."""
    validate_audio_path(source)
    melody_notes: tuple[Note, ...] = ()
    piano_source = source
    voice_found = None
    if vocals:
        parts = extract_vocal_parts(source, target_dir / f"{source.stem}_stems")
        voice_found = parts.has_voice
        melody_notes = parts.melody
        piano_source = parts.accompaniment_path

    pitch_result = detect_notes(piano_source)
    if not pitch_result.notes and not melody_notes:
        raise ValueError(f"음원에서 음을 찾지 못했습니다: {source}")

    tempo = tempo_bpm if tempo_bpm is not None else estimate_tempo(source)
    melody = quantize_notes(melody_notes, tempo)
    score = build_score(quantize_notes(pitch_result.notes, tempo), tempo, info, melody=melody)

    midi_path = save_midi(pitch_result, target_dir / f"{source.stem}.mid")
    musicxml_path = save_musicxml(score, target_dir / f"{source.stem}.musicxml")
    return TranscriptionResult(
        musicxml_path=musicxml_path,
        midi_path=midi_path,
        tempo_bpm=tempo,
        note_count=len(pitch_result.notes) + len(melody_notes),
        key_name=key_name_of(score),
        voice_found=voice_found,
        melody_note_count=_melody_note_count(melody),
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
    parser.add_argument(
        "--time-signature",
        default=None,
        help="박자표 직접 지정 (예: 3/4, 6/8). 음원은 기본 4/4, MIDI는 파일에 적힌 박자표를 씀",
    )
    parser.add_argument(
        "--vocals",
        action="store_true",
        help="사람이 부른 노래 녹음일 때: 목소리를 분리해 맨 위에 멜로디 단을 만듦 (몇 분 걸림)",
    )
    parser.add_argument(
        "--lyrics",
        default=None,
        help="가사 글 파일(.txt). 멜로디 음표에 한 글자씩 붙임. 길게 부르는 곳은 '-'",
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
            lyrics=read_lyrics_file(args.lyrics) if args.lyrics else (),
            time_signature=args.time_signature,
        )
        result = transcribe_file(args.audio, args.output_dir, args.tempo, info, args.vocals)
    except (AudioLoadError, MidiLoadError, LyricsError, PitchDetectionError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_ERROR

    if args.lyrics:
        print(f"가사: 음절 {len(info.lyrics)}개 → 멜로디 음표 {result.melody_note_count}개")
        if result.lyrics_left_over:
            print(f"알림: 음표가 모자라 가사 {result.lyrics_left_over}자가 남았어요. 가사 파일을 확인해 주세요.")

    if result.voice_found is False:
        print(
            "알림: 사람 목소리를 찾지 못해 멜로디 단 없이 만들었어요. "
            "Finale 재생 음원이라면 MIDI 파일을 넣어 보세요."
        )
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
