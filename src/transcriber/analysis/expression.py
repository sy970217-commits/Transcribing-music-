"""분석기 H단계: 표현. 음원 소리와 D단계 음, E단계 코드를 보고 셈여림과 페달 밟는 곳을 찾는다.

음마다 소리를 잰다(음 인식기의 세기는 크기가 고르게 맞춰져 나와 쓰지 않는다)
  - 세기: 음을 친 순간 소리 크기(dB). 함께 친 음이 많으면 그만큼 빼서 음 하나의 크기로 본다.
  - 남은 울림: 그 음 뒤로 음이 두 번 더 나오기 직전에, 그 음 높이 소리가 처음보다 얼마나 줄었는지(dB).
    페달 없이 손을 떼면 소리가 바로 사라지고, 페달을 밟으면 계속 울린다.
셈여림
1. 마디마다 음 세기의 중앙값을 pp, p, mp, mf, f, ff 로 바꾼다. 범위를 조금 벗어난 정도로는 바꾸지 않는다.
2. 두 마디 넘게 마디마다 꾸준히 세지면 '점점 세게(<)', 여려지면 '점점 여리게(>)'.
3. 한 마디만 튀는 셈여림은 앞 마디를 따른다.
페달(오른쪽 페달)
1. 코드가 이어지는 구간마다, 그 안에서 친 음들의 남은 울림 중앙값을 본다.
2. 충분히 남아 있으면 페달을 밟은 것으로 본다. 페달은 코드가 바뀔 때마다 떼었다 다시 밟는다.

실행: uv run expression 곡.wav
"""

import argparse
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path
from statistics import median

import librosa
import numpy as np

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.harmony import HarmonyResult
from transcriber.analysis.rhythm import RhythmResult, beat_number, beat_quarters_of, counted_beats
from transcriber.analysis.tonality import bar_starts
from transcriber.pitch import Note

# (셈여림, 이 세기 미만까지). 세기는 MIDI 세기(1~127)와 같은 눈금
LEVELS = (("pp", 40), ("p", 56), ("mp", 70), ("mf", 85), ("f", 100), ("ff", 128))
LEVEL_MARGIN = 5  # 지금 셈여림 범위를 이만큼 넘게 벗어나야 셈여림을 바꾼다(음 높이에 따라 크기가 조금씩 달라서)
HAIRPIN_STEP = 6  # 마디 세기가 이만큼 넘게 바뀌어야 '꾸준히 바뀐' 마디
HAIRPIN_BARS = 2  # 이만큼 이어서 바뀌어야 < 또는 >
PEDAL_DECAY_DB = -20.0  # 남은 울림이 이보다 크면(덜 줄면) 페달
MIN_PEDAL_NOTES = 2  # 남은 울림을 잰 음이 이보다 적은 구간은 페달 없음으로 본다

SAMPLE_RATE = 22050
HOP = 256  # 소리를 잴 때 한 칸(약 12ms)
ATTACK_SECONDS = 0.1  # 음을 친 뒤 이 시간 안에서 가장 큰 소리를 잰다
TOGETHER_SECONDS = 0.05  # 이보다 가까이 시작한 음은 함께 친 음
BEFORE_NEXT_SECONDS = 0.03  # 다음 음 직전: 이만큼 앞에서 잰다
LOWEST_PITCH, PITCH_COUNT = 21, 88  # 피아노 건반 범위(A0부터 88개)
OVERTONES = (0, 12, 19, 24, 28)  # 이만큼 아래 음을 치면 그 배음이 이 음 높이에서 울린다
# 세기 눈금 맞추기: 음 하나 크기가 REFERENCE_DB면 세기 70(mf), dB가 DB_PER_VELOCITY 오를 때마다 세기 1
REFERENCE_DB = -36.1
DB_PER_VELOCITY = 0.2


@dataclass(frozen=True)
class NoteSound:
    """음 하나의 소리. position은 시작 위치(4분음표 단위), decay는 남은 울림(dB, 잴 수 없으면 None)."""

    position: float
    velocity: float
    decay: float | None


@dataclass(frozen=True)
class DynamicSpan:
    """start~end(4분음표 단위)의 셈여림. mark는 'p', 'f' 같은 글자 또는 '<'(점점 세게), '>'(점점 여리게)."""

    start: Fraction
    end: Fraction
    mark: str


@dataclass(frozen=True)
class PedalSpan:
    """오른쪽 페달을 밟고 있는 구간(4분음표 단위)."""

    start: Fraction
    end: Fraction


@dataclass(frozen=True)
class ExpressionResult:
    dynamics: tuple[DynamicSpan, ...]
    pedals: tuple[PedalSpan, ...]


def to_db(value: float) -> float:
    return 20 * float(np.log10(value + 1e-9))


def decay_check_time(note: Note, onsets: np.ndarray, notes: tuple[Note, ...]) -> float | None:
    """남은 울림을 잴 때(그 음 뒤로 음이 두 번 더 나오기 직전). 그 사이 손으로 누르고 있거나
    같은 음(또는 배음이 겹치는 아래 음)을 다시 쳤으면 잴 수 없다(None)."""
    after = onsets[onsets > note.start_seconds + TOGETHER_SECONDS]
    if len(after) == 0:
        return None
    second = after[after > after[0] + TOGETHER_SECONDS]
    if len(second) == 0:
        return None
    check = float(second[0]) - BEFORE_NEXT_SECONDS
    struck_again = any(note.start_seconds + TOGETHER_SECONDS < m.start_seconds <= check
                       and note.pitch - m.pitch in OVERTONES for m in notes)
    return None if struck_again or note.end_seconds >= check else check


def measure_sounds(audio_path: str | Path, notes: tuple[Note, ...], beats: BeatAnalysis) -> tuple[NoteSound, ...]:
    """음원에서 음마다 세기와 남은 울림을 잰다."""
    if not notes:
        return ()
    samples, rate = librosa.load(str(audio_path), sr=SAMPLE_RATE)
    loudness = librosa.feature.rms(y=samples, frame_length=4 * HOP, hop_length=HOP)[0]
    spectrum = np.abs(librosa.cqt(samples, sr=rate, hop_length=HOP,
                                  fmin=librosa.midi_to_hz(LOWEST_PITCH), n_bins=PITCH_COUNT))

    def frame(seconds: float) -> int:
        return min(int(seconds * rate / HOP), len(loudness) - 1)

    starts = np.array([n.start_seconds for n in notes])
    onsets = np.unique(starts)
    beat_times = np.asarray(beats.beats, dtype=float)
    positions = beat_number(starts, beat_times, counted_beats(beats, beat_times)) * float(beat_quarters_of(beats))
    attack = int(ATTACK_SECONDS * rate / HOP) + 1
    sounds = []
    for note, position in zip(notes, positions):
        begin = frame(note.start_seconds)
        together = int(np.sum(np.abs(starts - note.start_seconds) < TOGETHER_SECONDS))
        level = to_db(loudness[begin:begin + attack].max()) - 10 * np.log10(together)
        velocity = 70 + (level - REFERENCE_DB) / DB_PER_VELOCITY
        check, row = decay_check_time(note, onsets, notes), note.pitch - LOWEST_PITCH
        decay = None
        if check is not None and 0 <= row < PITCH_COUNT:
            decay = to_db(spectrum[row, frame(check)]) - to_db(spectrum[row, begin:begin + attack].max())
        sounds.append(NoteSound(float(position), velocity, decay))
    return tuple(sounds)


def level_for(velocity: float) -> str:
    return next((name for name, upper in LEVELS if velocity < upper), LEVELS[-1][0])


def levels_with_margin(loudness: list[float]) -> list[str]:
    """마디마다 셈여림 글자. 지금 셈여림 범위를 LEVEL_MARGIN 넘게 벗어날 때만 바꾼다."""
    uppers = dict(LEVELS)
    lowers = dict(zip(uppers, [0] + [upper for _, upper in LEVELS]))
    marks, current = [], level_for(loudness[0]) if loudness else ""
    for value in loudness:
        if value < lowers[current] - LEVEL_MARGIN or value >= uppers[current] + LEVEL_MARGIN:
            current = level_for(value)
        marks.append(current)
    return marks


def bar_loudness(sounds: tuple[NoteSound, ...], bounds: list) -> list[float | None]:
    """마디마다 그 안에서 친 음 세기의 중앙값(음이 없으면 None)."""
    result = []
    for start, end in bounds:
        inside = [s.velocity for s in sounds if start <= s.position < end]
        result.append(median(inside) if inside else None)
    return result


def bar_marks(loudness: list[float | None]) -> list[str]:
    """마디마다 셈여림 글자 또는 < >."""
    filled, last = [], next((v for v in loudness if v is not None), 0.0)
    for value in loudness:  # 음이 없는 마디는 앞 마디 세기를 쓴다
        last = last if value is None else value
        filled.append(last)
    changes = [0.0] + [b - a for a, b in zip(filled, filled[1:])]
    marks = levels_with_margin(filled)
    for sign, mark in ((1, "<"), (-1, ">")):
        run = []
        for i, change in enumerate(changes + [0.0]):
            if i < len(filled) and change * sign >= HAIRPIN_STEP:
                run.append(i)
                continue
            if run and i < len(filled) and marks[run[-1]] == marks[i]:
                run = run[:-1]  # 다음 마디와 셈여림이 같으면 그 마디는 도착한 곳(글자로 적는다)
            if len(run) >= HAIRPIN_BARS:
                marks = [mark if j in run else m for j, m in enumerate(marks)]
            run = []
    return steady_levels(marks)


def steady_levels(marks: list[str]) -> list[str]:
    """한 마디만 다른 셈여림 글자는 앞(처음이면 뒤) 마디 글자로 바꾼 새 목록."""
    result = list(marks)
    for i, mark in enumerate(marks):
        if mark in "<>":
            continue
        before = result[i - 1] if i else None
        after = marks[i + 1] if i + 1 < len(marks) else None
        if before not in (None, "<", ">") and mark != before and after != mark:
            result[i] = before
        elif before is None and after not in (None, "<", ">") and mark != after:
            result[i] = after
    return result


def analyze_dynamics(sounds: tuple[NoteSound, ...], bounds: list) -> tuple[DynamicSpan, ...]:
    spans: list[DynamicSpan] = []
    for (start, end), mark in zip(bounds, bar_marks(bar_loudness(sounds, bounds))):
        if spans and spans[-1].mark == mark:
            spans[-1] = DynamicSpan(spans[-1].start, end, mark)
        else:
            spans.append(DynamicSpan(start, end, mark))
    return tuple(spans)


def is_pedalled(sounds: tuple[NoteSound, ...], start: Fraction, end: Fraction) -> bool:
    decays = [s.decay for s in sounds if start <= s.position < end and s.decay is not None]
    return len(decays) >= MIN_PEDAL_NOTES and median(decays) > PEDAL_DECAY_DB


def analyze_expression(rhythm: RhythmResult, harmony: HarmonyResult, beats: BeatAnalysis,
                       sounds: tuple[NoteSound, ...]) -> ExpressionResult:
    """박에 맞춘 음 + 코드 + 음마다 잰 소리 → 셈여림 구간, 페달 구간."""
    if not rhythm.notes or not sounds:
        return ExpressionResult((), ())
    end = max(n.start + n.length for n in rhythm.notes)
    starts = bar_starts(beats, rhythm.beat_quarters, end)
    bounds = list(zip(starts, starts[1:] + [end]))
    pedals = tuple(PedalSpan(c.start, c.end) for c in harmony.chords if is_pedalled(sounds, c.start, c.end))
    return ExpressionResult(analyze_dynamics(sounds, bounds), pedals)


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import RhythmError, quantize_notes
    from transcriber.audio_io import AudioLoadError
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원에서 셈여림과 페달 밟는 곳을 찾는다 (분석기 H단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        beats = analyze_beats(args.audio)
        notes = recognize_notes(Path(args.audio))["mix"]
        rhythm = quantize_notes(notes, beats)
        sounds = measure_sounds(args.audio, notes, beats)
        result = analyze_expression(rhythm, analyze_harmony(rhythm, beats), beats, sounds)
    except (AudioLoadError, PitchDetectionError, RhythmError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"셈여림 {len(result.dynamics)}곳 (위치는 4분음표 단위)")
    for span in result.dynamics:
        print(f"  {span.start}~{span.end}: {span.mark}")
    print(f"페달 {len(result.pedals)}번")
    for span in result.pedals:
        print(f"  {span.start}~{span.end}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
