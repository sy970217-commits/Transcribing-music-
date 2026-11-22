import json
import sys
from pathlib import Path

import pretty_midi
import pytest

sys.path.insert(0, str(Path(__file__).parent / "benchmark"))
import beat_set as bench  # noqa: E402


@pytest.mark.parametrize("name", list(bench.SONGS))
def test_answer_times_match_the_midi_file(name):
    """정답지의 박·첫 박 시각이 MIDI 파일을 MIDI 라이브러리로 읽어 계산한 시각과 같은지(정답지 검산)."""
    song = bench.SONGS[name]
    folder = bench.SET_DIR / name
    answer = json.loads((folder / "answer.json").read_text(encoding="utf-8"))
    midi = pretty_midi.PrettyMIDI(str(folder / "problem.mid"))

    def time_of(quarters):
        return midi.tick_to_time(round(quarters * midi.resolution))

    assert answer["downbeats"] == pytest.approx(
        [time_of(song.pickup + i * song.bar_quarters) for i in range(song.bars)], abs=1e-3
    )
    assert answer["beats"][:5] == pytest.approx(
        [time_of(song.pickup % song.beat_quarters + i * song.beat_quarters) for i in range(5)], abs=1e-3
    )
    assert answer == bench.answer_of(song)  # 저장된 정답지 = 곡 정의로 다시 만든 정답지


def test_compound_meter_counts_dotted_quarters():
    six_eight = bench.SONGS["03_8분의6박자"]

    assert six_eight.beat_quarters == bench.Fraction(3, 2)
    assert bench.answer_of(six_eight)["beats_per_bar"] == 2
    assert bench.answer_of(six_eight)["tempo_bpm"][0]["bpm"] == 60
