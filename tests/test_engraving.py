import re
from fractions import Fraction

from transcriber.rhythm import QuantizedNote
from transcriber.score import build_score, save_musicxml


def q(pitch, start, length=1, velocity=80):
    return QuantizedNote(pitch=pitch, velocity=velocity, start_beats=Fraction(start), duration_beats=Fraction(length))


def triplets(pitch, beats):
    return tuple(q(pitch + i % 3, Fraction(b) + Fraction(i, 3), Fraction(1, 3)) for b in range(beats) for i in range(3))


def part_xml(xml, index):
    return re.findall(r"<part id=.*?</part>", xml, re.S)[index]


def staff_notes(part, staff):
    """그 단의 음표(쉼표 제외)"""
    return [
        n for n in re.findall(r"<note[ >].*?</note>", part, re.S) if f"<staff>{staff}</staff>" in n and "<pitch>" in n
    ]


def build(tmp_path, piano, melody=()):
    return save_musicxml(build_score(piano, tempo_bpm=90, melody=melody), tmp_path / "s.musicxml").read_text(
        encoding="utf-8"
    )


def test_triplet_numbers_go_outside_the_piano_staves(tmp_path):
    piano = triplets(72, 4) + triplets(48, 4)  # 오른손·왼손 모두 셋잇단음표

    piano_part = part_xml(build(tmp_path, piano), 0)

    upper = "".join(staff_notes(piano_part, 1))
    lower = "".join(staff_notes(piano_part, 2))
    assert 'placement="above"' in upper and 'placement="below"' not in upper
    assert 'placement="below"' in lower and 'placement="above"' not in lower


def test_two_voice_stems_follow_the_staff(tmp_path):
    # 위 단: 미(64)를 4박 누르고 위로 솔·라·솔·라 / 아래 단: 도(48)를 4박 누르고 미·솔·미·솔
    upper = (q(64, 0, 4), q(67, 0), q(69, 1), q(67, 2), q(69, 3))
    lower = (q(48, 0, 4), q(52, 0), q(55, 1), q(52, 2), q(55, 3))
    xml = save_musicxml(build_score(upper + lower, tempo_bpm=90, allow_voices=True), tmp_path / "s.musicxml")
    piano_part = part_xml(xml.read_text(encoding="utf-8"), 0)

    assert "<backup>" in piano_part  # 두 성부
    assert all("<stem>up</stem>" in n for n in staff_notes(piano_part, 1))
    assert all("<stem>down</stem>" in n for n in staff_notes(piano_part, 2))


def test_single_voice_stems_point_away_from_the_gap(tmp_path):
    piano = (q(60, 0), q(62, 1), q(59, 0), q(57, 1))  # 두 단 사이 가까운 음들

    piano_part = part_xml(build(tmp_path, piano), 0)

    assert all("<stem>up</stem>" in n for n in staff_notes(piano_part, 1))
    assert all("<stem>down</stem>" in n for n in staff_notes(piano_part, 2))


def test_melody_marks_go_above_because_lyrics_are_below(tmp_path):
    melody = triplets(72, 4)
    piano = tuple(q(48, b, 1) for b in range(4))

    melody_part = part_xml(build(tmp_path, piano, melody), 0)

    assert 'placement="below"' not in melody_part
    assert '<direction placement="above">' in melody_part  # 셈여림(mf)
    assert '<tuplet bracket="yes" number="1" placement="above"' in melody_part


def test_piano_dynamics_go_above_the_upper_staff(tmp_path):
    piano = tuple(q(72, b, 1, velocity=50) for b in range(16)) + tuple(q(48, b, 1, velocity=50) for b in range(16))

    piano_part = part_xml(build(tmp_path, piano), 0)

    dynamic = re.search(r"<direction[^>]*>\s*<direction-type>\s*<dynamics", piano_part)
    assert dynamic is not None and 'placement="above"' in dynamic.group(0)


def test_fermata_goes_above_melody_and_upper_staff_only(tmp_path):
    from transcriber.tempo_marks import TempoChange

    melody = (q(72, 0, 2), q(74, 2, 2), q(76, 4, 2), q(77, 6), q(79, 7))
    piano = tuple(q(64, b) for b in range(8)) + tuple(q(48, b) for b in range(8))
    changes = (TempoChange(Fraction(0), 120), TempoChange(Fraction(6), 30))
    score = build_score(piano, tempo_bpm=120, melody=melody, tempo_changes=changes)
    xml = save_musicxml(score, tmp_path / "s.musicxml").read_text(encoding="utf-8")

    melody_part, piano_part = part_xml(xml, 0), part_xml(xml, 1)
    assert melody_part.count('<fermata type="upright"') == 1
    assert "".join(staff_notes(piano_part, 1)).count('<fermata type="upright"') == 1
    assert "<fermata" not in "".join(staff_notes(piano_part, 2))  # 두 단 사이엔 두지 않음
    assert 'type="inverted"' not in xml
    last_melody_note = staff_notes(melody_part, 1)[-1] if "<staff>" in melody_part else re.findall(
        r"<note[ >].*?</note>", melody_part, re.S
    )[-1]
    assert "<fermata" in last_melody_note  # 곡의 마지막 음에
