import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import note_set as bench  # noqa: E402


@pytest.mark.parametrize("name", list(bench.PROBLEMS))
def test_answer_notes_match_the_midi_files(name):
    """정답지의 음 목록이 곡을 만든 MIDI에서 다시 뽑은 음과 같은지(정답지 검산)."""
    _, tracks, separated = bench.PROBLEMS[name]
    answer = json.loads((bench.SET_DIR / name / "answer.json").read_text(encoding="utf-8"))

    assert answer["소리_분리"] == separated
    for track, mids in tracks.items():
        expected = sorted((n for m in mids for n in bench.notes_of(bench.BENCH / m)), key=lambda n: (n[1], n[0]))
        assert answer["트랙"][track] == expected


def test_perfect_answer_scores_one_and_empty_scores_zero():
    reference = [[60, 0.0, 0.5], [64, 0.5, 1.0]]

    assert bench.score(reference, reference)["시작_F1"] == 1.0
    assert bench.score(reference, [])["시작_F1"] == 0.0
