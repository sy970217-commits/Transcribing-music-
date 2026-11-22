"""음원에서 음(노트)을 찾아 MIDI로 저장하는 모듈. Spotify Basic Pitch를 사용한다."""

from dataclasses import dataclass
from pathlib import Path

from basic_pitch import ICASSP_2022_MODEL_PATH
from basic_pitch.inference import predict

from transcriber.audio_io import validate_audio_path

MAX_VELOCITY = 127
# 음이 계속 울리고 있다고 볼 기준. 기본값 0.3보다 높여 잡음 음을 줄인다.
# (가을꽃 원본 MIDI와 비교: 정확도 77% → 84%)
FRAME_THRESHOLD = 0.4
ONSET_THRESHOLD = 0.5  # Basic Pitch 기본값
MIN_NOTE_MS = 127.7  # Basic Pitch 기본값


class PitchDetectionError(Exception):
    """음을 찾는 중 문제가 생겼을 때 발생하는 오류."""


@dataclass(frozen=True)
class Note:
    """찾아낸 음 하나. pitch는 MIDI 번호(60=가운데 도, 69=라)."""

    start_seconds: float
    end_seconds: float
    pitch: int
    velocity: int


@dataclass(frozen=True)
class PitchResult:
    """음 찾기 결과: 음 목록과 MIDI 데이터."""

    notes: tuple[Note, ...]
    midi: object  # pretty_midi.PrettyMIDI


def detect_notes(
    audio_path: str | Path,
    onset_threshold: float = ONSET_THRESHOLD,
    frame_threshold: float = FRAME_THRESHOLD,
    min_note_ms: float = MIN_NOTE_MS,
) -> PitchResult:
    """음원에서 음을 찾는다. 결과는 시작 시간 순으로 정렬된다.

    onset_threshold: 음이 '시작했다'고 볼 기준(클수록 확실한 음만)
    frame_threshold: 음이 '계속 울린다'고 볼 기준
    min_note_ms: 이보다 짧은 음은 버린다
    """
    file_path = validate_audio_path(audio_path)

    try:
        _, midi, note_events = predict(
            file_path,
            ICASSP_2022_MODEL_PATH,
            onset_threshold=onset_threshold,
            frame_threshold=frame_threshold,
            minimum_note_length=min_note_ms,
        )
    except Exception as error:
        raise PitchDetectionError(f"음을 찾지 못했습니다: {file_path} ({error})") from error

    notes = tuple(
        sorted(
            (_to_note(event) for event in note_events),
            key=lambda note: (note.start_seconds, note.pitch),
        )
    )
    return PitchResult(notes=notes, midi=midi)


def save_midi(result: PitchResult, midi_path: str | Path) -> Path:
    """음 찾기 결과를 MIDI 파일로 저장한다. 폴더가 없으면 만든다."""
    output_path = Path(midi_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.midi.write(str(output_path))
    return output_path


def _to_note(event: tuple) -> Note:
    start, end, pitch, amplitude, *_ = event
    velocity = max(1, min(MAX_VELOCITY, round(float(amplitude) * MAX_VELOCITY)))
    return Note(
        start_seconds=float(start),
        end_seconds=float(end),
        pitch=int(pitch),
        velocity=velocity,
    )
