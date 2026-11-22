"""(보관) 음 찾기 결과를 MIDI 파일로 저장. 예전 transcribe가 음원마다 .mid를 남길 때 썼다."""

from pathlib import Path

from transcriber.pitch import PitchResult


def save_midi(result: PitchResult, midi_path: str | Path) -> Path:
    """음 찾기 결과를 MIDI 파일로 저장한다. 폴더가 없으면 만든다."""
    output_path = Path(midi_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    result.midi.write(str(output_path))
    return output_path
