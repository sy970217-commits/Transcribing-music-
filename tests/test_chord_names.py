import pytest

from transcriber.chord_names import NOTE_NAMES, chord_name, main, pitches_from_intervals


def name(*intervals, bass=0):
    return chord_name(pitches_from_intervals(intervals, bass))


def test_four_triads_on_c():
    assert name(0, 4, 3) == "CM"
    assert name(0, 3, 4) == "Cm"
    assert name(0, 3, 3) == "Cdim"
    assert name(0, 4, 4) == "Caug"


def test_note_names_follow_the_numbers():
    assert NOTE_NAMES == ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    assert [name(0, 4, 3, bass=b) for b in (2, 7, 10, 11)] == ["DM", "GM", "A#M", "BM"]


def test_inversions_get_slash_bass():
    assert name(0, 3, 5) == "G#M/C"  # 도·미♭·라♭ = 라♭(G#) 장3화음, 베이스 C
    assert name(0, 5, 4) == "FM/C"  # 도·파·라 = F 장3화음 2전위
    assert name(0, 3, 5, bass=4) == "CM/E"  # 미·솔·도 = C 장3화음 1전위


def test_augmented_prefers_the_bass_as_root():
    assert name(0, 4, 4, bass=4) == "Eaug"  # 미·솔#·도(=시#) 증3화음은 어느 음이든 근음이 될 수 있어 맨 아래 음을 근음으로


def test_octaves_and_doubled_notes_are_ignored():
    assert chord_name((48, 64, 67, 72)) == "CM"  # 도3·미4·솔4·도5
    assert chord_name((52, 60, 67)) == "CM/E"  # 미3·도4·솔4


def test_unknown_sets_return_none():
    assert chord_name((60, 62)) is None
    assert chord_name((60, 62, 64, 67)) is None  # 도·레·미·솔은 정해 둔 코드가 아님
    assert chord_name(()) is None


def test_cli_prints_the_name(capsys):
    assert main(["0", "4", "3"]) == 0
    assert capsys.readouterr().out.strip() == "CM"
    assert main(["0", "3", "4", "--bass", "9"]) == 0
    assert capsys.readouterr().out.strip() == "Am"
    with pytest.raises(SystemExit):
        main([])


def test_seventh_chords_on_c():
    assert name(0, 4, 3, 3) == "C7"
    assert name(0, 4, 3, 4) == "CM7"
    assert name(0, 3, 4, 3) == "Cm7"
    assert name(0, 3, 3, 4) == "Cm7b5"
    assert name(0, 3, 3, 3) == "Cdim7"


def test_seventh_chord_inversions_and_symmetric_dim7():
    assert name(0, 3, 3, 2, bass=4) == "C7/E"  # 미·솔·시♭·도
    assert name(0, 1, 4, 3, bass=11) == "CM7/B"  # 시·도·미·솔
    assert name(0, 3, 3, 3, bass=9) == "Adim7"  # 감7화음은 맨 아래 음을 근음으로
    assert name(0, 4, 3, 2, bass=3) == "Cm7/D#"  # 미♭·솔·시♭·도 (E♭6와 같은 음)
