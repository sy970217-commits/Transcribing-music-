"""분석기 F단계: 조성. D단계 음과 E단계 코드를 보고 곡의 조(C major, A minor …)와 조가 바뀌는 곳을 찾는다.

1. 마디마다 음이름(C, C#, … B)이 얼마나 오래 울렸는지 잰다.
2. 마디 앞뒤 몇 마디를 합쳐, 24개 조(장조 12 + 단조 12)의 '자주 쓰는 음 모양'과 얼마나 닮았는지 점수를 준다.
   (모양: 장조는 도·솔·미가 많고 파#·도# 같은 음은 적다. 단조는 라·미·도가 많다)
3. 그 조의 으뜸화음(다장조면 CM, 가단조면 Am)이 나온 마디는 점수를 더 준다. 조표가 같은 다장조·가단조를 가르는 데 쓴다.
4. 조를 바꾸면 점수를 많이 깎아, 여러 마디가 함께 가리킬 때만 조가 바뀐다.

실행: uv run key 곡.wav
"""

import argparse
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.harmony import HarmonyResult, best_path
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.chord_names import PITCH_CLASSES

# 조마다 음이 쓰이는 정도(Krumhansl-Kessler, 으뜸음부터 반음씩)
MAJOR_PROFILE = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
MINOR_PROFILE = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
MODES = ("major", "minor")
# 조 이름에 쓸 으뜸음 이름(조표가 단순한 쪽)
MAJOR_NAMES = ("C", "Db", "D", "Eb", "E", "F", "F#", "G", "Ab", "A", "Bb", "B")
MINOR_NAMES = ("C", "C#", "D", "Eb", "E", "F", "F#", "G", "G#", "A", "Bb", "B")
WINDOW_BARS = 2  # 앞뒤로 이만큼 마디를 합쳐 본다
TONIC_CHORD_BONUS = 0.3  # 으뜸화음이 마디 전체에 울리면 더하는 점수
CADENCE_BONUS = 1.0  # 딸림화음 → 으뜸화음(다장조면 G → C, 가단조면 E → Am)으로 끝맺는 마디에 더하는 점수
KEY_CHANGE_COST = 1.5  # 조를 바꿀 때 깎는 점수


@dataclass(frozen=True)
class KeySegment:
    """start~end(4분음표 단위)의 조. tonic은 으뜸음 번호(0=C … 11=B), mode는 'major' 또는 'minor'."""

    start: Fraction
    end: Fraction
    tonic: int
    mode: str

    @property
    def name(self) -> str:
        names = MAJOR_NAMES if self.mode == "major" else MINOR_NAMES
        return f"{names[self.tonic]} {self.mode}"

    @property
    def sharps(self) -> int:
        """조표: 샵 수(플랫이면 음수)."""
        major_tonic = (self.tonic + (3 if self.mode == "minor" else 0)) % PITCH_CLASSES
        count = major_tonic * 7 % PITCH_CLASSES
        return count - PITCH_CLASSES if count > 6 or (count == 6 and "b" in self.name.split()[0]) else count


@dataclass(frozen=True)
class KeyResult:
    keys: tuple[KeySegment, ...]


# 후보: (으뜸음, 조, 모양). 순서는 장조 12개 → 단조 12개
CANDIDATES = [(tonic, mode, np.roll(profile, tonic))
              for mode, profile in zip(MODES, (MAJOR_PROFILE, MINOR_PROFILE)) for tonic in range(PITCH_CLASSES)]


def bar_starts(beats: BeatAnalysis, unit: Fraction, end: Fraction) -> list[Fraction]:
    """마디 시작 위치들(못갖춘마디가 있으면 0과 첫 갖춘마디)."""
    bar = beats.beats_per_bar * unit
    first = beats.pickup_beats * unit
    starts = [Fraction(0)] if first > 0 else []
    position = first
    while position < end:
        starts.append(position)
        position += bar
    return starts


def pitch_weights(notes: tuple[RhythmNote, ...], start: Fraction, end: Fraction) -> np.ndarray:
    weights = np.zeros(PITCH_CLASSES)
    for note in notes:
        overlap = min(end, note.start + note.length) - max(start, note.start)
        if overlap > 0:
            weights[note.pitch % PITCH_CLASSES] += float(overlap)
    return weights


def tonic_share(harmony: HarmonyResult, start: Fraction, end: Fraction, tonic: int, mode: str) -> float:
    """start~end에서 이 조의 으뜸화음이 울린 비율."""
    kinds = ("M", "M7") if mode == "major" else ("m", "m7")
    held = sum(min(end, c.end) - max(start, c.start) for c in harmony.chords
               if c.chord and c.chord.root == tonic and c.chord.kind in kinds and c.start < end and c.end > start)
    return float(held / (end - start))


def cadences(harmony: HarmonyResult, start: Fraction, end: Fraction, tonic: int, mode: str) -> int:
    """start~end에서 딸림화음(장3화음·7화음) 다음에 으뜸화음이 온 횟수."""
    tonic_kinds = ("M", "M7") if mode == "major" else ("m", "m7")
    dominant = (tonic + 7) % PITCH_CLASSES
    pairs = zip(harmony.chords, harmony.chords[1:])
    return sum(1 for before, after in pairs if start <= after.start < end and before.chord and after.chord
               and before.chord.root == dominant and before.chord.kind in ("M", "7")
               and after.chord.root == tonic and after.chord.kind in tonic_kinds)


def bar_scores(weights: np.ndarray, shares: np.ndarray) -> np.ndarray:
    """마디마다(앞뒤 마디 포함) 조 후보 점수."""
    rows = []
    for i in range(len(weights)):
        total = weights[max(0, i - WINDOW_BARS): i + WINDOW_BARS + 1].sum(axis=0)
        if total.std() == 0:
            rows.append(TONIC_CHORD_BONUS * shares[i])
            continue
        fit = [np.corrcoef(total, profile)[0, 1] for _, _, profile in CANDIDATES]
        rows.append(np.array(fit) + TONIC_CHORD_BONUS * shares[i])
    return np.array(rows)


def analyze_key(rhythm: RhythmResult, harmony: HarmonyResult, beats: BeatAnalysis) -> KeyResult:
    """박에 맞춘 음 + 코드 → 조 구간들."""
    if not rhythm.notes:
        return KeyResult(())
    end = max(n.start + n.length for n in rhythm.notes)
    starts = bar_starts(beats, rhythm.beat_quarters, end)
    bounds = list(zip(starts, starts[1:] + [end]))
    weights = np.array([pitch_weights(rhythm.notes, a, b) for a, b in bounds])
    shares = np.array([[tonic_share(harmony, a, b, tonic, mode)
                        + CADENCE_BONUS / TONIC_CHORD_BONUS * cadences(harmony, a, b, tonic, mode)
                        for tonic, mode, _ in CANDIDATES] for a, b in bounds])
    path = best_path(bar_scores(weights, shares), [KEY_CHANGE_COST] * len(bounds))
    segments = []
    for (a, b), choice in zip(bounds, path):
        tonic, mode, _ = CANDIDATES[choice]
        if segments and (segments[-1].tonic, segments[-1].mode) == (tonic, mode):
            segments[-1] = KeySegment(segments[-1].start, b, tonic, mode)
        else:
            segments.append(KeySegment(a, b, tonic, mode))
    return KeyResult(tuple(segments))


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import RhythmError, quantize_notes
    from transcriber.audio_io import AudioLoadError
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원의 조성과 조바꿈을 찾는다 (분석기 F단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        beats = analyze_beats(args.audio)
        rhythm = quantize_notes(recognize_notes(Path(args.audio))["mix"], beats)
        result = analyze_key(rhythm, analyze_harmony(rhythm, beats), beats)
    except (AudioLoadError, PitchDetectionError, RhythmError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"조 {len(result.keys)}개 (위치는 4분음표 단위)")
    for segment in result.keys:
        print(f"  {segment.start}~{segment.end}: {segment.name} (조표 {segment.sharps:+d})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
