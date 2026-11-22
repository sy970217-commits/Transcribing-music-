import json
from fractions import Fraction
from pathlib import Path

from transcriber.analysis.beats import BeatAnalysis
from transcriber.analysis.expression import DynamicSpan, ExpressionResult, PedalSpan
from transcriber.analysis.harmony import ChordSegment, HarmonyResult
from transcriber.analysis.melody import MelodyNote, MelodyResult
from transcriber.analysis.rhythm import RhythmNote, RhythmResult
from transcriber.analysis.sheet import AnalysisSheet, main, save_sheet, to_plain
from transcriber.analysis.structure import Section, StructureResult
from transcriber.analysis.tonality import KeyResult, KeySegment
from transcriber.chord_names import Chord

BEATS = BeatAnalysis(beats=(0.0, 0.5), downbeats=(0.0,), time_signature="4/4", beats_per_bar=4,
                     pulses_per_beat=2, tempo_bpm=120.0, pickup_beats=0)


def small_sheet() -> AnalysisSheet:
    return AnalysisSheet(
        beats=BEATS,
        rhythm=RhythmResult((RhythmNote(60, Fraction(0), Fraction(3, 2), 70),), "4/4", Fraction(1)),
        harmony=HarmonyResult((ChordSegment(Fraction(0), Fraction(4), Chord(0, "M", 0)),)),
        key=KeyResult((KeySegment(Fraction(0), Fraction(4), 0, "major"),)),
        structure=StructureResult((Section(Fraction(0), Fraction(4), "A"),)),
        expression=ExpressionResult((DynamicSpan(Fraction(0), Fraction(4), "mf"),), (PedalSpan(Fraction(0), Fraction(4)),)),
        melody=MelodyResult((MelodyNote(60, Fraction(0), Fraction(3, 2), "아"),), (Fraction(0),)),
    )


def test_fractions_become_text():
    plain = to_plain(small_sheet())
    assert plain["rhythm"]["notes"][0] == {"pitch": 60, "start": "0", "length": "3/2", "velocity": 70}
    assert plain["melody"]["notes"][0]["lyric"] == "아"
    assert plain["harmony"]["chords"][0]["chord"] == {"root": 0, "kind": "M", "bass": 0}


def test_save_sheet_writes_json(tmp_path):
    path = save_sheet(small_sheet(), tmp_path / "곡_분석표.json")
    data = json.loads(path.read_text(encoding="utf-8"))
    assert set(data) == {"beats", "rhythm", "harmony", "key", "structure", "expression", "melody", "separation", "accompaniment"}
    assert data["key"]["keys"][0]["mode"] == "major"


def test_cli_missing_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_paths_become_text():
    assert to_plain({"vocals": Path("a/vocals.wav")}) == {"vocals": "a/vocals.wav"}


def test_backing_is_placed_without_triplets_when_voice_is_split(monkeypatch):
    import pytest

    import transcriber.analysis.beats as beats_mod
    import transcriber.analysis.harmony as harmony_mod
    import transcriber.analysis.notes as notes_mod
    import transcriber.analysis.rhythm as rhythm_mod
    from transcriber.analysis.sheet import analyze_song
    from transcriber.pitch import Note

    class Stop(Exception):
        pass

    voice = (Note(start_seconds=0.0, end_seconds=0.5, pitch=60, velocity=70),)
    piano = (Note(start_seconds=0.0, end_seconds=0.5, pitch=48, velocity=70),)
    calls = []

    def fake_quantize(notes, beats, allow_triplets=True):
        calls.append(({n.pitch for n in notes}, allow_triplets))
        return RhythmResult((), "4/4", Fraction(1))

    def stop(*args, **kwargs):
        raise Stop

    monkeypatch.setattr(beats_mod, "analyze_beats", lambda path: BEATS)
    monkeypatch.setattr(notes_mod, "recognize_notes", lambda path, sep: {"vocals": voice, "piano": piano})
    monkeypatch.setattr(rhythm_mod, "quantize_notes", fake_quantize)
    monkeypatch.setattr(harmony_mod, "analyze_harmony", stop)

    with pytest.raises(Stop):
        analyze_song("곡.wav")

    assert ({48}, False) in calls
