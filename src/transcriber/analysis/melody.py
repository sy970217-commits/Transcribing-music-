"""분석기 I단계: 멜로디·가사. D단계에서 박에 맞춘 음 중 멜로디(한 줄 선율)를 고르고, 가사 글을 멜로디 음에 붙인다.

멜로디 고르기(맨 위 음 따라가기)
1. 같은 자리에서 시작한 음 중 가장 높은 음이 멜로디 후보다.
2. 앞 멜로디 음이 아직 울리고 있는데 후보가 그보다 낮으면 반주(긴 멜로디 음 아래 분산화음 등)로 보고 건너뛴다.
3. 멜로디가 쉬는 동안 반주만 나오면 반주 맨 위 음을 멜로디로 잘못 고를 수 있다. 그래서 쉰 뒤의 후보가
   최근 멜로디 음들보다 REGISTER_DROP 넘게 낮으면 건너뛴다.
4. 멜로디 음이 겹치면 앞 음을 다음 음 시작에서 끊는다.

가사 붙이기
- 멜로디를 쉼(한 박 이상)으로 '구절'로 나눈다.
- 가사 한 줄이 끝나면 다음 줄은 다음 구절 처음부터 붙인다. 줄이 구절보다 길면 다음 구절로 넘친다.
- 가사 쓰는 법은 transcriber.lyrics와 같다("-"는 앞 글자 이어 부르기).
- 음원에서 가사를 알아듣지는 않는다(말소리 인식 AI가 필요). 가사 글은 사용자가 준다.

실행: uv run melody 곡.wav [--lyrics 가사.txt]
"""

import argparse
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from statistics import median

from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.lyrics import HOLD, parse_lyrics

REGISTER_DROP = 10  # 쉰 뒤 후보가 최근 멜로디보다 이만큼(반음 수) 넘게 낮으면 반주로 본다
RECENT_NOTES = 4  # '최근 멜로디'로 볼 음 수


@dataclass(frozen=True)
class MelodyNote:
    """멜로디 음 하나. 위치·길이는 4분음표 단위. lyric은 붙은 글자("" 이면 앞 글자를 이어 부름, None이면 없음)."""

    pitch: int
    start: Fraction
    length: Fraction
    lyric: str | None = None


@dataclass(frozen=True)
class MelodyResult:
    notes: tuple[MelodyNote, ...]
    phrase_starts: tuple[Fraction, ...]  # 구절이 시작하는 위치들


def top_notes(notes: tuple[RhythmNote, ...]) -> list[RhythmNote]:
    """시작 위치마다 가장 높은 음(시작 위치 순)."""
    tops: dict[Fraction, RhythmNote] = {}
    for note in notes:
        if note.start not in tops or note.pitch > tops[note.start].pitch:
            tops[note.start] = note
    return [tops[start] for start in sorted(tops)]


def is_accompaniment(candidate: RhythmNote, melody: list[MelodyNote]) -> bool:
    if not melody:
        return False
    last = melody[-1]
    if last.start + last.length > candidate.start:
        return candidate.pitch < last.pitch
    recent = median(n.pitch for n in melody[-RECENT_NOTES:])
    return candidate.pitch < recent - REGISTER_DROP


def pick_melody(notes: tuple[RhythmNote, ...]) -> tuple[MelodyNote, ...]:
    melody: list[MelodyNote] = []
    for candidate in top_notes(notes):
        if is_accompaniment(candidate, melody):
            continue
        if melody and melody[-1].start + melody[-1].length > candidate.start:
            last = melody[-1]
            melody[-1] = MelodyNote(last.pitch, last.start, candidate.start - last.start)
        melody.append(MelodyNote(candidate.pitch, candidate.start, candidate.length))
    return tuple(melody)


def phrase_indexes(melody: tuple[MelodyNote, ...], rest: Fraction) -> list[int]:
    """구절 첫 음의 번호들. 앞 음이 끝나고 rest 이상 쉬면 새 구절."""
    return [i for i, note in enumerate(melody)
            if i == 0 or note.start - (melody[i - 1].start + melody[i - 1].length) >= rest]


def place_lyrics(note_count: int, phrase_firsts: list[int], lines: list[tuple[str, ...]]) -> list[str | None]:
    """음마다 붙을 글자. 줄마다 다음 구절 처음부터 붙인다."""
    lyrics: list[str | None] = [None] * note_count
    position = 0
    for syllables in lines:
        position = next((p for p in phrase_firsts if p >= position), position)
        for syllable in syllables:
            if position >= note_count:
                return lyrics
            lyrics[position] = syllable
            position += 1
    return lyrics


def analyze_melody(rhythm: RhythmResult, lyrics_text: str | None = None) -> MelodyResult:
    """박에 맞춘 음 → 멜로디 음(가사 글이 있으면 글자도 붙임)과 구절 시작 위치."""
    melody = pick_melody(rhythm.notes)
    firsts = phrase_indexes(melody, rhythm.beat_quarters)
    if lyrics_text:
        lines = [parse_lyrics(line) for line in lyrics_text.splitlines()]
        words = place_lyrics(len(melody), firsts, [line for line in lines if line])
        melody = tuple(MelodyNote(n.pitch, n.start, n.length, w) for n, w in zip(melody, words))
    return MelodyResult(melody, tuple(melody[i].start for i in firsts))


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import RhythmError, quantize_notes
    from transcriber.audio_io import AudioLoadError
    from transcriber.lyrics import LyricsError, read_lyrics_file
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원에서 멜로디를 고르고 가사를 붙인다 (분석기 I단계)")
    parser.add_argument("audio", help="음원 파일")
    parser.add_argument("--lyrics", help="가사 글 파일(UTF-8). 한 줄이 한 구절")
    args = parser.parse_args(argv)
    try:
        text = None
        if args.lyrics:
            read_lyrics_file(args.lyrics)  # 없는 파일·빈 파일이면 여기서 오류
            text = Path(args.lyrics).read_text(encoding="utf-8")
        beats = analyze_beats(args.audio)
        result = analyze_melody(quantize_notes(recognize_notes(Path(args.audio))["mix"], beats), text)
    except (AudioLoadError, PitchDetectionError, RhythmError, LyricsError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"멜로디 음 {len(result.notes)}개, 구절 {len(result.phrase_starts)}개 (위치는 4분음표 단위)")
    for note in result.notes:
        word = "" if note.lyric is None else ("  (이어 부름)" if note.lyric == HOLD else f"  {note.lyric}")
        print(f"  {note.start}: 음 {note.pitch} 길이 {note.length}{word}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
