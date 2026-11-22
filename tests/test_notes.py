from pathlib import Path

import pytest

import transcriber.analysis.notes as notes_module
from transcriber.analysis.notes import MIX, TRACK_SETTINGS, clean_track, main, recognize_notes
from transcriber.analysis.separation import Separation
from transcriber.pitch import Note, PitchResult


def n(pitch, start, end, velocity=80):
    return Note(start_seconds=start, end_seconds=end, pitch=pitch, velocity=velocity)


def test_out_of_range_notes_are_dropped():
    found = (n(40, 0, 1), n(60, 1, 2), n(90, 2, 3))

    assert [x.pitch for x in clean_track("vocals", found)] == [60]  # 목소리 음역 C3~C6
    assert [x.pitch for x in clean_track("bass", found)] == [40, 60]


def test_voice_and_bass_keep_one_note_at_a_time():
    chord = (n(60, 0.0, 1.0, 90), n(64, 0.01, 1.0, 50), n(67, 0.5, 1.5, 80))

    voice = clean_track("vocals", chord)
    piano = clean_track("piano", chord)

    assert [x.pitch for x in voice] == [60, 67]  # 동시에 시작한 음 중 센 음, 뒤 음이 오면 앞 음을 끊음
    assert voice[0].end_seconds == pytest.approx(0.5)
    assert len(piano) == 3  # 피아노는 화음 그대로


def test_each_present_stem_is_read_with_its_settings(monkeypatch, tmp_path):
    calls = []

    def fake_detect(path, onset_threshold, frame_threshold, min_note_ms):
        calls.append((Path(path).stem, onset_threshold, frame_threshold))
        return PitchResult(notes=(n(60, 0, 1),), midi=None)

    monkeypatch.setattr(notes_module, "detect_notes", fake_detect)
    stems = {name: tmp_path / f"{name}.wav" for name in ("vocals", "drums", "bass", "piano", "other")}
    separation = Separation(
        source=tmp_path / "song.wav", model="htdemucs_6s", stems=stems,
        presence={"vocals": 1.0, "drums": 1.0, "bass": 0.0, "piano": 1.0, "other": 0.0},
    )

    found = recognize_notes(tmp_path / "song.wav", separation)

    assert set(found) == {"vocals", "piano"}  # 드럼(음높이 없음)과 없다고 판단된 트랙은 뺌
    assert ("piano", *TRACK_SETTINGS["piano"][:2]) in calls


def test_without_separation_the_whole_mix_is_read(monkeypatch, tmp_path):
    monkeypatch.setattr(notes_module, "detect_notes", lambda path, **k: PitchResult(notes=(n(60, 0, 1),), midi=None))

    assert list(recognize_notes(tmp_path / "song.wav")) == [MIX]


def test_cli_reports_bad_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err
