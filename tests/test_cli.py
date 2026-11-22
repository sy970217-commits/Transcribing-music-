import numpy as np
import pytest
import soundfile as sf
from music21 import converter

from transcriber.cli import EXIT_ERROR, EXIT_OK, main, transcribe_file

SAMPLE_RATE = 22050
A4_MIDI, C5_MIDI = 69, 72
TUNE = [69, 72, 74, 76, 72, 69, 72, 74]  # 4초: 박을 찾을 만큼 길게


def write_melody_wav(path, midi_numbers, seconds_each=0.5):
    t = np.linspace(0, seconds_each, int(SAMPLE_RATE * seconds_each), endpoint=False)
    tones = [0.5 * np.sin(2 * np.pi * 440.0 * 2 ** ((n - A4_MIDI) / 12) * t) for n in midi_numbers]
    sf.write(path, np.concatenate(tones), SAMPLE_RATE)
    return path


@pytest.fixture(scope="module")
def melody_wav(tmp_path_factory):
    return write_melody_wav(tmp_path_factory.mktemp("audio") / "melody.wav", TUNE)


def test_audio_becomes_sheet_and_score(melody_wav, tmp_path):
    result = transcribe_file(melody_wav, tmp_path, tempo_bpm=120)

    assert result.musicxml_path == tmp_path / "melody.musicxml"
    assert result.sheet_path == tmp_path / "melody_분석표.json"
    assert result.sheet_path.exists()
    pitches = {p.midi for n in converter.parse(str(result.musicxml_path)).recurse().notes for p in n.pitches}
    assert pitches and pitches <= set(TUNE)


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
    assert len(loaded.parts) == 3
    assert [p.midi for n in loaded.parts[0].recurse().notes for p in n.pitches] == [72]


def write_voice_and_piano_midi(path, melody_pitches):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano, voice = pretty_midi.Instrument(program=0), pretty_midi.Instrument(program=52)
    piano.notes.append(pretty_midi.Note(velocity=80, pitch=48, start=0, end=1))
    for i, pitch in enumerate(melody_pitches):
        voice.notes.append(pretty_midi.Note(velocity=80, pitch=pitch, start=i * 0.5, end=(i + 1) * 0.5))
    midi.instruments.extend([piano, voice])
    midi.write(str(path))
    return path


def test_main_adds_lyrics_from_file(tmp_path, capsys):
    song = write_voice_and_piano_midi(tmp_path / "song.mid", [72, 74, 76])
    lyrics = tmp_path / "가사.txt"
    lyrics.write_text("가을-", encoding="utf-8")

    exit_code = main([str(song), "--output-dir", str(tmp_path), "--lyrics", str(lyrics)])

    xml = (tmp_path / "song.musicxml").read_text(encoding="utf-8")
    assert exit_code == EXIT_OK
    assert "<text>가</text>" in xml and "<text>을</text>" in xml
    assert "음절 3개 → 멜로디 음표 3개" in capsys.readouterr().out


def test_main_warns_about_left_over_lyrics(tmp_path, capsys):
    song = write_voice_and_piano_midi(tmp_path / "song.mid", [72, 74])
    lyrics = tmp_path / "가사.txt"
    lyrics.write_text("가을 꽃 피네", encoding="utf-8")

    exit_code = main([str(song), "--output-dir", str(tmp_path), "--lyrics", str(lyrics)])

    assert exit_code == EXIT_OK
    assert "가사 3자가 남았어요" in capsys.readouterr().out


def test_main_puts_lyrics_on_audio_melody(melody_wav, tmp_path, capsys):
    lyrics = tmp_path / "가사.txt"
    lyrics.write_text("가을", encoding="utf-8")

    args = [str(melody_wav), "--output-dir", str(tmp_path), "--lyrics", str(lyrics)]
    exit_code = main(args)

    xml = (tmp_path / "melody.musicxml").read_text(encoding="utf-8")
    assert exit_code == EXIT_OK
    assert "<text>가</text>" in xml and "<text>을</text>" in xml
    assert "음절 2개 → 멜로디 음표 2개" in capsys.readouterr().out


def test_main_uses_given_time_signature(melody_wav, tmp_path):
    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "120", "--time-signature", "3/4"])

    xml = (tmp_path / "melody.musicxml").read_text(encoding="utf-8")
    assert exit_code == EXIT_OK
    assert "<beats>3</beats>" in xml


def test_main_rejects_unknown_time_signature(melody_wav, tmp_path, capsys):
    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "120", "--time-signature", "세박자"])

    assert exit_code == EXIT_ERROR
    assert "알 수 없는 박자표" in capsys.readouterr().err


def test_midi_pedal_becomes_ped_marks(tmp_path):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)
    piano = pretty_midi.Instrument(program=0)
    for beat in range(8):
        piano.notes.append(pretty_midi.Note(velocity=80, pitch=48 + beat % 3, start=beat * 0.5, end=beat * 0.5 + 0.5))
    piano.control_changes.extend(
        [pretty_midi.ControlChange(64, 127, 0.0), pretty_midi.ControlChange(64, 0, 2.0)]
    )
    midi.instruments.append(piano)
    midi.write(str(tmp_path / "pedal.mid"))

    result = transcribe_file(tmp_path / "pedal.mid", tmp_path / "out")

    xml = result.musicxml_path.read_text(encoding="utf-8")
    assert '<pedal number="1" sign="yes" type="start"' in xml
    assert '<pedal number="1" sign="yes" type="stop"' in xml


def test_rolled_chord_in_midi_gets_arpeggio_sign(tmp_path):
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(initial_tempo=120)  # 1박 = 0.5초
    piano = pretty_midi.Instrument(program=0)
    for i, pitch in enumerate((64, 67, 72, 76)):  # 아래에서 위로 0.1박씩 늦게
        piano.notes.append(pretty_midi.Note(velocity=80, pitch=pitch, start=i * 0.05, end=2.0))
    midi.instruments.append(piano)
    midi.write(str(tmp_path / "roll.mid"))

    result = transcribe_file(tmp_path / "roll.mid", tmp_path / "out")

    xml = result.musicxml_path.read_text(encoding="utf-8")
    assert xml.count("<arpeggiate") == 4  # 화음의 네 음 모두에 표시
    assert xml.count("<chord />") == 3  # 네 음이 한 화음으로 묶임


def test_main_reports_missing_file(tmp_path, capsys):
    exit_code = main([str(tmp_path / "nope.mp3")])

    assert exit_code == EXIT_ERROR
    assert "찾을 수 없습니다" in capsys.readouterr().err


def test_main_rejects_negative_tempo(melody_wav, tmp_path, capsys):
    exit_code = main([str(melody_wav), "--output-dir", str(tmp_path), "--tempo", "-5"])

    assert exit_code == EXIT_ERROR
    assert "템포" in capsys.readouterr().err
