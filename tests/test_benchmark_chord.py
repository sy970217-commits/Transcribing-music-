import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import chord_set as bench  # noqa: E402


@pytest.mark.parametrize("name", list(bench.PROBLEMS))
def test_answer_file_matches_the_song_plan(name):
    song, plan, _ = bench.PROBLEMS[name]
    saved = json.loads((bench.SET_DIR / name / "answer.json").read_text(encoding="utf-8"))

    assert saved == bench.answer_of(song, plan)


def test_new_song_covers_many_chord_kinds_and_inversions():
    names = {name for _, _, name in bench.answer_of(*bench.PROBLEMS["07_화음_여러가지"][:2])["chords"]}

    assert {"Am", "Dm7", "G7", "CM7", "Bdim", "Caug", "Bm7b5", "Dm/F", "CM/E"} <= names


def test_pickup_bar_has_no_chord():
    chords = json.loads((bench.SET_DIR / "05_못갖춘마디" / "answer.json").read_text(encoding="utf-8"))["chords"]

    assert chords[0] == ["0", "1", "N"]


def test_split_name_reads_root_kind_and_bass():
    assert bench.split_name("C#m7/E") == ("C#", "m7", "E")
    assert bench.split_name("G7") == ("G", "7", "G")
    assert bench.split_name("N") == ("N", "", "N")


def test_score_separates_root_kind_and_inversion():
    reference = [["0", "2", "CM/E"], ["2", "4", "Am"]]

    assert bench.score(reference, reference)["자리바꿈까지_정확도"] == 1.0
    result = bench.score(reference, [["0", "2", "CM"], ["2", "4", "A7"]])
    assert result == {"근음_정확도": 1.0, "코드_정확도": 0.5, "자리바꿈까지_정확도": 0.0}
    assert bench.score(reference, [])["근음_정확도"] == 0.0
