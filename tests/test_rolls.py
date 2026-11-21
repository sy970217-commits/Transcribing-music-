from transcriber.rhythm import BeatNote
from transcriber.rolls import mark_rolled_chords


def n(pitch, start, end):
    return BeatNote(pitch=pitch, velocity=80, start_beats=start, end_beats=end)


def test_rolled_chord_like_gaeulkkot_measure_71():
    # 가을꽃 71마디: 베이스 두 음은 함께, 오른손 화음은 아래에서 위로 펼쳐 침
    notes = (n(28, 0.0, 4), n(40, 0.0, 4), n(74, 0.0, 4), n(77, 0.18, 4), n(80, 0.35, 4), n(83, 0.53, 4))

    result = {x.pitch: x for x in mark_rolled_chords(notes)}

    assert all(result[p].rolled and result[p].start_beats == 0.0 for p in (74, 77, 80, 83))
    assert not result[28].rolled and not result[40].rolled


def test_plain_chord_is_not_rolled():
    notes = (n(60, 0, 1), n(64, 0, 1), n(67, 0, 1))

    assert not any(x.rolled for x in mark_rolled_chords(notes))


def test_broken_chord_figure_is_not_rolled():
    # 16분음표로 펼친 화음(각 음이 다음 음 전에 끝남)은 아르페지오가 아님
    notes = (n(60, 0, 0.25), n(64, 0.25, 0.5), n(67, 0.5, 0.75), n(72, 0.75, 1))

    assert not any(x.rolled for x in mark_rolled_chords(notes))


def test_triplets_are_not_rolled():
    notes = (n(60, 0, 2), n(64, 1 / 3, 2), n(67, 2 / 3, 2))

    assert not any(x.rolled for x in mark_rolled_chords(notes))


def test_two_staggered_notes_are_not_enough():
    notes = (n(60, 0, 2), n(64, 0.1, 2))

    assert not any(x.rolled for x in mark_rolled_chords(notes))
