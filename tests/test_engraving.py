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
