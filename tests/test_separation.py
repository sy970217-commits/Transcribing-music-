import json

import numpy as np
import pytest
import soundfile as sf

from transcriber.analysis.separation import (
    DEFAULT_MODEL,
    MODEL_STEMS,
    SUMMARY_FILE,
    SeparationError,
    main,
    separate,
    stem_presence,
)

RATE = 22050


def tone(freq, seconds=12.0, level=0.5):
    t = np.arange(int(RATE * seconds)) / RATE
    return (level * np.sin(2 * np.pi * freq * t)).astype(np.float32)


def write(path, samples):
    sf.write(path, samples, RATE)
    return path


@pytest.fixture
def song(tmp_path):
    """피아노(440Hz) + 베이스(110Hz)가 섞인 12초 음원과, 정답 트랙"""
    piano, bass = tone(440), tone(110)
    return write(tmp_path / "song.wav", piano + bass), {"other": piano, "bass": bass}


def fake_separator(answers, calls):
    """정답 트랙을 그대로 돌려주는 가짜 분리기(실제 Demucs는 몇 분 걸려 테스트에서 쓰지 않음)"""

    def run(source, target, model):
        calls.append(model)
        target.mkdir(parents=True, exist_ok=True)
        silent = np.zeros_like(next(iter(answers.values())))
        return {
            name: write(target / f"{name}.wav", answers.get(name, silent))
            for name in MODEL_STEMS[model]
        }

    return run


def test_stems_are_saved_with_presence(tmp_path, song):
    path, answers = song
    calls = []

    result = separate(path, tmp_path / "out", separator=fake_separator(answers, calls))

    assert set(result.stems) == set(MODEL_STEMS[DEFAULT_MODEL])
    assert all(p.is_file() and p.parent == tmp_path / "out" / "song" / "분리" / DEFAULT_MODEL for p in result.stems.values())
    assert result.present("other") and result.present("bass")
    assert not result.present("vocals") and not result.present("drums")
    summary = json.loads((result.stems["bass"].parent / SUMMARY_FILE).read_text(encoding="utf-8"))
    assert summary["presence"]["drums"] == 0.0


def test_second_run_reuses_saved_stems(tmp_path, song):
    path, answers = song
    calls = []
    separate(path, tmp_path / "out", separator=fake_separator(answers, calls))

    again = separate(path, tmp_path / "out", separator=fake_separator(answers, calls))

    assert calls == [DEFAULT_MODEL]  # 두 번째에는 분리하지 않고 저장된 결과를 씀
    assert again.present("bass")


def test_presence_counts_loud_windows():
    mix = tone(440, seconds=20)
    quiet_half = np.concatenate([tone(440, seconds=10), np.zeros(RATE * 10, dtype=np.float32)])

    assert stem_presence(mix, mix) == 1.0
    assert stem_presence(quiet_half, mix) == pytest.approx(0.5)
    assert stem_presence(np.zeros_like(mix), mix) == 0.0


def test_four_stem_model_can_still_be_chosen(tmp_path, song):
    path, answers = song

    result = separate(path, tmp_path, model="htdemucs", separator=fake_separator(answers, []))

    assert set(result.stems) == {"vocals", "drums", "bass", "other"}


def test_missing_stem_and_unknown_model_are_errors(tmp_path, song):
    path, _ = song

    with pytest.raises(SeparationError):
        separate(path, tmp_path, model="없는모델")
    with pytest.raises(SeparationError):
        separate(path, tmp_path, separator=lambda s, t, m: {})


def test_cli_reports_bad_file(capsys):
    assert main(["없는파일.wav"]) == 1
    assert "오류" in capsys.readouterr().err


def test_near_silent_windows_are_ignored():
    # 15초 연주 + 15초 거의 무음(잔향). 무음 구간에 새어 나온 아주 작은 소리는 세지 않음
    mix = np.concatenate([tone(440, seconds=15), tone(440, seconds=15, level=0.001)])
    leak = np.concatenate([np.zeros(RATE * 15, dtype=np.float32), tone(60, seconds=15, level=0.0005)])

    assert stem_presence(leak, mix) == 0.0
