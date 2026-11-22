"""분석표: 음원을 B~I단계로 분석한 결과를 한곳에 모은다. 악보는 이 분석표를 보고 만든다.

분석표에 담는 것(위치·길이는 모두 4분음표 단위)
- beats: 박·박자·빠르기·못갖춘마디(B)
- rhythm: 박에 맞춘 음(C·D)
- harmony: 화음 구간(E)
- key: 조 구간(F)
- structure: 곡 구조(G)
- expression: 셈여림·페달(H)
- melody: 멜로디 음·가사·구절(I)
- separation: 소리 분리 결과(A). --separate를 줄 때만 한다(몇 분 걸림)
  - 나누면 트랙마다 음을 찾아 합치고, 목소리 트랙이 있으면 멜로디는 목소리 트랙에서 찾는다(셋잇단 없이 정리).
  - accompaniment: 목소리 트랙을 뺀 반주 음. 악보의 피아노 단에 멜로디가 또 들어가지 않게 한다.
  - 안 나누면 섞인 소리 전체(mix)에서 음을 찾는다.

분석표는 JSON 파일로도 저장해서, 악보가 이상할 때 어느 단계가 틀렸는지 찾기 쉽게 한다.

실행: uv run analyze 곡.wav [--lyrics 가사.txt] [--output 폴더] [--separate]
"""

import argparse
import dataclasses
import json
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.expression import ExpressionResult
from transcriber.analysis.harmony import HarmonyResult
from transcriber.analysis.melody import MelodyResult
from transcriber.analysis.rhythm import RhythmResult
from transcriber.analysis.separation import Separation
from transcriber.analysis.structure import StructureResult
from transcriber.analysis.tonality import KeyResult

DEFAULT_OUTPUT_DIR = Path("output")


@dataclass(frozen=True)
class AnalysisSheet:
    beats: BeatAnalysis
    rhythm: RhythmResult
    harmony: HarmonyResult
    key: KeyResult
    structure: StructureResult
    expression: ExpressionResult
    melody: MelodyResult
    separation: Separation | None = None
    accompaniment: RhythmResult | None = None  # 목소리를 뺀 반주 음(목소리 트랙을 나눴을 때만)


def analyze_song(
    audio_path: str | Path, lyrics_text: str | None = None, separation: Separation | None = None
) -> AnalysisSheet:
    """음원 → 분석표. 단계 순서대로 앞 단계 결과를 다음 단계에 넘긴다. separation은 A단계 결과(없으면 섞인 소리)."""
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.expression import analyze_expression, measure_sounds
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.melody import analyze_melody
    from transcriber.analysis.notes import merge_tracks, recognize_notes
    from transcriber.analysis.rhythm import quantize_notes
    from transcriber.analysis.structure import analyze_structure
    from transcriber.analysis.tonality import analyze_key

    beats = analyze_beats(audio_path)
    found = recognize_notes(Path(audio_path), separation)
    notes = merge_tracks(found)
    rhythm = quantize_notes(notes, beats)
    vocals = found.get("vocals")
    melody_source = quantize_notes(vocals, beats, allow_triplets=False) if vocals else rhythm
    backing = {track: found_notes for track, found_notes in found.items() if track != "vocals"}
    accompaniment = quantize_notes(merge_tracks(backing), beats) if vocals else None
    harmony = analyze_harmony(rhythm, beats)
    sounds = measure_sounds(audio_path, notes, beats)
    return AnalysisSheet(
        beats=beats,
        rhythm=rhythm,
        harmony=harmony,
        key=analyze_key(rhythm, harmony, beats),
        structure=analyze_structure(rhythm, beats),
        expression=analyze_expression(rhythm, harmony, beats, sounds),
        melody=analyze_melody(melody_source, lyrics_text),
        separation=separation,
        accompaniment=accompaniment,
    )


def to_plain(value):
    """분석표를 JSON으로 적을 수 있는 값(dict·list·str·수)으로 바꾼다. 분수는 "3/2" 같은 글자로."""
    if dataclasses.is_dataclass(value):
        return {f.name: to_plain(getattr(value, f.name)) for f in dataclasses.fields(value)}
    if isinstance(value, (Fraction, Path)):
        return str(value)
    if isinstance(value, (tuple, list)):
        return [to_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): to_plain(v) for k, v in value.items()}
    return value


def save_sheet(sheet: AnalysisSheet, path: str | Path) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(to_plain(sheet), ensure_ascii=False, indent=1), encoding="utf-8")
    return target


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.rhythm import RhythmError
    from transcriber.analysis.separation import SeparationError, separate
    from transcriber.audio_io import AudioLoadError
    from transcriber.lyrics import LyricsError, read_lyrics_file
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원을 분석해 분석표(JSON)를 만든다 (B~I단계 모두)")
    parser.add_argument("audio", help="음원 파일")
    parser.add_argument("--lyrics", help="가사 글 파일(UTF-8). 한 줄이 한 구절")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT_DIR), help="분석표를 저장할 폴더")
    parser.add_argument("--separate", action="store_true", help="먼저 악기별로 소리를 나누기(A단계, 몇 분 걸림)")
    args = parser.parse_args(argv)
    try:
        text = None
        if args.lyrics:
            read_lyrics_file(args.lyrics)  # 없는 파일·빈 파일이면 여기서 오류
            text = Path(args.lyrics).read_text(encoding="utf-8")
        separation = separate(args.audio, args.output) if args.separate else None
        sheet = analyze_song(args.audio, text, separation)
    except (AudioLoadError, SeparationError, PitchDetectionError, RhythmError, LyricsError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    path = save_sheet(sheet, Path(args.output) / f"{Path(args.audio).stem}_분석표.json")
    print(f"분석표: {path}")
    print(f"  박자 {sheet.beats.time_signature}, 빠르기 {sheet.beats.tempo_bpm:.0f}, 음 {len(sheet.rhythm.notes)}개")
    print(f"  화음 {len(sheet.harmony.chords)}구간, 조 {', '.join(k.name for k in sheet.key.keys) or '없음'}")
    print(f"  구조 {' '.join(s.label for s in sheet.structure.sections) or '없음'}")
    print(f"  셈여림 {len(sheet.expression.dynamics)}곳, 페달 {len(sheet.expression.pedals)}번")
    print(f"  멜로디 음 {len(sheet.melody.notes)}개, 구절 {len(sheet.melody.phrase_starts)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
