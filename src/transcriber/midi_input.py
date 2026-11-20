"""MIDI 파일(예: Finale에서 내보낸 파일)을 읽어 악보용 음으로 바꾸는 모듈.

음원에서 음을 찾는 것보다 훨씬 정확하다. 박자는 MIDI의 박 정보(tick)로
계산하므로, 곡 중간에 빠르기가 바뀌어도(리타르단도 등) 마디가 밀리지 않는다.
"""

from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import pretty_midi

from transcriber.rhythm import DEFAULT_SUBDIVISION, DEFAULT_TEMPO_BPM, QuantizedNote
from transcriber.tempo_marks import TempoChange

MIDI_EXTENSIONS = frozenset({".mid", ".midi"})
PIANO_PROGRAMS = range(0, 8)  # General MIDI 0~7번은 피아노 계열 악기
TEMPO_POSITION_STEPS = 16  # 빠르기 변화 위치를 1/16박 단위로 맞춤


class MidiLoadError(Exception):
    """MIDI 파일을 읽을 수 없을 때 발생하는 오류."""


@dataclass(frozen=True)
class MidiSong:
    """MIDI에서 읽은 곡: 템포, 멜로디(노래) 음, 반주 음."""

    tempo_bpm: float
    melody: tuple[QuantizedNote, ...]
    accompaniment: tuple[QuantizedNote, ...]
    tempo_changes: tuple[TempoChange, ...] = ()  # 첫 빠르기 포함, 박 단위 위치


def is_midi_file(path: str | Path) -> bool:
    return Path(path).suffix.lower() in MIDI_EXTENSIONS


def read_midi(path: str | Path, subdivision: int = DEFAULT_SUBDIVISION) -> MidiSong:
    """MIDI 파일을 읽는다. 피아노가 아닌 악기 트랙이 있으면 그 트랙을 멜로디로 본다."""
    file_path = Path(path)
    if not file_path.is_file():
        raise MidiLoadError(f"파일을 찾을 수 없습니다: {file_path}")
    try:
        midi = pretty_midi.PrettyMIDI(str(file_path))
    except Exception as error:
        raise MidiLoadError(f"MIDI 파일을 읽을 수 없습니다: {file_path} ({error})") from error

    tracks = [inst for inst in midi.instruments if not inst.is_drum and inst.notes]
    if not tracks:
        raise MidiLoadError(f"MIDI 파일에 음이 없습니다: {file_path}")

    melody_track = _find_melody_track(tracks)
    accompaniment = [
        _quantize(midi, n, subdivision)
        for track in tracks
        if track is not melody_track
        for n in track.notes
    ]
    melody = (
        [_quantize(midi, n, subdivision) for n in melody_track.notes] if melody_track else []
    )
    return MidiSong(
        tempo_bpm=_first_tempo(midi),
        melody=_sorted(melody),
        accompaniment=_sorted(accompaniment),
        tempo_changes=_tempo_changes(midi, subdivision),
    )


def _tempo_changes(midi: pretty_midi.PrettyMIDI, subdivision: int) -> tuple[TempoChange, ...]:
    """빠르기 변화를 박 단위 위치로 읽는다. 같은 박의 변화는 마지막 것만, 같은 빠르기 반복은 뺀다."""
    times, tempos = midi.get_tempo_changes()
    by_beat: dict[Fraction, float] = {}
    for time, bpm in zip(times, tempos):
        # 빠르기 변화 위치는 음표보다 촘촘하게(1/16박) 맞춘다. 작은 어긋남이 쌓이지 않게.
        beat = _snap_beats(midi.time_to_tick(time) / midi.resolution, TEMPO_POSITION_STEPS)
        by_beat[beat] = float(bpm)

    changes: list[TempoChange] = []
    for beat in sorted(by_beat):
        if changes and abs(changes[-1].bpm - by_beat[beat]) < 0.05:
            continue
        changes.append(TempoChange(beat=beat, bpm=by_beat[beat]))
    return tuple(changes)


def _find_melody_track(tracks: list[pretty_midi.Instrument]) -> pretty_midi.Instrument | None:
    if len(tracks) < 2:
        return None
    candidates = [t for t in tracks if t.program not in PIANO_PROGRAMS]
    return candidates[0] if candidates else None


def _first_tempo(midi: pretty_midi.PrettyMIDI) -> float:
    _, tempos = midi.get_tempo_changes()
    return float(tempos[0]) if len(tempos) else DEFAULT_TEMPO_BPM


def _snap_beats(beats: float, subdivision: int) -> Fraction:
    return Fraction(round(beats * subdivision), subdivision)


def _quantize(midi: pretty_midi.PrettyMIDI, note: pretty_midi.Note, subdivision: int) -> QuantizedNote:
    start = _snap_beats(midi.time_to_tick(note.start) / midi.resolution, subdivision)
    end = _snap_beats(midi.time_to_tick(note.end) / midi.resolution, subdivision)
    return QuantizedNote(
        pitch=note.pitch,
        velocity=note.velocity,
        start_beats=start,
        duration_beats=max(end - start, Fraction(1, subdivision)),
    )


def _sorted(notes: list[QuantizedNote]) -> tuple[QuantizedNote, ...]:
    return tuple(sorted(notes, key=lambda n: (n.start_beats, n.pitch)))
