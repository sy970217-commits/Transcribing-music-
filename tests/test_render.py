from fractions import Fraction

import pretty_midi
import pytest

from transcriber.render import EXIT_ERROR, EXIT_OK, ScoreLoadError, main, score_to_midi
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
