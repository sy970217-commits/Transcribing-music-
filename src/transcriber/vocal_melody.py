"""노래 녹음에서 목소리를 분리해 멜로디를 뽑는 모듈. Demucs(목소리 분리 AI)를 사용한다.

Demucs는 사람이 부른 진짜 목소리를 배운 AI다. Finale 재생 음원의 가상 합창 소리처럼
사람 목소리가 아닌 소리는 거의 분리하지 못한다. 그런 경우는 MIDI 파일을 넣는 편이 낫다.
"""

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from transcriber.audio_io import load_audio
from transcriber.pitch import Note, detect_notes

DEMUCS_MODEL = "htdemucs"
LOWEST_VOICE_PITCH = 48  # 낮은 도(C3). 사람 목소리 범위 밖의 음은 버린다
HIGHEST_VOICE_PITCH = 84  # 높은 도(C6)
# 곡을 5초씩 잘라, 목소리 크기가 전체의 10% 이상인 구간이 20% 이상이면 "목소리 있음"
# (곡 전체 평균만 보면 잠깐 튄 잡음 한 구간 때문에 잘못 판단할 수 있다)
VOICE_WINDOW_SAMPLES = 22050 * 5
MIN_VOICE_ENERGY_RATIO = 0.1
MIN_VOICED_WINDOW_SHARE = 0.2
SAME_START_SECONDS = 0.05  # 이 시간 안에 시작한 음들은 동시에 시작한 것으로 본다


@dataclass(frozen=True)
class VocalParts:
    """목소리 분리 결과: 멜로디 음과 반주(목소리를 뺀) 음원 경로."""

    melody: tuple[Note, ...]
    accompaniment_path: Path
    has_voice: bool


def separate_stems(audio_path: Path, work_dir: Path) -> tuple[Path, Path]:
    """Demucs로 음원을 목소리와 반주로 나눈다. (vocals.wav, no_vocals.wav)를 돌려준다."""
    from demucs.separate import main as demucs_main  # 무거운 라이브러리라 필요할 때만 불러온다

    demucs_main(
        ["-n", DEMUCS_MODEL, "--two-stems", "vocals", "-o", str(work_dir), str(audio_path)]
    )
    stem_dir = work_dir / DEMUCS_MODEL / audio_path.stem
    return stem_dir / "vocals.wav", stem_dir / "no_vocals.wav"


def extract_vocal_parts(audio_path: str | Path, work_dir: str | Path) -> VocalParts:
    """목소리를 분리해 멜로디(한 번에 한 음)를 뽑는다. 목소리가 없으면 멜로디는 비어 있다."""
    source = Path(audio_path)
    vocals_path, accompaniment_path = separate_stems(source, Path(work_dir))

    voice_found = has_voice(load_audio(vocals_path).samples, load_audio(source).samples)
    if not voice_found:
        return VocalParts(melody=(), accompaniment_path=source, has_voice=False)

    in_range = tuple(
        n
        for n in detect_notes(vocals_path).notes
        if LOWEST_VOICE_PITCH <= n.pitch <= HIGHEST_VOICE_PITCH
    )
    return VocalParts(
        melody=to_monophonic(in_range),
        accompaniment_path=accompaniment_path,
        has_voice=True,
    )


def has_voice(
    vocals: np.ndarray, mix: np.ndarray, window: int = VOICE_WINDOW_SAMPLES
) -> bool:
    """분리된 목소리가 곡의 충분히 많은 구간에서 들리는지 확인한다."""
    length = min(len(vocals), len(mix))
    starts = range(0, length, window)
    voiced = [
        _energy(vocals[i : i + window]) >= MIN_VOICE_ENERGY_RATIO * _energy(mix[i : i + window])
        for i in starts
        if _energy(mix[i : i + window]) > 0
    ]
    return bool(voiced) and sum(voiced) / len(voiced) >= MIN_VOICED_WINDOW_SHARE


def _energy(samples: np.ndarray) -> float:
    return float(np.sqrt(np.mean(np.square(samples)))) if samples.size else 0.0


def to_monophonic(notes: tuple[Note, ...]) -> tuple[Note, ...]:
    """노래는 한 번에 한 음만 낸다. 겹치는 음을 정리해 한 줄 멜로디로 만든다.

    동시에 시작한 음 중에서는 가장 센 음을 남기고, 앞 음은 다음 음이 시작할 때 끊는다.
    """
    ordered = sorted(notes, key=lambda n: (n.start_seconds, -n.velocity))
    melody: list[Note] = []
    for current in ordered:
        if melody and current.start_seconds - melody[-1].start_seconds < SAME_START_SECONDS:
            if current.velocity > melody[-1].velocity:
                melody[-1] = current
            continue
        if melody and melody[-1].end_seconds > current.start_seconds:
            previous = melody[-1]
            melody[-1] = Note(
                start_seconds=previous.start_seconds,
                end_seconds=current.start_seconds,
                pitch=previous.pitch,
                velocity=previous.velocity,
            )
        melody.append(current)
    return tuple(melody)
