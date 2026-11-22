from fractions import Fraction


def test_each_hand_chooses_its_own_grid():
    from transcriber.rhythm import BeatNote, quantize_beat_notes

    # 왼손: 셋잇단음표(0, 1/3, 2/3) / 오른손: 8분음표(0, 1/2)
    left = tuple(BeatNote(pitch=48, velocity=80, start_beats=b / 3, end_beats=(b + 1) / 3) for b in range(3))
    right = tuple(BeatNote(pitch=72, velocity=80, start_beats=b / 2, end_beats=(b + 1) / 2) for b in range(2))

    starts = {(n.pitch, n.start_beats) for n in quantize_beat_notes(left + right, split_pitch=60)}

    assert {(48, Fraction(i, 3)) for i in range(3)} <= starts
    assert {(72, Fraction(0)), (72, Fraction(1, 2))} <= starts


def test_late_chord_does_not_hide_a_triplet():
    from transcriber.rhythm import BeatNote, quantize_beat_notes

    # 살짝 늦게(0.03박) 친 4음 화음 뒤에 셋잇단음표 두 음(조금 흔들림)
    chord = tuple(BeatNote(pitch=p, velocity=80, start_beats=0.03, end_beats=0.33) for p in (60, 64, 67, 72))
    rest = (
        BeatNote(pitch=61, velocity=80, start_beats=0.362, end_beats=0.66),
        BeatNote(pitch=61, velocity=80, start_beats=0.684, end_beats=1.0),
    )

    starts = sorted({n.start_beats for n in quantize_beat_notes(chord + rest)})

    assert starts == [Fraction(0), Fraction(1, 3), Fraction(2, 3)]
