"""분석기 D단계: 리듬. C단계에서 찾은 음(초 단위 시작·끝)을 B단계의 박에 맞춰 악보에 쓸 위치·길이로 바꾼다.

- 위치·길이는 4분음표 단위 분수(1 = 4분음표, 1/2 = 8분음표, 1/3 = 셋잇단 8분음표, 3/2 = 점4분음표).
  0은 곡의 첫 박(못갖춘마디가 있으면 그 시작).
- 박마다 그 안의 음 시작들을 보고 박을 몇 칸으로 나눌지 고른다. 단순한 나눔(1→2→3→4칸)부터 시험해
  모든 음이 칸에 가깝게 맞는 첫 나눔을 쓴다. 그래서 8분음표와 셋잇단이 한 곡에 섞여도 박마다 따로 맞춘다.
  6/8처럼 한 박이 셋으로 나뉘는 박자는 1→3→6칸을 쓴다.
- 빠르기가 바뀌어도 박 위치(초)를 따라가므로 그대로 맞는다.

실행: uv run rhythm 곡.wav
"""

import argparse
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from transcriber.analysis.beats import BeatAnalysis, analyze_beats
from transcriber.audio_io import AudioLoadError
from transcriber.pitch import Note, PitchDetectionError

SIMPLE_DIVISIONS = (1, 2, 3, 4)  # 4분음표 박: 그대로, 8분, 셋잇단, 16분
COMPOUND_DIVISIONS = (1, 3, 6)  # 점4분음표 박(6/8 등): 그대로, 8분, 16분
FIT_TOLERANCE = 0.07  # 박 길이 대비 이만큼 안이면 칸에 맞는다고 본다
EARLY_SHARE = 0.125  # 박보다 이만큼(박 길이 대비) 일찍 시작한 음은 그 박의 첫 칸으로 본다
# 피아노 소리는 서서히 작아져 음 끝이 일찍 잡힌다. 가까운 음역(반음 9개 안)의 다음 음이 1박 안에 시작하면
# 그 음까지 늘린다(실제_입력 길이_정확도 평균 0.42→0.71). 1박보다 긴 쉼표는 남는다
NEARBY_SEMITONES = 9
FILL_GAP_BEATS = 1.0
SAME_TIME_BEATS = 0.2  # 이보다 가까이 시작한 음은 같이 누른 음(화음)으로 본다


class RhythmError(ValueError):
    """리듬을 정리할 수 없을 때(박이 너무 적음 등)."""


@dataclass(frozen=True)
class RhythmNote:
    """악보에 쓸 음 하나. start·length는 4분음표 단위."""

    pitch: int
    start: Fraction
    length: Fraction
    velocity: int


@dataclass(frozen=True)
class RhythmResult:
    notes: tuple[RhythmNote, ...]
    time_signature: str
    beat_quarters: Fraction  # 한 박이 4분음표 몇 개인지(6/8은 3/2)


def beat_quarters_of(beats: BeatAnalysis) -> Fraction:
    if beats.pulses_per_beat == 3:
        return Fraction(3, 2)
    return Fraction(4, int(beats.time_signature.split("/")[1]))


def beat_number(times: np.ndarray, beat_times: np.ndarray, numbers: np.ndarray | None = None) -> np.ndarray:
    """초 → 몇 번째 박인지(소수). numbers는 찾은 박마다의 박 번호(없으면 0, 1, 2…).
    첫 박 앞·마지막 박 뒤는 가장 가까운 박 간격으로 늘린다."""
    index = np.arange(len(beat_times), dtype=float) if numbers is None else numbers
    inside = np.interp(times, beat_times, index)
    first_rate = (index[1] - index[0]) / (beat_times[1] - beat_times[0])
    last_rate = (index[-1] - index[-2]) / (beat_times[-1] - beat_times[-2])
    before = index[0] + (times - beat_times[0]) * first_rate
    after = index[-1] + (times - beat_times[-1]) * last_rate
    return np.where(times < beat_times[0], before, np.where(times > beat_times[-1], after, inside))


def counted_beats(beats: BeatAnalysis, beat_times: np.ndarray) -> np.ndarray:
    """찾은 박마다 '곡 첫 박부터 몇 번째 박인지'. 마디 첫 박마다 번호를 다시 맞춘다.
    빠르기가 바뀌는 곳에서 박을 하나 더(덜) 찾아도 그 마디 안에서만 틀리고, 다음 마디부터는 바로잡힌다."""
    if not beats.downbeats:
        return np.arange(len(beat_times), dtype=float)
    bars = sorted({int(np.argmin(np.abs(beat_times - t))) for t in beats.downbeats})
    per_bar, first = beats.beats_per_bar, beats.pickup_beats
    numbers = np.arange(len(beat_times), dtype=float) - bars[0] + first  # 첫 마디 앞(못갖춘마디)
    for k, (bar, next_bar) in enumerate(zip(bars, bars[1:])):
        count = next_bar - bar  # 이 마디에서 찾은 박 수(보통 per_bar)
        numbers[bar:next_bar] = first + k * per_bar + np.arange(count) * per_bar / count
    numbers[bars[-1]:] = first + (len(bars) - 1) * per_bar + np.arange(len(beat_times) - bars[-1])
    return numbers


def choose_division(offsets: list[float], divisions: tuple[int, ...]) -> int:
    """박 안 위치(0~1)들에 가장 단순하게 맞는 나눔 칸 수."""
    if not offsets:
        return divisions[0]

    def worst(d: int) -> float:
        return max(abs(o * d - round(o * d)) / d for o in offsets)

    for d in divisions:
        if worst(d) <= FIT_TOLERANCE:
            return d
    return min(divisions, key=worst)


def snap(value: float, division: int) -> Fraction:
    """박 번호(소수)를 그 박의 나눔 칸에 맞춘다."""
    return Fraction(round(value * division), division)


def snap_end(value: float, divisions: tuple[int, ...]) -> Fraction:
    """끝 위치는 어떤 나눔이든 가장 가까운 칸으로."""
    return min((snap(value, d) for d in divisions), key=lambda f: abs(float(f) - value))


def quantize_notes(notes: tuple[Note, ...], beats: BeatAnalysis) -> RhythmResult:
    """음 목록을 박에 맞춰 4분음표 단위 위치·길이로 바꾼다."""
    beat_times = np.asarray(beats.beats, dtype=float)
    if len(beat_times) < 2:
        raise RhythmError("박이 2개보다 적어 리듬을 정리할 수 없어요")
    unit = beat_quarters_of(beats)
    divisions = COMPOUND_DIVISIONS if beats.pulses_per_beat == 3 else SIMPLE_DIVISIONS
    numbers = counted_beats(beats, beat_times)
    if not notes:
        return RhythmResult((), beats.time_signature, unit)

    starts = beat_number(np.array([n.start_seconds for n in notes]), beat_times, numbers)
    ends = fill_short_gaps(
        np.array([n.pitch for n in notes]), starts,
        beat_number(np.array([n.end_seconds for n in notes]), beat_times, numbers),
    )
    owner = np.floor(starts + EARLY_SHARE).astype(int)
    division_of = {
        beat: choose_division([float(s - beat) for s in starts[owner == beat]], divisions) for beat in set(owner)
    }
    result = []
    for note, start, end, beat in zip(notes, starts, ends, owner):
        division = division_of[beat]
        begin = beat + snap(float(start - beat), division)
        finish = max(snap_end(float(end), divisions), begin + Fraction(1, max(divisions)))
        result.append(RhythmNote(note.pitch, begin * unit, (finish - begin) * unit, note.velocity))
    ordered = tuple(sorted(result, key=lambda n: (n.start, n.pitch)))
    return RhythmResult(ordered, beats.time_signature, unit)


def fill_short_gaps(pitches: np.ndarray, starts: np.ndarray, ends: np.ndarray) -> np.ndarray:
    """음 끝(박 번호)을 고친 새 배열. 가까운 음역의 다음 음까지 짧은 틈은 메우고, 같은 음이 다시 나오면 거기서 끊는다."""
    new_ends = ends.copy()
    for i in range(len(starts)):
        later = starts > starts[i] + SAME_TIME_BEATS
        nearby = later & (np.abs(pitches - pitches[i]) <= NEARBY_SEMITONES)
        if nearby.any():
            following = starts[nearby].min()
            if new_ends[i] < following <= new_ends[i] + FILL_GAP_BEATS:
                new_ends[i] = following
        repeated = later & (pitches == pitches[i])
        if repeated.any():
            new_ends[i] = min(new_ends[i], starts[repeated].min())
    return new_ends


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.notes import recognize_notes

    parser = argparse.ArgumentParser(description="음원의 음을 박에 맞춰 악보 위치·길이로 바꾼다 (분석기 D단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        beats = analyze_beats(args.audio)
        result = quantize_notes(recognize_notes(Path(args.audio))["mix"], beats)
    except (AudioLoadError, PitchDetectionError, RhythmError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"박자표 {result.time_signature}, 음 {len(result.notes)}개 (위치·길이는 4분음표 단위)")
    for note in result.notes[:12]:
        print(f"  음 {note.pitch}: 위치 {note.start}, 길이 {note.length}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
