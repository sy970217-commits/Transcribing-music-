import re
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


def test_lyrics_are_written_under_melody(tmp_path):
    melody = (q(72, 0), q(74, 1), q(76, 2))
    score = build_score((), tempo_bpm=90, info=ScoreInfo(lyrics=("가", "", "을")), melody=melody)

    xml = save_musicxml(score, tmp_path / "song.musicxml").read_text(encoding="utf-8")
    assert "<text>가</text>" in xml
    assert "<text>을</text>" in xml


def test_lyrics_without_melody_raise_clear_error():
    with pytest.raises(ValueError, match="멜로디 단이 필요"):
        build_score((q(C4, 0),), tempo_bpm=90, info=ScoreInfo(lyrics=("가",)))


def test_melody_only_score_is_allowed():
    score = build_score((), tempo_bpm=90, melody=(q(72, 0),))

    assert len(score.parts) == 3


def test_three_four_time_signature_is_written(tmp_path):
    from transcriber.meters import TimeSignatureChange

    waltz = tuple(q(C4 + i % 3, i) for i in range(12))
    score = build_score(waltz, tempo_bpm=90, time_signatures=(TimeSignatureChange(Fraction(0), "3/4"),))

    xml = save_musicxml(score, tmp_path / "waltz.musicxml").read_text(encoding="utf-8")
    assert "<beats>3</beats>" in xml and "<beat-type>4</beat-type>" in xml
    assert xml.count("<measure ") == 4  # 12박 ÷ 3박 = 4마디 (피아노 두 단은 한 악기)


def test_time_signature_change_in_the_middle(tmp_path):
    from transcriber.meters import TimeSignatureChange

    notes = tuple(q(C4, i) for i in range(14))  # 4/4 2마디(8박) + 3/4 2마디(6박)
    changes = (TimeSignatureChange(Fraction(0), "4/4"), TimeSignatureChange(Fraction(8), "3/4"))

    xml = save_musicxml(build_score(notes, 90, time_signatures=changes), tmp_path / "s.musicxml").read_text(
        encoding="utf-8"
    )

    assert xml.count("<measure ") == 4  # 4마디 (피아노 두 단은 한 악기)
    assert "<beats>4</beats>" in xml and "<beats>3</beats>" in xml


def test_time_signature_from_info_overrides(tmp_path):
    from transcriber.meters import TimeSignatureChange

    score = build_score(
        tuple(q(C4, i) for i in range(6)),
        tempo_bpm=90,
        info=ScoreInfo(time_signature="6/8"),
        time_signatures=(TimeSignatureChange(Fraction(0), "4/4"),),
    )

    xml = save_musicxml(score, tmp_path / "s.musicxml").read_text(encoding="utf-8")
    assert "<beats>6</beats>" in xml and "<beat-type>8</beat-type>" in xml


def test_key_change_measure_number_counts_three_four():
    from transcriber.meters import TimeSignatureChange

    # 3/4에서 조가 바뀌는 곳: 16마디 × 3박 = 48박 뒤 → 17마디
    three = (TimeSignatureChange(Fraction(0), "3/4"),)
    notes = tuple(q(G_MAJOR_SCALE[i % 8], i) for i in range(48)) + tuple(
        q(A_MAJOR_SCALE[i % 8], 48 + i) for i in range(48)
    )

    assert "17마디부터" in key_name_of(build_score(notes, tempo_bpm=90, time_signatures=three))


def test_notes_are_spelled_for_the_key(tmp_path):
    # 가장조 음계 + D♯(63) 하나: E♭이 아니라 D♯으로 적혀야 한다
    notes = repeat_scale(A_MAJOR_SCALE, 4) + (q(63, 16),)
    score = build_score(notes, tempo_bpm=90, info=ScoreInfo(key_name="A"))

    xml = save_musicxml(score, tmp_path / "s.musicxml").read_text(encoding="utf-8")
    assert "<step>D</step>\n          <alter>1</alter>" in xml
    assert "<step>E</step>\n          <alter>-1</alter>" not in xml


def test_double_barline_before_key_change(tmp_path):
    notes = repeat_scale(G_MAJOR_SCALE, 16) + repeat_scale(A_MAJOR_SCALE, 16, start_beat=64)

    xml = save_musicxml(build_score(notes, tempo_bpm=90), tmp_path / "s.musicxml").read_text(encoding="utf-8")

    # 16마디 끝 겹세로줄 1개 (피아노 두 단은 한 악기라 세로줄도 하나)
    assert xml.count("<bar-style>light-light</bar-style>") == 1
    import re

    measure_16 = re.search(r'<measure[^>]*number="16".*?</measure>', xml, re.S).group(0)
    assert "light-light" in measure_16


def test_piano_is_one_instrument_with_two_staves(tmp_path):
    notes = (q(C4, 0), q(59, 0), q(C3, 1))  # 가운데 도(C4)는 높은음자리표, 시(B3)는 낮은음자리표

    xml = save_musicxml(build_score(notes, tempo_bpm=90), tmp_path / "s.musicxml").read_text(encoding="utf-8")

    assert xml.count("<score-part ") == 1
    assert "<staves>2</staves>" in xml  # 두 단으로 된 악기는 MusicXML 기본값으로 중괄호로 묶인다
    c4 = xml.split("<step>C</step>")[1].split("</note>")[0]
    assert "<octave>4</octave>" in c4 and "<staff>1</staff>" in c4
    b3 = xml.split("<step>B</step>")[1].split("</note>")[0]
    assert "<octave>3</octave>" in b3 and "<staff>2</staff>" in b3


def printed_accidentals(xml):
    """마디별로 [(음이름+옥타브, 보이는 임시표)]"""
    import re

    result = {}
    for number, body in re.findall(r'<measure[^>]*number="(\d+)"[^>]*>(.*?)</measure>', xml, re.S):
        shown = []
        for one in re.findall(r"<note[ >].*?</note>", body, re.S):
            step = re.search(r"<step>(\w)</step>", one)
            if step is None:
                continue
            octave = re.search(r"<octave>(\d)</octave>", one).group(1)
            accidental = re.search(r"<accidental[^>]*>([\w-]+)</accidental>", one)
            shown.append((step.group(1) + octave, accidental.group(1) if accidental else ""))
        result[int(number)] = shown
    return result


def test_accidentals_only_where_needed(tmp_path):
    def quarter(pitch_number, beat):
        return q(pitch_number, beat)

    # 올림다단조(조표 ♯4: F C G D)
    notes = (
        quarter(68, 0), quarter(73, 1), quarter(75, 2), quarter(66, 3),  # 1마디: 조표 안의 음
        quarter(75, 4), quarter(74, 5), quarter(75, 6), quarter(73, 7),  # 2마디: D♯ D♮ D♯
        quarter(74, 8), quarter(73, 9), quarter(71, 10), quarter(73, 11),  # 3마디: D♮, B
        quarter(75, 12), quarter(63, 13), quarter(73, 14), quarter(73, 15),  # 4마디: D♯5, D♯4
        quarter(74, 16), quarter(62, 17), quarter(73, 18), quarter(73, 19),  # 5마디: D♮5, D♮4
    )
    xml = save_musicxml(build_score(notes, 90, ScoreInfo(key_name="c#")), tmp_path / "a.musicxml").read_text(
        encoding="utf-8"
    )
    shown = printed_accidentals(xml)

    assert [a for _, a in shown[1]] == ["", "", "", ""]  # 조표에 있는 음에는 표시 없음
    assert [a for _, a in shown[2][:3]] == ["", "natural", "sharp"]  # 같은 마디에서 바뀌면 표시
    assert shown[3][0] == ("D5", "natural") and shown[3][2] == ("B4", "")  # B에 쓸데없는 ♮ 없음
    assert [a for _, a in shown[4][:2]] == ["", ""]  # 앞 마디를 알려 주는 친절 임시표 없음
    assert [a for _, a in shown[5][:2]] == ["natural", "natural"]  # 조표와 다르면 옥타브마다 표시


def test_grand_staff_distance_is_set(tmp_path):
    from music21 import converter

    path = save_musicxml(build_score((q(C4, 0), q(C3, 0)), tempo_bpm=90), tmp_path / "s.musicxml")
    xml = path.read_text(encoding="utf-8")

    defaults = xml.split("<defaults>")[1].split("</defaults>")[0]
    assert '<staff-layout number="2">' in defaults
    grand_staff = defaults.split('<staff-layout number="2">')[1].split("</staff-layout>")[0]
    assert "<staff-distance>20</staff-distance>" in grand_staff  # 두 단의 C4 덧줄이 같은 높이(바꾸지 않음)
    assert '<staff-layout number="1">' not in defaults  # 공통 설정에는 피아노 두 단 간격만
    assert defaults.index("</scaling>") < defaults.index("<staff-layout")  # MusicXML 순서 규칙
    assert len(converter.parse(str(path)).parts) == 2  # 파일이 여전히 올바르게 읽힘


def test_melody_to_piano_distance_in_every_piano_measure(tmp_path):
    melody = (q(72, 0), q(74, 5))  # 2마디
    path = save_musicxml(build_score((q(C4, 0), q(C3, 5)), tempo_bpm=90, melody=melody), tmp_path / "s.musicxml")
    xml = path.read_text(encoding="utf-8")

    melody_part, piano_part = re.findall(r"<part id=.*?</part>", xml, re.S)
    assert piano_part.count("<print>") == piano_part.count("<measure ") == 2  # 어느 줄이든 간격이 같게
    piano_print = piano_part.split("<print>")[1].split("</print>")[0]
    assert "<print>" not in melody_part
    assert piano_print.count("<staff-layout") == 2
    assert '<staff-layout number="1">\n          <staff-distance>120' in piano_print
    assert '<staff-layout number="2">\n          <staff-distance>20' in piano_print


def test_piano_alone_has_no_melody_distance(tmp_path):
    xml = save_musicxml(build_score((q(C4, 0), q(C3, 0)), tempo_bpm=90), tmp_path / "s.musicxml").read_text(
        encoding="utf-8"
    )

    assert "<print>" not in xml


def test_no_double_barline_without_changes(tmp_path):
    xml = save_musicxml(build_score(repeat_scale(G_MAJOR_SCALE, 8), 90), tmp_path / "s.musicxml").read_text(
        encoding="utf-8"
    )

    assert "light-light" not in xml


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


def test_key_change_lands_on_exact_measure():
    # 19마디부터 조가 바뀜 (4마디 단위 경계가 아님)
    notes = repeat_scale(G_MAJOR_SCALE, 18) + repeat_scale(A_MAJOR_SCALE, 14, start_beat=72)

    assert "19마디부터" in key_name_of(build_score(notes, tempo_bpm=90))


BOTH_KEYS_TONES = (69, 71, 74, 76, 78)  # 라 시 레 미 파#: 사장조와 가장조에 모두 있는 음


def test_key_change_goes_where_melody_starts_after_bridge():
    # 1~16마디 G장조, 17~18마디는 두 조 모두에 맞는 다리, 19마디부터 A장조 노래 시작
    piano = (
        repeat_scale(G_MAJOR_SCALE, 16)
        + repeat_scale(BOTH_KEYS_TONES, 2, start_beat=64)
        + repeat_scale(A_MAJOR_SCALE, 14, start_beat=72)
    )
    melody = tuple(q(81, 72 + beat) for beat in range(8))

    score = build_score(piano, tempo_bpm=90, melody=melody)

    assert "19마디부터" in key_name_of(score)


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
