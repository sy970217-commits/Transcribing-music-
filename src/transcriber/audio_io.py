"""음원 파일을 불러오는 모듈."""

from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

SUPPORTED_EXTENSIONS = frozenset({".mp3", ".wav", ".flac", ".m4a", ".ogg"})
DEFAULT_SAMPLE_RATE = 22050


class AudioLoadError(Exception):
    """음원을 불러올 수 없을 때 발생하는 오류."""


@dataclass(frozen=True)
class AudioData:
    """불러온 음원. samples는 -1~1 사이 값의 모노 파형."""

    samples: np.ndarray
    sample_rate: int

    @property
    def duration_seconds(self) -> float:
        return len(self.samples) / self.sample_rate


def validate_audio_path(path: str | Path) -> Path:
    """파일이 있고 지원하는 음원 형식인지 확인한다."""
    file_path = Path(path)
    if not file_path.is_file():
        raise AudioLoadError(f"파일을 찾을 수 없습니다: {file_path}")
    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        supported = ", ".join(sorted(SUPPORTED_EXTENSIONS))
        raise AudioLoadError(f"지원하지 않는 형식입니다: {file_path.suffix} (지원: {supported})")
    return file_path


def load_audio(path: str | Path, sample_rate: int = DEFAULT_SAMPLE_RATE) -> AudioData:
    """음원 파일을 모노로 불러와 지정한 샘플레이트로 맞춘다."""
    file_path = validate_audio_path(path)

    try:
        samples, loaded_rate = librosa.load(file_path, sr=sample_rate, mono=True)
    except Exception as error:
        raise AudioLoadError(f"음원을 읽을 수 없습니다: {file_path} ({error})") from error

    if samples.size == 0:
        raise AudioLoadError(f"소리가 없는 빈 파일입니다: {file_path}")

    return AudioData(samples=samples, sample_rate=int(loaded_rate))
