from pathlib import Path

import numpy as np
import pytest

import transcriber.analysis.notes as notes_module
from transcriber.analysis.notes import MIX, MIX_SETTINGS, TRACK_SETTINGS, clean_track, drop_bass_doubles, drop_quiet_notes, main, merge_tracks, recognize_notes, to_monophonic
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

    def fake_detect(path, onset_threshold, frame_threshold, min_note_ms, melodia_trick):
        calls.append((Path(path).stem, onset_threshold, frame_threshold))
        return PitchResult(notes=(n(60, 0, 1),), midi=None)

    monkeypatch.setattr(notes_module, "_loudness", lambda path: np.array([]))
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


def test_separated_piano_keeps_notes_longer_than_the_mix(monkeypatch, tmp_path):
    """분리한 피아노 트랙은 소리가 약해 울림 기준을 낮추고, 이어 붙이기를 끈다."""
    calls = []
    monkeypatch.setattr(
        notes_module, "detect_notes",
        lambda path, **k: calls.append(k) or PitchResult(notes=(), midi=None),
    )

    recognize_notes(tmp_path / "song.wav")

    assert calls[0]["frame_threshold"] == MIX_SETTINGS[1]
    assert TRACK_SETTINGS["piano"][1] < MIX_SETTINGS[1]
    assert calls[0]["melodia_trick"] is False


def test_cli_reports_bad_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_keeps_loudest_of_notes_starting_together():
    melody = to_monophonic((n(60, 0.0, 1.0, velocity=40), n(67, 0.01, 1.0, velocity=100)))

    assert [x.pitch for x in melody] == [67]


def test_cuts_previous_note_when_next_starts():
    melody = to_monophonic((n(60, 0.0, 2.0), n(62, 1.0, 2.0)))

    assert [(x.pitch, x.end_seconds) for x in melody] == [(60, 1.0), (62, 2.0)]


def test_merge_tracks_joins_all_tracks_in_start_order():
    found = {"vocals": (n(64, 1.0, 2.0),), "piano": (n(48, 0.0, 1.0), n(60, 1.0, 2.0))}
    assert [x.pitch for x in merge_tracks(found)] == [48, 60, 64]


def test_voice_note_an_octave_off_is_moved_back():
    line = (n(70, 0, 1), n(84, 1, 2), n(69, 2, 3), n(65, 3, 4), n(53, 4, 5), n(60, 5, 6))

    voice = clean_track("vocals", line)

    assert [x.pitch for x in voice] == [70, 72, 69, 65, 65, 60]  # 위·아래로 튄 음을 한 옥타브 옮김


def test_real_leaps_and_piano_notes_are_kept():
    leap = (n(67, 0, 1), n(60, 1, 2), n(67, 2, 3))  # 5도 내려갔다 올라오는 진짜 선율
    spike = (n(70, 0, 1), n(84, 1, 2), n(69, 2, 3))

    assert [x.pitch for x in clean_track("vocals", leap)] == [67, 60, 67]
    assert [x.pitch for x in clean_track("piano", spike)] == [70, 84, 69]


def test_voice_note_split_without_gap_is_joined():
    line = (n(65, 0, 0.5), n(65, 0.5, 1.2), n(67, 1.2, 2), n(67, 2.1, 3))

    voice = clean_track("vocals", line)

    # 틈 없이 쪼개진 같은 음은 한 음으로, 쉬었다가 다시 부른 같은 음은 그대로 둔다
    assert [(x.pitch, x.start_seconds, x.end_seconds) for x in voice] == [(65, 0, 1.2), (67, 1.2, 2), (67, 2.1, 3)]


def test_piano_repeated_notes_are_not_joined():
    line = (n(65, 0, 0.5), n(65, 0.5, 1.0))

    assert len(clean_track("piano", line)) == 2


def test_notes_where_the_voice_track_is_almost_silent_are_dropped():
    loudness = np.array([0.001] * 50 + [0.5] * 50)  # 0.02초마다: 앞 1초는 거의 조용, 뒤 1초는 노래
    found = (n(60, 0.2, 0.5), n(62, 1.2, 1.5), n(64, 0.9, 1.1))

    kept = drop_quiet_notes(found, loudness, 0.02)

    assert [x.pitch for x in kept] == [62, 64]  # 조용한 곳의 음만 버림, 노래에 걸친 음은 남김


def test_quiet_check_keeps_notes_when_loudness_is_missing():
    found = (n(60, 0, 1),)

    assert drop_quiet_notes(found, np.array([]), 0.02) == found


def test_piano_notes_doubling_the_bass_are_dropped():
    found = {
        "bass": (n(40, 0, 1),),
        "piano": (n(40, 0.5, 1.5), n(40, 2, 3), n(52, 0, 1)),
        "vocals": (n(40, 0, 1),),
    }

    cleaned = drop_bass_doubles(found)

    assert [(x.pitch, x.start_seconds) for x in cleaned["piano"]] == [(40, 2), (52, 0)]  # 겹친 같은 음만 버림
    assert cleaned["bass"] == found["bass"]
    assert cleaned["vocals"] == found["vocals"]


def test_without_bass_nothing_is_dropped():
    found = {"piano": (n(40, 0, 1),)}

    assert drop_bass_doubles(found) == found
