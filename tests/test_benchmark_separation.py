import json
import sys
from pathlib import Path

import mido
import numpy as np

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import separation_set as bench  # noqa: E402

SET_DIR = bench.SET_DIR


def note_count(path: Path) -> int:
    return sum(1 for track in mido.MidiFile(path).tracks for m in track if m.type == "note_on" and m.velocity > 0)


def test_every_problem_has_matching_answers():
    for name, tracks in bench.PROBLEMS.items():
        folder = SET_DIR / name
        answer = json.loads((folder / "answer.json").read_text(encoding="utf-8"))
        stems = sorted(t.stem for t in tracks)

        assert answer["있어야_하는_트랙"] == stems
        assert sorted(answer["있어야_하는_트랙"] + answer["없어야_하는_트랙"]) == sorted(bench.ALL_STEMS)
        # 문제 MIDI의 음 = 정답 트랙 MIDI 음의 합
        assert note_count(folder / "problem.mid") == sum(note_count(folder / f"answer_{s}.mid") for s in stems)


def test_saved_midi_matches_the_song_definition(tmp_path):
    for name, tracks in bench.PROBLEMS.items():
        bench.write_midi(tracks, tmp_path / "again.mid")
        assert (tmp_path / "again.mid").read_bytes() == (SET_DIR / name / "problem.mid").read_bytes()


def test_scores_reward_close_estimates():
    t = np.arange(22050) / 22050
    reference = np.sin(2 * np.pi * 440 * t)
    noisy = reference + 0.1 * np.sin(2 * np.pi * 97 * t)

    assert bench.si_sdr(reference * 0.5, reference) > 60  # 크기만 다르면 거의 완벽
    assert 15 < bench.si_sdr(noisy, reference) < 25
    assert bench.leakage_db(reference * 0.01, reference) < -39
