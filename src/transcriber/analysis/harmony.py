"""분석기 E단계: 화음. D단계에서 박에 맞춘 음을 보고 구간마다 코드(CM, Am7, CM/E …)를 정한다.

1. 박마다 음이름(C, C#, … B)이 얼마나 오래 울렸는지 잰다. 맨 아래 음은 더 무겁게 센다.
2. 모든 코드 후보(근음 12개 × 종류 9개)에 박마다 점수를 준다.
   코드 음이 많이 울리면 +, 코드 밖 음(꾸밈음)이 울리면 -, 코드 음이 빠져 있으면 -, 맨 아래 음이 근음이면 +.
3. 코드를 자주 바꾸면 점수를 깎아(마디 첫 박은 조금, 마디 가운데는 더, 그 밖은 많이) 가장 점수가 높은 흐름을 고른다.
   그래서 꾸밈음 한두 개로 코드가 흔들리지 않는다.
4. 같은 코드가 이어진 구간(마디·반 마디 조각)마다 가장 낮은 음을 보고 자리바꿈(/E 같은)을 정한다.

실행: uv run harmony 곡.wav
"""

import argparse
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.chord_names import CHORD_TYPES, PITCH_CLASSES, Chord

BASS_WEIGHT = 1.0  # 맨 아래 음은 울린 시간의 (1 + 이 값)배로 센다
OUTSIDE_PENALTY = 1.0  # 코드 밖 음 비율 × 이 값만큼 깎는다
MISSING_PENALTY = 0.6  # 빠진 코드 음 비율 × 이 값만큼 깎는다
ROOT_IN_BASS_BONUS = 0.25  # 맨 아래 음이 근음이면 더한다
EXTRA_TONE_COST = 0.1  # 음이 많은 코드(7화음)는 조금 깎아, 비기면 3화음을 고른다
MIN_TONES = 2  # 음이름이 이보다 적게 울린 박은 판단하지 않는다(앞뒤 코드를 이어 간다)
MIN_TONE_SHARE = 0.1  # 박 안에서 이 비율보다 짧게 울린 코드 음은 빠진 것으로 본다(꾸밈음 때문에 Am7로 착각 방지)
UNSURE_NO_CHORD_SCORE = 0.2  # 첫 코드 앞의 판단하지 않는 박에서 '코드 없음'에 주는 점수(곡 처음 못갖춘마디 등)
# 코드를 바꿀 때 깎는 점수: 마디 첫 박 / 마디 가운데 박(4/4의 3박, 6/8처럼 2박 마디는 없음) / 그 밖
CHANGE_COST_BAR, CHANGE_COST_HALF, CHANGE_COST_BEAT = 0.1, 0.25, 0.8


@dataclass(frozen=True)
class ChordSegment:
    """start~end(4분음표 단위)에 울리는 코드. chord가 None이면 코드 없음."""

    start: Fraction
    end: Fraction
    chord: Chord | None

    @property
    def name(self) -> str:
        return self.chord.name if self.chord else "N"


@dataclass(frozen=True)
class HarmonyResult:
    chords: tuple[ChordSegment, ...]


# 후보: (근음, 종류, 구성음 이름 번호들). 맨 끝 None = 코드 없음
CANDIDATES = [(root, kind, frozenset((root + t) % PITCH_CLASSES for t in tones))
              for root in range(PITCH_CLASSES) for tones, kind in CHORD_TYPES.items()]


def slot_weights(notes: tuple[RhythmNote, ...], start: Fraction, end: Fraction) -> tuple[np.ndarray, int | None]:
    """start~end에 음이름마다 울린 시간(맨 아래 음은 더 무겁게)과 맨 아래 음이름.
    박 앞에서 시작해 박의 앞쪽 절반 안에 끝나는 음이 둘 이상이면 앞 코드의 남은 울림이라 세지 않는다.
    하나뿐이면 선율 음일 수 있어 센다(예: 앞 꾸밈음과 같은 높이라 반 박 일찍 잡힌 선율)."""
    weights = np.zeros(PITCH_CLASSES)
    middle = (start + end) / 2
    ringing = {n for n in notes if n.start < start and start < n.start + n.length <= middle}
    counted = notes if len(ringing) < MIN_TONES else [n for n in notes if n not in ringing]
    sounding = [(n, min(end, n.start + n.length) - max(start, n.start)) for n in counted]
    sounding = [(n, overlap) for n, overlap in sounding if overlap > 0]
    for note, overlap in sounding:
        weights[note.pitch % PITCH_CLASSES] += float(overlap)
    if not sounding:
        return weights, None
    lowest, overlap = min(sounding, key=lambda pair: pair[0].pitch)
    weights[lowest.pitch % PITCH_CLASSES] += BASS_WEIGHT * float(overlap)
    return weights, lowest.pitch % PITCH_CLASSES


def slot_scores(weights: np.ndarray, bass: int | None) -> np.ndarray:
    """후보 코드마다 이 박의 점수. 마지막 칸은 코드 없음."""
    if np.count_nonzero(weights) < MIN_TONES:
        return np.zeros(len(CANDIDATES) + 1)
    scores = np.zeros(len(CANDIDATES) + 1)
    share = weights / weights.sum()
    for i, (root, _, tones) in enumerate(CANDIDATES):
        inside = sum(share[t] for t in tones)
        missing = sum(1 for t in tones if share[t] < MIN_TONE_SHARE) / len(tones)
        scores[i] = (inside - OUTSIDE_PENALTY * (1 - inside) - MISSING_PENALTY * missing
                     + ROOT_IN_BASS_BONUS * (bass == root) - EXTRA_TONE_COST * (len(tones) - 3))
    return scores


def change_cost(beat_index: int, beats_per_bar: int, pickup_beats: int) -> float:
    """beat_index번째 박에서 코드를 바꿀 때 깎는 점수."""
    in_bar = (beat_index - pickup_beats) % beats_per_bar
    if in_bar == 0:
        return CHANGE_COST_BAR
    if beats_per_bar >= 4 and beats_per_bar % 2 == 0 and in_bar == beats_per_bar // 2:
        return CHANGE_COST_HALF
    return CHANGE_COST_BEAT


def best_path(scores: np.ndarray, costs: list[float]) -> list[int]:
    """박마다 후보 점수(박 수 × 후보 수)에서, 바꿀 때 costs만큼 깎으며 합이 가장 큰 후보 흐름."""
    total = scores[0].copy()
    came_from = []
    for row, cost in zip(scores[1:], costs[1:]):
        best = int(np.argmax(total))
        switch = total[best] - cost
        back = np.where(total >= switch, np.arange(len(total)), best)
        total = np.maximum(total, switch) + row
        came_from.append(back)
    path = [int(np.argmax(total))]
    for back in reversed(came_from):
        path.append(int(back[path[-1]]))
    return path[::-1]


def segment_bass(notes: tuple[RhythmNote, ...], start: Fraction, end: Fraction, root: int, tones: frozenset) -> int:
    """구간에서 가장 낮게 울린 음이 코드 음이면 그 음, 아니면 근음."""
    inside = [n for n in notes if n.start < end and n.start + n.length > start]
    if not inside:
        return root
    lowest = min(inside, key=lambda n: n.pitch).pitch % PITCH_CLASSES
    return lowest if lowest in tones else root


def analyze_harmony(rhythm: RhythmResult, beats: BeatAnalysis) -> HarmonyResult:
    """박에 맞춘 음 → 코드 구간들."""
    if not rhythm.notes:
        return HarmonyResult(())
    unit = rhythm.beat_quarters
    song_end = max(n.start + n.length for n in rhythm.notes)
    count = int(np.ceil(song_end / unit))
    rows = np.array([slot_scores(*slot_weights(rhythm.notes, i * unit, (i + 1) * unit)) for i in range(count)])
    leading = np.argmax(rows.any(axis=1)) if rows.any() else count
    rows[:leading, -1] = UNSURE_NO_CHORD_SCORE  # 첫 코드 앞(못갖춘마디 등)의 판단 못 하는 박은 '코드 없음'
    costs = [change_cost(i, beats.beats_per_bar, beats.pickup_beats) for i in range(count)]
    path = best_path(rows, costs)
    # 코드가 바뀌는 곳과 마디 첫 박·가운데 박에서 나눈 조각마다 맨 아래 음을 정하고, 같은 코드·같은 맨 아래 음은 다시 잇는다
    cuts = [i for i in range(count) if i == 0 or path[i] != path[i - 1] or costs[i] <= CHANGE_COST_HALF] + [count]
    pieces = [make_segment(rhythm.notes, path[a], a * unit, b * unit) for a, b in zip(cuts, cuts[1:])]
    merged = [pieces[0]]
    for piece in pieces[1:]:
        if piece.chord == merged[-1].chord:
            merged[-1] = ChordSegment(merged[-1].start, piece.end, piece.chord)
        else:
            merged.append(piece)
    return HarmonyResult(tuple(merged))


def make_segment(notes: tuple[RhythmNote, ...], choice: int, start: Fraction, end: Fraction) -> ChordSegment:
    if choice == len(CANDIDATES):
        return ChordSegment(start, end, None)
    root, kind, tones = CANDIDATES[choice]
    return ChordSegment(start, end, Chord(root=root, kind=kind, bass=segment_bass(notes, start, end, root, tones)))


def main(argv: list[str] | None = None) -> int:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import RhythmError, quantize_notes
    from transcriber.audio_io import AudioLoadError
    from transcriber.pitch import PitchDetectionError

    parser = argparse.ArgumentParser(description="음원의 코드 진행을 찾는다 (분석기 E단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        beats = analyze_beats(args.audio)
        result = analyze_harmony(quantize_notes(recognize_notes(Path(args.audio))["mix"], beats), beats)
    except (AudioLoadError, PitchDetectionError, RhythmError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"코드 {len(result.chords)}개 (위치는 4분음표 단위)")
    for segment in result.chords:
        print(f"  {segment.start}~{segment.end}: {segment.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
