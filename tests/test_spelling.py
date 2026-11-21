from music21 import key, note, stream

from transcriber.spelling import respell_part, spell


def test_sharp_key_uses_sharp_names():
    assert spell(63, key.Key("A")).nameWithOctave == "D#4"


def test_flat_key_uses_flat_names():
    assert spell(66, key.Key("E-")).nameWithOctave == "G-4"
    assert spell(70, key.Key("F")).nameWithOctave == "B-4"


def test_minor_key_leading_tone_is_raised():
    # 마단조의 이끎음은 D♯ (E♭이 아님)
    assert spell(75, key.Key("e")).nameWithOctave == "D#5"


def test_scale_notes_keep_scale_names():
    # 올림바장조(F♯ major)의 E♯은 F가 아니라 E♯
    assert spell(65, key.Key("F#")).name == "E#"
    # 내림사장조(G♭ major)의 C♭은 B가 아니라 C♭, 옥타브도 맞게
    assert spell(71, key.Key("G-")).nameWithOctave == "C-5"


def test_borrowed_notes_in_major_are_lowered():
    # 가을꽃 PDF 33·36마디: 사장조인데 E♭ (단조에서 빌려 온 ♭6)
    assert spell(63, key.Key("G")).name == "E-"
    assert spell(70, key.Key("G")).name == "B-"  # ♭3
    assert spell(65, key.Key("G")).name == "F"  # ♭7은 제자리표 F


def test_leading_notes_in_major_are_raised():
    # 가을꽃 PDF 30마디: 사장조의 G♯ (♯1)
    assert spell(68, key.Key("G")).name == "G#"
    assert spell(73, key.Key("G")).name == "C#"  # ♯4


def test_raised_fourth_in_flat_key_is_natural_sign():
    # 내림마장조의 ♯4는 A♭을 올린 A(제자리표)
    assert spell(69, key.Key("E-")).name == "A"


def test_c_major_keeps_common_names():
    assert spell(70, key.Key("C")).name == "B-"
    assert spell(66, key.Key("C")).name == "F#"


def test_respell_part_follows_key_change():
    part = stream.Part()
    part.insert(0, key.Key("E-"))
    part.insert(0, note.Note(63))  # 내림마장조: E♭
    part.insert(4, key.Key("E"))
    part.insert(4, note.Note(63))  # 마장조: D♯

    respell_part(part)

    assert [n.pitch.name for n in part.flatten().notes] == ["E-", "D#"]
    assert [n.pitch.midi for n in part.flatten().notes] == [63, 63]  # 소리는 그대로
