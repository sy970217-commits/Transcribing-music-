from fractions import Fraction
from pathlib import Path

import numpy as np
import pretty_midi
import pytest
import soundfile as sf

from transcriber.render import (
    EXIT_ERROR,
    EXIT_OK,
    AudioRenderError,
    ScoreLoadError,
    find_fluidsynth,
    main,
    midi_to_audio,
    score_to_midi,
)
from transcriber.rhythm import QuantizedNote
from transcriber.score import build_score, save_musicxml

TEMPO = 120  # 1박 = 0.5초


def q(pitch, start, length=1):
    return QuantizedNote(pitch=pitch, velocity=80, start_beats=Fraction(start), duration_beats=Fraction(length))


@pytest.fixture
def score_file(tmp_path):
    melody = (q(72, 0), q(74, 1), q(76, 2, length=2))
    piano = (q(48, 0, length=4), q(64, 0, length=4))
    score = build_score(piano, tempo_bpm=TEMPO, melody=melody)
    return save_musicxml(score, tmp_path / "song.musicxml")


def all_notes(midi_path):
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    return sorted((round(n.start, 3), n.pitch) for inst in midi.instruments for n in inst.notes)


def test_score_becomes_midi_with_same_notes(score_file, tmp_path):
    midi_path = score_to_midi(score_file, tmp_path / "out")

    assert midi_path == tmp_path / "out" / "song.mid"
    assert all_notes(midi_path) == [(0.0, 48), (0.0, 64), (0.0, 72), (0.5, 74), (1.0, 76)]


def test_melody_plays_as_choir_and_piano_as_piano(score_file, tmp_path):
    midi = pretty_midi.PrettyMIDI(str(score_to_midi(score_file, tmp_path)))

    programs = {inst.program for inst in midi.instruments}
    melody_track = next(inst for inst in midi.instruments if any(n.pitch == 74 for n in inst.notes))
    assert melody_track.program == 52  # Choir Aahs
    assert programs == {0, 52}


def test_tempo_mark_is_kept(score_file, tmp_path):
    midi = pretty_midi.PrettyMIDI(str(score_to_midi(score_file, tmp_path)))

    assert midi.get_tempo_changes()[1][0] == pytest.approx(TEMPO, abs=0.5)


def test_tempo_changes_survive_score_and_midi(tmp_path):
    from transcriber.tempo_marks import TempoChange

    piano = tuple(q(60, beat) for beat in range(24))
    ramp = tuple(TempoChange(Fraction(8) + Fraction(i, 2), 85 - 5 * i) for i in range(4))
    changes = (TempoChange(Fraction(0), 90), *ramp, TempoChange(Fraction(12), 76))
    score_path = save_musicxml(
        build_score(piano, tempo_bpm=90, tempo_changes=changes), tmp_path / "song.musicxml"
    )

    xml = score_path.read_text(encoding="utf-8")
    tempos = pretty_midi.PrettyMIDI(str(score_to_midi(score_path, tmp_path))).get_tempo_changes()[1]

    assert ">rit.</words>" in xml
    assert "<per-minute>76</per-minute>" in xml
    assert [round(t) for t in tempos] == [90, 85, 80, 75, 70, 76]


SOUNDFONT = Path(__file__).resolve().parents[1] / "soundfonts" / "MuseScore_General.sf3"
needs_synth = pytest.mark.skipif(
    find_fluidsynth() is None or not SOUNDFONT.is_file(),
    reason="FluidSynth 또는 사운드폰트가 설치되지 않음",
)


@needs_synth
def test_midi_becomes_audible_wav(score_file, tmp_path):
    midi_path = score_to_midi(score_file, tmp_path)

    wav_path = midi_to_audio(midi_path, SOUNDFONT)

    samples, rate = sf.read(wav_path)
    assert wav_path == tmp_path / "song.wav"
    # 4박 @120 = 2초. 소리가 잦아드는 시간(잔향)이 뒤에 붙어 조금 더 길다
    assert 2.0 <= len(samples) / rate <= 10.0
    assert np.abs(samples).max() > 0.01  # 무음이 아님


def test_missing_soundfont_raises_clear_error(score_file, tmp_path):
    midi_path = score_to_midi(score_file, tmp_path)

    with pytest.raises(AudioRenderError, match="사운드폰트를 찾을 수 없습니다"):
        midi_to_audio(midi_path, tmp_path / "없음.sf3")


def test_missing_fluidsynth_raises_install_hint(score_file, tmp_path, monkeypatch):
    from transcriber import render

    monkeypatch.setattr(render, "find_fluidsynth", lambda: None)
    midi_path = score_to_midi(score_file, tmp_path)

    with pytest.raises(AudioRenderError, match="brew install fluid-synth"):
        midi_to_audio(midi_path, SOUNDFONT)


@needs_synth
def test_main_with_audio_option(score_file, tmp_path, capsys):
    exit_code = main([str(score_file), "--output-dir", str(tmp_path), "--audio", "--soundfont", str(SOUNDFONT)])

    assert exit_code == EXIT_OK
    assert "song.wav" in capsys.readouterr().out


MEASURE_PITCHES = (60, 62, 64, 65, 67, 69)  # 1~6마디에 온음표 하나씩: 도 레 미 파 솔 라


def write_measures_score(path, add_marks):
    """마디마다 다른 음 하나인 악보를 만든다. 연주 순서를 마디 번호로 확인하기 위함."""
    from music21 import meter, note, stream

    part = stream.Part()
    measures = []
    for number, pitch in enumerate(MEASURE_PITCHES, start=1):
        measure = stream.Measure(number=number)
        if number == 1:
            measure.insert(0, meter.TimeSignature("4/4"))
        measure.append(note.Note(pitch, quarterLength=4))
        measures.append(measure)
        part.append(measure)
    add_marks(part, measures)
    score = stream.Score()
    score.insert(0, part)
    return Path(score.write("musicxml", fp=str(path)))


def played_measures(midi_path):
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = sorted((n for inst in midi.instruments for n in inst.notes), key=lambda n: n.start)
    return [MEASURE_PITCHES.index(n.pitch) + 1 for n in notes]


def test_repeat_signs_play_twice(tmp_path):
    from music21 import bar

    def marks(part, ms):
        ms[0].leftBarline = bar.Repeat(direction="start")
        ms[1].rightBarline = bar.Repeat(direction="end")

    score_path = write_measures_score(tmp_path / "repeat.musicxml", marks)

    assert played_measures(score_to_midi(score_path, tmp_path)) == [1, 2, 1, 2, 3, 4, 5, 6]


def test_first_and_second_endings(tmp_path):
    from music21 import bar, spanner

    def marks(part, ms):
        ms[0].leftBarline = bar.Repeat(direction="start")
        ms[2].rightBarline = bar.Repeat(direction="end")
        part.insert(0, spanner.RepeatBracket(ms[2], number=1))
        part.insert(0, spanner.RepeatBracket(ms[3], number=2))

    score_path = write_measures_score(tmp_path / "volta.musicxml", marks)

    assert played_measures(score_to_midi(score_path, tmp_path)) == [1, 2, 3, 1, 2, 4, 5, 6]


def test_dal_segno_al_coda(tmp_path):
    from music21 import repeat

    def marks(part, ms):
        ms[1].insert(0, repeat.Segno())
        ms[2].insert(3.99, repeat.Coda("To Coda"))
        ms[3].insert(3.99, repeat.DalSegnoAlCoda())
        ms[4].insert(0, repeat.Coda())

    score_path = write_measures_score(tmp_path / "ds.musicxml", marks)

    assert played_measures(score_to_midi(score_path, tmp_path)) == [1, 2, 3, 4, 2, 3, 5, 6]


def test_dal_segno_without_segno_sign_raises_clear_error(tmp_path):
    from music21 import repeat

    def marks(part, ms):
        ms[2].insert(3.99, repeat.DalSegnoAlFine())

    score_path = write_measures_score(tmp_path / "broken_ds.musicxml", marks)

    with pytest.raises(ScoreLoadError, match="반복 기호가 잘못"):
        score_to_midi(score_path, tmp_path)


def test_dynamics_are_written_and_velocities_kept(tmp_path):
    soft_then_loud = tuple(
        QuantizedNote(pitch=60 + beat % 5, velocity=50 if beat < 16 else 95,
                      start_beats=Fraction(beat), duration_beats=Fraction(1))
        for beat in range(32)
    )
    score_path = save_musicxml(build_score(soft_then_loud, tempo_bpm=120), tmp_path / "dyn.musicxml")

    xml = score_path.read_text(encoding="utf-8")
    midi = pretty_midi.PrettyMIDI(str(score_to_midi(score_path, tmp_path)))
    velocities = [n.velocity for inst in midi.instruments for n in sorted(inst.notes, key=lambda n: n.start)]

    assert "<p />" in xml and "<f />" in xml
    assert velocities[:16] == [50] * 16 and velocities[16:] == [95] * 16


def test_missing_score_raises_clear_error(tmp_path):
    with pytest.raises(ScoreLoadError, match="찾을 수 없습니다"):
        score_to_midi(tmp_path / "없음.musicxml", tmp_path)


def test_finale_file_gets_export_hint(tmp_path):
    finale = tmp_path / "song.musx"
    finale.write_bytes(b"finale")

    with pytest.raises(ScoreLoadError, match="내보내기 → MusicXML"):
        score_to_midi(finale, tmp_path)


def test_broken_score_raises_clear_error(tmp_path):
    broken = tmp_path / "broken.musicxml"
    broken.write_text("<not really music>", encoding="utf-8")

    with pytest.raises(ScoreLoadError):
        score_to_midi(broken, tmp_path)


def test_main_prints_midi_path(score_file, tmp_path, capsys):
    exit_code = main([str(score_file), "--output-dir", str(tmp_path / "out")])

    assert exit_code == EXIT_OK
    assert "song.mid" in capsys.readouterr().out


def test_main_reports_error(tmp_path, capsys):
    exit_code = main([str(tmp_path / "없음.musicxml")])

    assert exit_code == EXIT_ERROR
    assert "찾을 수 없습니다" in capsys.readouterr().err
