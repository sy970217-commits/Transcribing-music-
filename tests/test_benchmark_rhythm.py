import json
import sys
from fractions import Fraction
from pathlib import Path

import mido
import pytest

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import rhythm_set as bench  # noqa: E402


@pytest.mark.parametrize("name", list(bench.PROBLEMS))
def test_answer_matches_the_midi_file(name):
    """정답지의 음(높이·위치·길이)이 MIDI 파일의 틱을 4분음표 단위로 바꾼 값과 같은지(정답지 검산)."""
    midi = mido.MidiFile(bench.midi_of(name))
    started, notes, now = {}, [], 0
    for message in mido.merge_tracks(midi.tracks):
        now += message.time
        if message.type == "note_on" and message.velocity > 0 and message.channel != bench.DRUM_CHANNEL:
            started[message.note] = now
        elif message.type in ("note_off", "note_on") and message.note in started:
            begin = started.pop(message.note)
            notes.append([message.note, str(Fraction(begin, midi.ticks_per_beat)),
                          str(Fraction(now - begin, midi.ticks_per_beat))])
    answer = json.loads((bench.SET_DIR / name / "answer.json").read_text(encoding="utf-8"))

    assert sorted(answer["notes"]) == sorted(notes)


def test_new_song_has_dotted_triplet_and_sixteenth_notes():
    lengths = {length for _, _, length in bench.answer_of(bench.NEW_SONGS["06_리듬_여러가지"])["notes"]}

    assert {"3/2", "1/3", "1/4", "3/4", "4"} <= lengths


def test_score_is_perfect_for_the_answer_and_zero_for_nothing():
    reference = [[60, "0", "1"], [64, "1/2", "1/2"], [67, "4/3", "1/3"]]

    assert bench.score(reference, reference)["둘다_F1"] == 1.0
    assert bench.score(reference, [])["위치_F1"] == 0.0


def test_score_counts_wrong_length_only_in_length_accuracy():
    reference = [[60, "0", "1"], [62, "1", "1"]]
    estimate = [[60, Fraction(0), Fraction(1)], [62, Fraction(1), Fraction(1, 2)]]

    result = bench.score(reference, estimate)

    assert result["위치_F1"] == 1.0
    assert result["길이_정확도"] == 0.5
    assert result["둘다_F1"] == 0.5
