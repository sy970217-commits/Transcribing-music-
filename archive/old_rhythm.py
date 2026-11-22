"""(보관) 예전 방식: 음원 전체에서 빠르기 하나를 찾고, 초 단위 음을 박자 칸에 맞춘다.
지금은 analysis.beats(B단계)·analysis.rhythm(D단계)이 대신한다.
"""

from fractions import Fraction
from pathlib import Path

import librosa
import numpy as np

from transcriber.audio_io import load_audio
from transcriber.pitch import Note
from transcriber.rhythm import DEFAULT_SUBDIVISION, DEFAULT_TEMPO_BPM, BeatNote, QuantizedNote, quantize_beat_notes

MIN_TEMPO_BPM = 40.0
MAX_TEMPO_BPM = 240.0
SECONDS_PER_MINUTE = 60.0


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
    split_pitch: int | None = None,
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
    return quantize_beat_notes(raw, subdivision, split_pitch)
