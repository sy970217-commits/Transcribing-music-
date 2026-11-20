"""템포(빠르기)를 찾고, 음 길이를 악보용 박자 단위로 정리(퀀타이즈)하는 모듈."""

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
    quantized = (_quantize_note(note, seconds_per_beat, subdivision) for note in notes)
    return tuple(sorted(quantized, key=lambda n: (n.start_beats, n.pitch)))


def _snap(seconds: float, seconds_per_beat: float, subdivision: int) -> Fraction:
    steps = round(seconds / seconds_per_beat * subdivision)
    return Fraction(steps, subdivision)


def _quantize_note(note: Note, seconds_per_beat: float, subdivision: int) -> QuantizedNote:
    start = _snap(note.start_seconds, seconds_per_beat, subdivision)
    end = _snap(note.end_seconds, seconds_per_beat, subdivision)
    shortest = Fraction(1, subdivision)
    return QuantizedNote(
        pitch=note.pitch,
        velocity=note.velocity,
        start_beats=start,
        duration_beats=max(end - start, shortest),
    )
