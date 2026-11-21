from fractions import Fraction

from transcriber.tempo_marks import TempoChange, plan_tempo_marks

BAR = Fraction(4)


def c(beat, bpm):
    return TempoChange(beat=Fraction(beat), bpm=bpm)


def kinds(marks):
    return [(m.kind, m.text or round(m.bpm)) for m in marks]


def test_new_tempo_held_for_a_bar_is_shown():
    marks = plan_tempo_marks((c(0, 90), c(16, 76)), total_beats=Fraction(64), bar_beats=BAR)

    assert kinds(marks) == [("shown", 76)]


def test_gradual_slowdown_becomes_rit_text():
    ramp = tuple(c(Fraction(16) + Fraction(i, 2), 90 - 5 * (i + 1)) for i in range(6))
    marks = plan_tempo_marks((c(0, 90), *ramp), total_beats=Fraction(64), bar_beats=BAR)

    assert marks[0].kind == "text" and marks[0].text == "rit."
    assert marks[0].beat == 16
    assert all(m.kind == "hidden" for m in marks[1:])
    assert len(marks) == 7


def test_gradual_speedup_becomes_accel_text():
    ramp = tuple(c(Fraction(16) + i, 60 + 5 * (i + 1)) for i in range(3))
    marks = plan_tempo_marks((c(0, 60), *ramp), total_beats=Fraction(64), bar_beats=BAR)

    assert marks[0].text == "accel."


def test_tiny_phrase_end_slowdown_is_hidden():
    # Finale가 프레이즈 끝에 넣는 아주 작은 늦춤 (90 → 88.5 → 다시 90)
    dips = (c(10, 89.5), c(10.5, 88.9), c(11, 88.5), c(12, 90))
    marks = plan_tempo_marks((c(0, 90), *dips), total_beats=Fraction(64), bar_beats=BAR)

    assert all(m.kind == "hidden" for m in marks)


def test_rit_then_new_tempo_like_gaeulkkot():
    # 가을꽃 70~73마디: rit. → 71마디 ♩=76 → 73마디 ♩=90
    ramp = tuple(c(Fraction(276) + Fraction(i, 2), 85 - 5 * i) for i in range(6))
    changes = (c(0, 90), *ramp, c(280, 76), c(288, 90))

    shown_or_text = [k for k in kinds(plan_tempo_marks(changes, Fraction(320), BAR)) if k[0] != "hidden"]

    assert shown_or_text == [("text", "rit."), ("shown", 76), ("shown", 90)]


def test_sudden_big_slowdown_becomes_fermata():
    # 가을꽃 끝: ♩=90에서 rit. 뒤 ♩=15.5로 확 느려짐 → 늘임표
    ramp = tuple(c(Fraction(293) + Fraction(i, 2), 85 - 5 * i) for i in range(5))
    changes = (c(0, 90), *ramp, c(298, 15.5))

    fermatas = [m for m in plan_tempo_marks(changes, Fraction(304), BAR) if m.kind == "fermata"]

    assert [(m.beat, m.end_beat) for m in fermatas] == [(298, 304)]


def test_fermata_in_the_middle_ends_when_tempo_returns():
    changes = (c(0, 90), c(15, 30), c(16, 90))

    fermatas = [m for m in plan_tempo_marks(changes, Fraction(64), BAR) if m.kind == "fermata"]

    assert [(m.beat, m.end_beat) for m in fermatas] == [(15, 16)]


def test_ordinary_rit_is_not_fermata():
    ramp = tuple(c(Fraction(16) + Fraction(i, 2), 85 - 5 * i) for i in range(6))

    marks = plan_tempo_marks((c(0, 90), *ramp), Fraction(64), BAR)

    assert not any(m.kind == "fermata" for m in marks)


def test_single_tempo_needs_no_marks():
    assert plan_tempo_marks((c(0, 90),), total_beats=Fraction(64), bar_beats=BAR) == ()
