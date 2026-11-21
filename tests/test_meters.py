from fractions import Fraction

import pytest

from transcriber.meters import (
    TimeSignatureChange,
    bar_length,
    measure_number_at,
    normalize_changes,
    parse_time_signature,
)


def ts(beat, text):
    return TimeSignatureChange(beat=Fraction(beat), text=text)


def test_bar_lengths_in_quarter_beats():
    assert bar_length("4/4") == 4
    assert bar_length("3/4") == 3
    assert bar_length("6/8") == 3
    assert bar_length("2/2") == 4


def test_unknown_time_signature_raises_clear_error():
    with pytest.raises(ValueError, match="알 수 없는 박자표"):
        parse_time_signature("세박자")


def test_adds_default_at_start_and_drops_repeats():
    changes = normalize_changes((ts(12, "3/4"), ts(24, "3/4")))

    assert changes == (ts(0, "4/4"), ts(12, "3/4"))


def test_measure_numbers_in_three_four():
    changes = (ts(0, "3/4"),)

    assert measure_number_at(0, changes) == 1
    assert measure_number_at(3, changes) == 2
    assert measure_number_at(8.5, changes) == 3


def test_measure_numbers_across_time_signature_change():
    # 1~2마디 4/4 (8박), 3마디부터 3/4
    changes = (ts(0, "4/4"), ts(8, "3/4"))

    assert measure_number_at(7, changes) == 2
    assert measure_number_at(8, changes) == 3
    assert measure_number_at(11, changes) == 4
