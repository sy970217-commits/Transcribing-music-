"""악보(MusicXML)를 MIDI와 오디오(wav)로 바꾸는 모듈과 실행 명령.

사용법: uv run render 악보.musicxml [--audio] [--output-dir output]
Finale 파일(.musx)은 Finale에서 "파일 → 내보내기 → MusicXML"로 저장한 뒤 넣는다.
오디오는 FluidSynth(연주 프로그램)와 사운드폰트(악기 소리 모음)로 만든다.
"""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

from music21 import converter, stream

SCORE_EXTENSIONS = frozenset({".musicxml", ".xml", ".mxl"})
DEFAULT_OUTPUT_DIR = Path("output")
DEFAULT_SOUNDFONT = Path("soundfonts/MuseScore_General.sf3")
FLUIDSYNTH_FALLBACK_PATHS = (Path("/opt/homebrew/bin/fluidsynth"), Path("/usr/local/bin/fluidsynth"))
AUDIO_SAMPLE_RATE = 44100
AUDIO_GAIN = "0.5"  # FluidSynth 기본값(0.2)은 소리가 작아서 조금 키운다
RENDER_TIMEOUT_SECONDS = 600
EXIT_OK = 0
EXIT_ERROR = 1


class ScoreLoadError(Exception):
    """악보 파일을 읽을 수 없을 때 발생하는 오류."""


class AudioRenderError(Exception):
    """오디오를 만들 수 없을 때 발생하는 오류."""


def find_fluidsynth() -> Path | None:
    found = shutil.which("fluidsynth")
    if found:
        return Path(found)
    return next((p for p in FLUIDSYNTH_FALLBACK_PATHS if p.is_file()), None)


def midi_to_audio(midi_path: str | Path, soundfont: str | Path = DEFAULT_SOUNDFONT) -> Path:
    """MIDI를 사운드폰트의 악기 소리로 연주해 같은 이름의 wav 파일로 저장한다."""
    source = Path(midi_path)
    font = Path(soundfont)
    fluidsynth = find_fluidsynth()
    if fluidsynth is None:
        raise AudioRenderError("FluidSynth가 없어요. 터미널에서 'brew install fluid-synth'로 설치해 주세요.")
    if not font.is_file():
        raise AudioRenderError(f"사운드폰트를 찾을 수 없습니다: {font}")

    wav_path = source.with_suffix(".wav")
    command = [
        str(fluidsynth), "-n", "-i", "-q",
        "-g", AUDIO_GAIN,
        "-r", str(AUDIO_SAMPLE_RATE),
        "-F", str(wav_path),
        str(font), str(source),
    ]
    try:
        result = subprocess.run(command, capture_output=True, text=True, timeout=RENDER_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as error:
        raise AudioRenderError(f"오디오를 만드는 데 너무 오래 걸려 멈췄어요: {source}") from error
    if result.returncode != 0 or not wav_path.is_file() or wav_path.stat().st_size == 0:
        detail = (result.stderr or result.stdout).strip()[-300:]
        raise AudioRenderError(f"오디오를 만들지 못했어요: {source} ({detail})")
    return wav_path


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
        description="악보(MusicXML)를 MIDI 파일과 오디오(wav)로 바꿉니다.",
    )
    parser.add_argument("score", help="변환할 악보 파일 (.musicxml, .xml, .mxl)")
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_OUTPUT_DIR),
        help="결과 파일을 저장할 폴더 (기본: output)",
    )
    parser.add_argument("--audio", action="store_true", help="악기 소리로 연주한 wav 파일도 만듦")
    parser.add_argument(
        "--soundfont",
        default=str(DEFAULT_SOUNDFONT),
        help=f"악기 소리 파일 (기본: {DEFAULT_SOUNDFONT})",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print(f"변환 중: {args.score}")
    try:
        midi_path = score_to_midi(args.score, args.output_dir)
        wav_path = midi_to_audio(midi_path, args.soundfont) if args.audio else None
    except (ScoreLoadError, AudioRenderError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return EXIT_ERROR
    print(f"완료! MIDI: {midi_path}")
    if wav_path is not None:
        print(f"  오디오: {wav_path}")
    return EXIT_OK


if __name__ == "__main__":
    sys.exit(main())
