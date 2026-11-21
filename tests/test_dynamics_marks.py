from fractions import Fraction

from transcriber.dynamics_marks import level_for, plan_dynamics
from transcriber.rhythm import QuantizedNote

BAR = Fraction(4)


def notes_with_measure_velocities(velocities):
    """마디마다 4분음표 4개, 마디별 세기를 정해서 만든다."""
    return tuple(
        QuantizedNote(pitch=60, velocity=v, start_beats=Fraction(m * 4 + b), duration_beats=Fraction(1))
        for m, v in enumerate(velocities)
        for b in range(4)
    )


def summary(marks):
    return [(int(m.beat // BAR) + 1, m.kind, m.text) for m in marks]


def test_velocity_levels():
    assert [level_for(v) for v in (30, 50, 65, 80, 95, 110)] == ["pp", "p", "mp", "mf", "f", "ff"]


def test_steady_loudness_gets_one_starting_mark():
    marks = plan_dynamics(notes_with_measure_velocities([80, 82, 78, 84, 80, 81, 79, 83]), BAR)

    assert summary(marks) == [(1, "level", "mf")]


def test_lasting_change_gets_new_mark():
    marks = plan_dynamics(notes_with_measure_velocities([50] * 4 + [95] * 4), BAR)

    assert summary(marks) == [(1, "level", "p"), (5, "level", "f")]


def test_short_spike_is_ignored():
    marks = plan_dynamics(notes_with_measure_velocities([80, 80, 105, 80, 80, 80, 80, 80]), BAR)

    assert summary(marks) == [(1, "level", "mf")]


def test_gradual_rise_gets_crescendo_before_new_level():
    marks = plan_dynamics(notes_with_measure_velocities([50, 50, 60, 70] + [95] * 4), BAR)

    assert summary(marks) == [(1, "level", "p"), (3, "crescendo", None), (5, "level", "f")]
    assert marks[1].end_beat == 16


def test_gradual_fall_gets_diminuendo():
    marks = plan_dynamics(notes_with_measure_velocities([95, 95, 85, 75] + [45] * 4), BAR)

    assert (3, "diminuendo", None) in summary(marks)
