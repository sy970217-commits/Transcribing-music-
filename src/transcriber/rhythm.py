"""템포(빠르기)를 찾고, 음 길이를 악보용 박자 단위로 정리(퀀타이즈)하는 모듈."""

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import librosa
import numpy as np

from transcriber.audio_io import load_audio
from transcriber.pitch import Note

DEFAULT_TEMPO_BPM = 120.0
MIN_TEMPO_BPM = 40.0
MAX_TEMPO_BPM = 240.0
SECONDS_PER_MINUTE = 60.0
DEFAULT_SUBDIVISION = 4  # 한 박을 4칸으로 나눔 = 16분음표 단위
TRIPLET_DIVISION = 3  # 한 박을 3칸으로 나눔 = 8분음표 셋잇단음표
# 셋잇단음표 칸의 어긋남이 16분음표 칸의 절반보다 작을 때만 셋잇단음표로 본다
# (헷갈리면 더 흔한 16분음표 쪽을 고른다)
TRIPLET_PREFERENCE = 0.5


@dataclass(frozen=True)
class QuantizedNote:
    """박자 단위로 정리된 음. 1박 = 4분음표 하나."""

    pitch: int
    velocity: int
    start_beats: Fraction
    duration_beats: Fraction


def estimate_tempo(audio_path: str | Path) -> float:
    """음원의 템포(BPM, 1분당 박 수)를 찾는다. 못 찾으면 120을 쓴다."""
    audio = load_audio(audio_path)
    tempo, _ = librosa.beat.beat_track(y=audio.samples, sr=audio.sample_rate)
    bpm = float(np.atleast_1d(tempo)[0])
    if not MIN_TEMPO_BPM <= bpm <= MAX_TEMPO_BPM:
        return DEFAULT_TEMPO_BPM
    return bpm


def quantize_notes(
    notes: tuple[Note, ...],
    tempo_bpm: float,
    subdivision: int = DEFAULT_SUBDIVISION,
) -> tuple[QuantizedNote, ...]:
    """음의 시작과 길이를 가장 가까운 박자 칸에 맞춘다."""
    if tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")
    if subdivision <= 0:
        raise ValueError(f"박 나누기 수는 0보다 커야 합니다: {subdivision}")

    seconds_per_beat = SECONDS_PER_MINUTE / tempo_bpm
    raw = tuple(
        BeatNote(
            pitch=n.pitch,
            velocity=n.velocity,
            start_beats=n.start_seconds / seconds_per_beat,
            end_beats=n.end_seconds / seconds_per_beat,
        )
        for n in notes
    )
    return quantize_beat_notes(raw, subdivision)


@dataclass(frozen=True)
class BeatNote:
    """박 단위로 잰, 아직 칸에 맞추지 않은 음."""

    pitch: int
    velocity: int
    start_beats: float
    end_beats: float


def quantize_beat_notes(
    notes: tuple[BeatNote, ...], subdivision: int = DEFAULT_SUBDIVISION
) -> tuple[QuantizedNote, ...]:
    """음을 박자 칸에 맞춘다. 박마다 16분음표 칸과 셋잇단음표 칸 중 더 잘 맞는 쪽을 고른다."""
    divisions = _choose_divisions(tuple(n.start_beats for n in notes), subdivision)

    def division_at(beat: float) -> int:
        return divisions.get(math.floor(beat), subdivision)

    quantized = []
    for n in notes:
        start = _snap_to(n.start_beats, division_at(n.start_beats))
        end = _snap_to(n.end_beats, division_at(n.end_beats))
        shortest = Fraction(1, division_at(float(start)))
        quantized.append(
            QuantizedNote(
                pitch=n.pitch,
                velocity=n.velocity,
                start_beats=start,
                duration_beats=max(end - start, shortest),
            )
        )
    return tuple(sorted(quantized, key=lambda q: (q.start_beats, q.pitch)))


def _choose_divisions(starts: tuple[float, ...], subdivision: int) -> dict[int, int]:
    """박마다 쓸 칸 나누기 수를 정한다. 셋잇단음표 칸이 훨씬 잘 맞을 때만 3을 쓴다."""
    by_beat: dict[int, list[float]] = {}
    for start in starts:
        by_beat.setdefault(math.floor(start), []).append(start)

    divisions = {}
    for beat, onsets in by_beat.items():
        binary_error = sum(_snap_error(x, subdivision) for x in onsets)
        triplet_error = sum(_snap_error(x, TRIPLET_DIVISION) for x in onsets)
        use_triplet = triplet_error < binary_error * TRIPLET_PREFERENCE
        divisions[beat] = TRIPLET_DIVISION if use_triplet else subdivision
    return divisions


def _snap_to(beats: float, division: int) -> Fraction:
    return Fraction(round(beats * division), division)


def _snap_error(beats: float, division: int) -> float:
    return abs(beats - float(_snap_to(beats, division)))
