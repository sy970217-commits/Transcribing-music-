import numpy as np
import pytest
import soundfile as sf

from transcriber.analysis.beats import analyze_beats, bar_positions, choose_meter, main

RATE = 22050


def accents_for(pattern, bars=8):
    """맥박마다의 셈(정답 박자 패턴 반복 + 약간의 흔들림)"""
    rng = np.random.default_rng(0)
    values = np.tile(np.array(pattern, dtype=float), bars)
    return values + rng.normal(0, 0.05, len(values))


def test_four_four_and_waltz_and_compound_meters():
    assert choose_meter(accents_for([3, 0, 1, 0]), 0.6)[:2] == (1, 4)  # 4/4, ♩=100
    assert choose_meter(accents_for([3, 0, 0]), 0.5)[:2] == (1, 3)  # 3/4, ♩=120
    # 8분음표 맥박(0.33초)이 1·4번째에 셈 → 점4분음표 박 2개 = 6/8
    assert choose_meter(accents_for([3, 0, 0, 1.5, 0, 0]), 0.33)[:2] == (3, 2)


def test_pickup_phase_is_found():
    group, per_bar, phase = choose_meter(accents_for([0, 3, 0, 1]), 0.6)  # 둘째 맥박부터 마디 시작
    assert (group, per_bar, phase) == (1, 4, 1)


def test_bar_position_recovers_after_an_extra_beat():
    # 4/4로 3마디, 그다음 박 하나가 더 끼어든 뒤 다시 4/4 3마디
    pattern = [3, 0, 1, 0] * 3 + [0] + [3, 0, 1, 0] * 3
    positions = bar_positions(np.array(pattern, dtype=float), 4)

    downbeats = [i for i, p in enumerate(positions) if p == 0]
    assert downbeats == [0, 4, 8, 13, 17, 21]


def test_click_track_audio(tmp_path):
    # ♩=100 4/4: 첫 박은 낮고 센 소리, 나머지는 높고 약한 소리, 8마디
    beat = int(RATE * 0.6)
    audio = np.zeros(beat * 32, dtype=np.float32)
    t = np.arange(int(RATE * 0.1)) / RATE
    for i in range(32):
        freq, level = (80, 0.9) if i % 4 == 0 else (1000, 0.3)
        audio[i * beat : i * beat + len(t)] += level * np.sin(2 * np.pi * freq * t) * np.exp(-t * 30)
    path = tmp_path / "click.wav"
    sf.write(path, audio, RATE)

    result = analyze_beats(path)

    assert result.time_signature == "4/4"
    assert result.tempo_bpm == pytest.approx(100, abs=3)
    assert result.downbeats[1] - result.downbeats[0] == pytest.approx(2.4, abs=0.1)


def test_cli_reports_bad_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err
