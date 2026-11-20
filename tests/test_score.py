from fractions import Fraction

import pytest
from music21 import chord, converter, note, tempo

from transcriber.rhythm import QuantizedNote
from transcriber.score import ScoreInfo, build_score, key_name_of, save_musicxml

C4, E4, G4, C3 = 60, 64, 67, 48


def q(pitch, start, length=1):
    return QuantizedNote(
        pitch=pitch,
        velocity=80,
        start_beats=Fraction(start),
        duration_beats=Fraction(length),
    )


def pitches_in(part):
    found = []
    for element in part.recurse().notes:
        if isinstance(element, chord.Chord) and len(element.pitches) > 1:
            found.append(tuple(sorted(p.midi for p in element.pitches)))
        elif isinstance(element, chord.Chord):
            found.append(element.pitches[0].midi)
        elif isinstance(element, note.Note):
            found.append(element.pitch.midi)
    return found


def test_splits_notes_into_right_and_left_hand():
    score = build_score((q(C4, 0), q(C3, 0)), tempo_bpm=120)
    treble, bass = score.parts

    assert pitches_in(treble) == [C4]
    assert pitches_in(bass) == [C3]


def test_notes_at_same_time_become_a_chord():
    score = build_score((q(C4, 0), q(E4, 0), q(G4, 0)), tempo_bpm=120)

    assert pitches_in(score.parts[0]) == [(C4, E4, G4)]


def test_melody_gets_its_own_staff_on_top():
    melody = (q(72, 0), q(74, 1))
    score = build_score((q(C4, 0), q(C3, 0)), tempo_bpm=90, melody=melody)
    top, treble, bass = score.parts

    assert pitches_in(top) == [72, 74]
    assert pitches_in(treble) == [C4]
    assert pitches_in(bass) == [C3]


def test_melody_only_score_is_allowed():
    score = build_score((), tempo_bpm=90, melody=(q(72, 0),))

    assert len(score.parts) == 3


def test_overlapping_notes_do_not_create_tie_fragments():
    # 길게 누른 도 위에 미, 솔이 차례로 들어오는 경우
    notes = (q(C4, 0, length=3), q(E4, 1), q(G4, 2))
    part = build_score(notes, tempo_bpm=120).parts[0]

    elements = list(part.recurse().notes)
    assert pitches_in(part) == [C4, E4, G4]
    assert all(element.tie is None for element in elements)


def test_notes_starting_together_share_shortest_gap():
    notes = (q(C4, 0, length=2), q(E4, 0, length=1), q(G4, 1))
    first = list(build_score(notes, tempo_bpm=120).parts[0].recurse().notes)[0]

    assert first.quarterLength == 1


def test_saved_musicxml_can_be_read_back(tmp_path):
    melody = (q(C4, 0), q(E4, 1), q(G4, 2, length=Fraction(1, 2)))
    path = save_musicxml(build_score(melody, tempo_bpm=90), tmp_path / "out" / "song.musicxml")

    loaded = converter.parse(str(path))
    marks = list(loaded.recurse().getElementsByClass(tempo.MetronomeMark))
    assert pitches_in(loaded.parts[0]) == [C4, E4, G4]
    assert marks[0].number == 90


G_MAJOR_SCALE = (67, 69, 71, 72, 74, 76, 78, 79)  # 솔 라 시 도 레 미 파# 솔


def g_major_melody():
    return tuple(q(p, i) for i, p in enumerate(G_MAJOR_SCALE))


def test_detects_key_signature_automatically():
    score = build_score(g_major_melody(), tempo_bpm=90)

    # 사장조와 마단조는 조표가 같다(♯ 1개). 악보에 보이는 건 조표다.
    assert "조표 ♯ 1개" in key_name_of(score)


def test_uses_given_key():
    score = build_score(g_major_melody(), tempo_bpm=90, info=ScoreInfo(key_name="D"))

    assert key_name_of(score) == "D major, 조표 ♯ 2개"


A_MAJOR_SCALE = (69, 71, 73, 74, 76, 78, 80, 81)  # 라 시 도# 레 미 파# 솔# 라


def repeat_scale(scale, measures, start_beat=0):
    """4/4 기준으로 음계를 4분음표로 반복해 원하는 마디 수만큼 채운다."""
    return tuple(q(scale[i % len(scale)], start_beat + i) for i in range(measures * 4))


def test_marks_key_change_in_the_middle():
    notes = repeat_scale(G_MAJOR_SCALE, 16) + repeat_scale(A_MAJOR_SCALE, 16, start_beat=64)

    description = key_name_of(build_score(notes, tempo_bpm=90))

    assert "조표 ♯ 1개 → 17마디부터" in description
    assert description.endswith("조표 ♯ 3개")


def test_one_misread_section_does_not_delay_key_change():
    # 가을꽃에서 본 경우: 바뀐 조(♯3) 구간 중간에 한 구간만 ♯4(E장조)로 읽힘
    e_major_scale = (76, 78, 80, 81, 83, 85, 87, 88)
    notes = (
        repeat_scale(G_MAJOR_SCALE, 16)
        + repeat_scale(A_MAJOR_SCALE, 8, start_beat=64)
        + repeat_scale(e_major_scale, 4, start_beat=96)
        + repeat_scale(A_MAJOR_SCALE, 16, start_beat=112)
    )

    assert "17마디부터" in key_name_of(build_score(notes, tempo_bpm=90))


def test_short_visit_to_other_key_is_not_a_key_change():
    notes = (
        repeat_scale(G_MAJOR_SCALE, 16)
        + repeat_scale(A_MAJOR_SCALE, 4, start_beat=64)
        + repeat_scale(G_MAJOR_SCALE, 16, start_beat=80)
    )

    assert "→" not in key_name_of(build_score(notes, tempo_bpm=90))


def test_unknown_key_raises_clear_error():
    with pytest.raises(ValueError, match="알 수 없는 조성"):
        build_score(g_major_melody(), tempo_bpm=90, info=ScoreInfo(key_name="H#q"))


def test_title_and_credits_are_saved(tmp_path):
    info = ScoreInfo(title="가을꽃", composer="작곡가", lyricist="작사가")
    path = save_musicxml(build_score(g_major_melody(), 90, info), tmp_path / "song.musicxml")

    xml = path.read_text(encoding="utf-8")
    assert "<work-title>가을꽃</work-title>" in xml
    assert '<creator type="composer">작곡가</creator>' in xml
    assert '<creator type="lyricist">작사가</creator>' in xml
    assert "<fifths>1</fifths>" in xml  # 조표 ♯ 1개


def test_empty_notes_raise_clear_error():
    with pytest.raises(ValueError, match="음이 없습니다"):
        build_score((), tempo_bpm=120)
