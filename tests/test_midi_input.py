from fractions import Fraction

import pretty_midi
import pytest

from transcriber.midi_input import MidiLoadError, is_midi_file, read_midi

TEMPO = 90
SECONDS_PER_BEAT = 60 / TEMPO
CHOIR_AAHS = 52  # 합창 "아~" 소리 악기
PIANO = 0


def add_notes(instrument, notes):
    for pitch, start_beat, beats in notes:
        start = start_beat * SECONDS_PER_BEAT
        instrument.notes.append(
            pretty_midi.Note(velocity=80, pitch=pitch, start=start, end=start + beats * SECONDS_PER_BEAT)
        )


def write_song(path, with_voice=True):
    midi = pretty_midi.PrettyMIDI(initial_tempo=TEMPO)
    piano = pretty_midi.Instrument(program=PIANO)
    add_notes(piano, [(48, 0, 2), (55, 0, 2), (64, 2, 1)])
    midi.instruments.append(piano)
    if with_voice:
        voice = pretty_midi.Instrument(program=CHOIR_AAHS)
        add_notes(voice, [(67, 0, 1), (69, 1, 0.5), (71, 1.5, 0.5)])
        midi.instruments.append(voice)
    midi.write(str(path))
    return path


def test_voice_track_becomes_melody(tmp_path):
    song = read_midi(write_song(tmp_path / "song.mid"))

    assert [n.pitch for n in song.melody] == [67, 69, 71]
    assert [n.start_beats for n in song.melody] == [0, 1, Fraction(3, 2)]
    assert [n.duration_beats for n in song.melody] == [1, Fraction(1, 2), Fraction(1, 2)]


def test_piano_track_becomes_accompaniment(tmp_path):
    song = read_midi(write_song(tmp_path / "song.mid"))

    assert [n.pitch for n in song.accompaniment] == [48, 55, 64]


def test_reads_tempo(tmp_path):
    song = read_midi(write_song(tmp_path / "song.mid"))

    assert song.tempo_bpm == pytest.approx(TEMPO, abs=0.5)


def test_reads_time_signature_and_its_change(tmp_path):
    from transcriber.meters import TimeSignatureChange

    midi = pretty_midi.PrettyMIDI(initial_tempo=TEMPO)
    piano = pretty_midi.Instrument(program=PIANO)
    add_notes(piano, [(60, 0, 1), (62, 6, 1)])
    midi.instruments.append(piano)
    midi.time_signature_changes.append(pretty_midi.TimeSignature(3, 4, 0))
    midi.time_signature_changes.append(pretty_midi.TimeSignature(6, 8, 6 * SECONDS_PER_BEAT))
    midi.write(str(tmp_path / "waltz.mid"))

    song = read_midi(tmp_path / "waltz.mid")

    assert song.time_signatures == (
        TimeSignatureChange(beat=Fraction(0), text="3/4"),
        TimeSignatureChange(beat=Fraction(6), text="6/8"),
    )


def test_piano_only_file_has_no_melody(tmp_path):
    song = read_midi(write_song(tmp_path / "piano.mid", with_voice=False))

    assert song.melody == ()
    assert len(song.accompaniment) == 3


def test_recognizes_midi_extensions():
    assert is_midi_file("a.mid") and is_midi_file("b.MIDI")
    assert not is_midi_file("c.wav")


def test_missing_file_raises_clear_error(tmp_path):
    with pytest.raises(MidiLoadError, match="찾을 수 없습니다"):
        read_midi(tmp_path / "nope.mid")


def test_broken_file_raises_clear_error(tmp_path):
    broken = tmp_path / "broken.mid"
    broken.write_bytes(b"not midi")

    with pytest.raises(MidiLoadError, match="읽을 수 없습니다"):
        read_midi(broken)
