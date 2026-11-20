import numpy as np
import pytest
import soundfile as sf
from music21 import converter

from transcriber.cli import EXIT_ERROR, EXIT_OK, main, transcribe_file

SAMPLE_RATE = 22050
A4_MIDI, C5_MIDI = 69, 72


def write_melody_wav(path, midi_numbers, seconds_each=0.5):
    t = np.linspace(0, seconds_each, int(SAMPLE_RATE * seconds_each), endpoint=False)
    tones = [0.5 * np.sin(2 * np.pi * 440.0 * 2 ** ((n - A4_MIDI) / 12) * t) for n in midi_numbers]
    sf.write(path, np.concatenate(tones), SAMPLE_RATE)
    return path


@pytest.fixture(scope="module")
def melody_wav(tmp_path_factory):
    return write_melody_wav(tmp_path_factory.mktemp("audio") / "melody.wav", [A4_MIDI, C5_MIDI])


def test_creates_sheet_music_and_midi(melody_wav, tmp_path):
    result = transcribe_file(melody_wav, tmp_path, tempo_bpm=120)

    assert result.musicxml_path == tmp_path / "melody.musicxml"
    assert result.midi_path.exists()
    pitches = [p.midi for n in converter.parse(str(result.musicxml_path)).recurse().notes for p in n.pitches]
    assert pitches == [A4_MIDI, C5_MIDI]


def test_uses_given_tempo(melody_wav, tmp_path):
    result = transcribe_file(melody_wav, tmp_path, tempo_bpm=90)

    assert result.tempo_bpm == 90


def test_main_returns_ok_and_prints_paths(melody_wav, tmp_path, capsys):
    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "120"])

    assert exit_code == EXIT_OK
    assert "melody.musicxml" in capsys.readouterr().out


def test_main_writes_title_and_composer(melody_wav, tmp_path):
    args = ["--output-dir", str(tmp_path), "--tempo", "120", "--title", "시험곡", "--composer", "홍길동"]
    exit_code = main([str(melody_wav), *args])

    xml = (tmp_path / "melody.musicxml").read_text(encoding="utf-8")
    assert exit_code == EXIT_OK
    assert "<work-title>시험곡</work-title>" in xml
    assert '<creator type="composer">홍길동</creator>' in xml


def test_title_defaults_to_file_name(melody_wav, tmp_path):
    result = transcribe_file(melody_wav, tmp_path, tempo_bpm=120)

    assert "<work-title>melody</work-title>" in result.musicxml_path.read_text(encoding="utf-8")


def test_midi_file_becomes_score_with_melody_staff(tmp_path):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=90)
    piano, voice = pretty_midi.Instrument(program=0), pretty_midi.Instrument(program=52)
    piano.notes.append(pretty_midi.Note(velocity=80, pitch=48, start=0, end=1))
    voice.notes.append(pretty_midi.Note(velocity=80, pitch=72, start=0, end=1))
    midi.instruments.extend([piano, voice])
    midi.write(str(tmp_path / "song.mid"))

    result = transcribe_file(tmp_path / "song.mid", tmp_path / "out")

    loaded = converter.parse(str(result.musicxml_path))
    assert result.midi_path is None
    assert len(loaded.parts) == 3
    assert [p.midi for n in loaded.parts[0].recurse().notes for p in n.pitches] == [72]


def test_vocals_option_adds_melody_staff(melody_wav, tmp_path, monkeypatch):
    from transcriber import cli
    from transcriber.pitch import Note
    from transcriber.vocal_melody import VocalParts

    sung = (Note(start_seconds=0.0, end_seconds=0.5, pitch=76, velocity=90),)
    monkeypatch.setattr(
        cli,
        "extract_vocal_parts",
        lambda source, work_dir: VocalParts(melody=sung, accompaniment_path=source, has_voice=True),
    )

    result = transcribe_file(melody_wav, tmp_path, tempo_bpm=120, vocals=True)

    loaded = converter.parse(str(result.musicxml_path))
    assert result.voice_found is True
    assert len(loaded.parts) == 3
    assert [p.midi for n in loaded.parts[0].recurse().notes for p in n.pitches] == [76]


def test_main_warns_when_no_voice_found(melody_wav, tmp_path, monkeypatch, capsys):
    from transcriber import cli
    from transcriber.vocal_melody import VocalParts

    monkeypatch.setattr(
        cli,
        "extract_vocal_parts",
        lambda source, work_dir: VocalParts(melody=(), accompaniment_path=source, has_voice=False),
    )

    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "120", "--vocals"])

    assert exit_code == EXIT_OK
    assert "목소리를 찾지 못해" in capsys.readouterr().out


def test_main_reports_missing_file(tmp_path, capsys):
    exit_code = main([str(tmp_path / "nope.mp3")])

    assert exit_code == EXIT_ERROR
    assert "찾을 수 없습니다" in capsys.readouterr().err


def test_main_rejects_negative_tempo(melody_wav, tmp_path, capsys):
    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "-5"])

    assert exit_code == EXIT_ERROR
    assert "템포" in capsys.readouterr().err
