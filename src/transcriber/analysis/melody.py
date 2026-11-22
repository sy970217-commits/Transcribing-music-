"""분석기 I단계: 멜로디·가사. D단계에서 박에 맞춘 음 중 멜로디(한 줄 선율)를 고르고, 가사 글을 멜로디 음에 붙인다.

멜로디 고르기(맨 위 음 따라가기)
1. 같은 자리에서 시작한 음 중 가장 높은 음이 멜로디 후보다.
2. 앞 멜로디 음이 아직 울리고 있는데 후보가 그보다 낮으면 반주(긴 멜로디 음 아래 분산화음 등)로 보고 건너뛴다.
3. 멜로디가 쉬는 동안 반주만 나오면 반주 맨 위 음을 멜로디로 잘못 고를 수 있다. 그래서 쉰 뒤(틈이 있을 때)의 후보가
   바로 앞(한 마디쯤)에 나온 반주 음(멜로디로 고르지 않은 음)보다 높지 않으면 건너뛴다.
   또 쉬었든 아니든, 한 마디 안의 앞 멜로디 음보다 MAX_DROP 넘게 낮은 후보도 건너뛴다.
   음 인식(C단계)이 피아노의 긴 음을 짧게 끊는 일이 많아서 필요하다.
4. 멜로디 음이 겹치면 앞 음을 다음 음 시작에서 끊는다.

가사 붙이기
- 멜로디를 '구절'로 나눈다. 한 박 이상 쉬거나 두 박 이상 긴 음 뒤에서 나눈다
  (D단계가 1박 이하 쉼표를 앞 음에 붙여 늘리므로, 짧은 쉼은 긴 음으로 보인다).
  구절을 더 잘게 나눠도 가사는 앞 줄에 이어 붙으므로 괜찮다.
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

from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.lyrics import HOLD, parse_lyrics

RECENT_QUARTERS = 4  # 쉰 뒤 후보를 이만큼(4분음표 수) 앞까지 나온 음과 비교한다
MAX_DROP = 16  # 후보가 한 마디 안의 앞 멜로디 음보다 이만큼(반음 수) 넘게 낮으면 반주로 본다
PHRASE_END_BEATS = 2  # 이 박 수 이상 긴 음 뒤에서 구절을 나눈다


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


def accompaniment_ceiling(notes: tuple[RhythmNote, ...], melody: list[MelodyNote], start: Fraction) -> int | None:
    """start 앞 RECENT_QUARTERS 안에 시작한, 멜로디가 아닌 음 중 가장 높은 음."""
    chosen = {(n.start, n.pitch) for n in melody}
    under = [n.pitch for n in notes
             if start - RECENT_QUARTERS <= n.start < start and (n.start, n.pitch) not in chosen]
    return max(under, default=None)


def is_accompaniment(candidate: RhythmNote, melody: list[MelodyNote], notes: tuple[RhythmNote, ...]) -> bool:
    if not melody:
        return False
    last = melody[-1]
    if last.start + last.length > candidate.start:
        return candidate.pitch < last.pitch
    if candidate.start - last.start <= RECENT_QUARTERS and candidate.pitch < last.pitch - MAX_DROP:
        return True
    if last.start + last.length == candidate.start:
        return False
    ceiling = accompaniment_ceiling(notes, melody, candidate.start)
    return ceiling is not None and candidate.pitch <= ceiling


def pick_melody(notes: tuple[RhythmNote, ...]) -> tuple[MelodyNote, ...]:
    melody: list[MelodyNote] = []
    for candidate in top_notes(notes):
        if is_accompaniment(candidate, melody, notes):
            continue
        if melody and melody[-1].start + melody[-1].length > candidate.start:
            last = melody[-1]
            melody[-1] = MelodyNote(last.pitch, last.start, candidate.start - last.start)
        melody.append(MelodyNote(candidate.pitch, candidate.start, candidate.length))
    return tuple(melody)


def phrase_indexes(melody: tuple[MelodyNote, ...], beat: Fraction) -> list[int]:
    """구절 첫 음의 번호들. 앞 음 뒤에 한 박 이상 쉬거나, 앞 음이 PHRASE_END_BEATS박 이상 길면 새 구절."""
    def starts_phrase(i: int) -> bool:
        before = melody[i - 1]
        return melody[i].start - (before.start + before.length) >= beat or before.length >= PHRASE_END_BEATS * beat
    return [i for i in range(len(melody)) if i == 0 or starts_phrase(i)]


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
