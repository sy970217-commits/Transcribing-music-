"""분석기 B단계: 박·박자 분석. 음원에서 박 위치, 마디 첫 박 위치, 박자표, 빠르기를 찾는다.

방법
1. 맥박(펄스) 찾기: librosa 박 추적으로 고르게 반복되는 맥박 위치를 찾는다.
   맥박은 실제 박일 수도, 8분음표처럼 더 잘게 쪼갠 단위일 수도 있다.
2. 맥박마다 '셈'을 잰다: 베이스(낮은 음) 시작, 화음 바뀜, 전체 소리 시작 세기를 합친다.
   마디 첫 박에는 보통 베이스가 들어오고 화음이 바뀐다.
3. 후보 박자 중 가장 잘 맞는 것을 고른다.
   - 한 박 = 맥박 1·2·3개 (3개면 6/8·9/8·12/8 같은 겹박자)
   - 한 마디 = 박 2·3·4개
   - 마디가 시작하는 맥박 위치(못갖춘마디 처리)
   점수 = 셈 패턴이 그 박자의 본보기(마디 첫 박 2, 다른 박 시작 1, 나머지 맥박 0)와 얼마나 닮았는지(상관계수)
          - 한 박 빠르기가 세기 편한 빠르기(100)에서 멀수록 감점 (55~145 밖은 제외)
          + 흔한 박자표일수록 조금 가산(4/4 > 3/4·6/8 > 2/4·12/8 > 9/8)
   맥박 2개를 한 박으로 묶는 것은 맥박이 너무 빨라 그대로는 박으로 셀 수 없을 때만 쓴다.
4. 마디 첫 박 따라가기: 박마다 '마디 안 몇 번째 박인지'를 정하되, 보통은 1→2→3→4→1로 넘어가고
   빠르기가 바뀌는 곳 등에서 박을 하나 더/덜 셌을 때만 순서를 건너뛸 수 있게(감점) 한다(비터비 방식).

실행: uv run beats 곡.wav
"""

import argparse
import math
import sys
from dataclasses import dataclass
from pathlib import Path

import librosa
import numpy as np

from transcriber.audio_io import AudioLoadError, load_audio

HOP = 512
PULSE_PRIOR_BPM = 120.0  # 맥박을 찾을 때 기대 빠르기(이 근처에서 잘 잡힘, 문제지로 확인)
# 맥박을 찾을 때 빠르기를 얼마나 일정하게 지킬지(librosa 기본 100). 낮추면 느려지거나 빨라지는 곳을 더 잘 따라간다
# (문제지 빠르기 변화 곡 박_정확도 0.94→0.97, 다른 곡은 그대로)
PULSE_TIGHTNESS = 20.0
BASS_MAX_HZ = 200.0  # 이보다 낮은 소리를 '베이스'로 본다
COMFORT_BPM = 100.0  # 사람이 세기 편한 박 빠르기
SOUND_START_RATIO = 0.01  # 연주 시작을 찾는 소리 크기 기준(가장 큰 소리 대비)
TEMPO_PENALTY = 0.3  # 한 박 빠르기가 COMFORT_BPM에서 한 옥타브(2배) 벗어날 때 감점(본보기 닮음 점수 -1~1 기준)
MIN_BEAT_BPM, MAX_BEAT_BPM = 55.0, 145.0  # 사람이 세는 박 빠르기 범위
BAR_JUMP_COST = 3.0  # 마디 안 박 순서를 건너뛸 때의 감점
METER_PRIOR = {"4/4": 0.3, "3/4": 0.15, "6/8": 0.15, "2/4": 0.0, "12/8": 0.0, "9/8": -0.1}
# (한 박에 들어가는 맥박 수, 한 마디 박 수) → 박자표
METERS = {
    (1, 2): "2/4", (1, 3): "3/4", (1, 4): "4/4",
    (2, 2): "2/4", (2, 3): "3/4", (2, 4): "4/4",
    (3, 2): "6/8", (3, 3): "9/8", (3, 4): "12/8",
}


@dataclass(frozen=True)
class BeatAnalysis:
    """박·박자 분석 결과. 시각은 모두 초."""

    beats: tuple[float, ...]
    downbeats: tuple[float, ...]
    time_signature: str
    beats_per_bar: int
    pulses_per_beat: int  # 3이면 겹박자(한 박이 셋으로 나뉨)
    tempo_bpm: float  # 한 박 기준 빠르기(가운데 값)
    pickup_beats: int  # 첫 마디 첫 박 앞의 박 수(못갖춘마디)


def analyze_beats(audio_path: str | Path) -> BeatAnalysis:
    """음원의 박·박자를 분석한다."""
    audio = load_audio(audio_path)
    samples, rate = audio.samples, audio.sample_rate
    pulses = _track_pulses(samples, rate)
    if len(pulses) < 4:
        raise ValueError(f"박을 찾지 못했어요(소리가 너무 짧거나 고르지 않음): {audio_path}")
    accents = pulse_accents(samples, rate, pulses)
    group, per_bar, phase = choose_meter(accents, float(np.median(np.diff(pulses))))
    beat_index = [i for i in range(len(pulses)) if (i - phase) % group == 0]
    beats = tuple(round(float(pulses[i]), 4) for i in beat_index)
    positions = bar_positions(accents[beat_index], per_bar, first=(phase // group))
    downbeat_index = [beat_index[k] for k, p in enumerate(positions) if p == 0]
    downbeats = tuple(round(float(pulses[i]), 4) for i in downbeat_index)
    first_bar_pulse = downbeat_index[0] if downbeat_index else 0
    return BeatAnalysis(
        beats=beats,
        downbeats=downbeats,
        time_signature=METERS[(group, per_bar)],
        beats_per_bar=per_bar,
        pulses_per_beat=group,
        tempo_bpm=round(60.0 / float(np.median(np.diff(beats))), 2),
        pickup_beats=sum(1 for i in beat_index if i < first_bar_pulse),
    )


def _track_pulses(samples: np.ndarray, rate: int) -> np.ndarray:
    """맥박 위치(초). 박 추적기는 곡 처음 몇 박을 건너뛰므로, 연주 시작까지 같은 간격으로 앞쪽을 채운다
    (못갖춘마디를 세려면 첫 소리의 박이 있어야 한다)."""
    envelope = librosa.onset.onset_strength(y=samples, sr=rate, hop_length=HOP)
    _, tracked = librosa.beat.beat_track(
        onset_envelope=envelope, sr=rate, hop_length=HOP, start_bpm=PULSE_PRIOR_BPM,
        tightness=PULSE_TIGHTNESS, units="time"
    )
    pulses = list(np.asarray(tracked, dtype=float))
    if len(pulses) < 2 or envelope.max() <= 0:
        return np.asarray(pulses)
    # 연주 시작 = 소리 크기가 곡에서 가장 큰 소리의 1%(-40dB)를 처음 넘는 순간. 작은 못갖춘마디 한 음도 잡힌다
    loudness = librosa.feature.rms(y=samples, hop_length=HOP)[0]
    first_sound = float(librosa.frames_to_time(np.argmax(loudness >= SOUND_START_RATIO * loudness.max()), sr=rate, hop_length=HOP))
    period = float(np.median(np.diff(pulses)))
    while pulses[0] - period >= first_sound - 0.3 * period:
        pulses.insert(0, max(0.0, pulses[0] - period))
    return np.asarray(pulses)


def pulse_accents(samples: np.ndarray, rate: int, pulses: np.ndarray) -> np.ndarray:
    """맥박마다 '셈'(클수록 마디·박의 시작일 가능성이 큼). 세 가지 특징을 표준화해 더한다."""
    frames = librosa.time_to_frames(pulses, sr=rate, hop_length=HOP)
    mel = librosa.feature.melspectrogram(y=samples, sr=rate, hop_length=HOP, n_mels=64, fmax=8000)
    mel_freqs = librosa.mel_frequencies(n_mels=64, fmax=8000)
    low = librosa.power_to_db(mel[mel_freqs <= BASS_MAX_HZ])
    bass_onset = np.maximum(0, np.diff(low, axis=1, prepend=low[:, :1])).mean(axis=0)
    onset = librosa.onset.onset_strength(y=samples, sr=rate, hop_length=HOP)
    chroma = librosa.feature.chroma_cqt(y=samples, sr=rate, hop_length=HOP)
    period = max(1, int(np.median(np.diff(frames)))) if len(frames) > 1 else 1

    features = []
    for signal in (bass_onset, onset):
        features.append(np.array([_peak_near(signal, f) for f in frames]))
    features.append(np.array([_chroma_change(chroma, f, period) for f in frames]))
    return sum(_standardize(f) for f in features)


def _peak_near(signal: np.ndarray, frame: int, width: int = 2) -> float:
    start, end = max(0, frame - width), min(len(signal), frame + width + 1)
    return float(signal[start:end].max()) if end > start else 0.0


def _chroma_change(chroma: np.ndarray, frame: int, span: int) -> float:
    """맥박 바로 앞과 뒤 구간의 화음(음이름 분포)이 얼마나 다른지."""
    before = chroma[:, max(0, frame - span) : frame]
    after = chroma[:, frame : frame + span]
    if before.shape[1] == 0 or after.shape[1] == 0:
        return 0.0
    a, b = before.mean(axis=1), after.mean(axis=1)
    return float(1 - np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b) + 1e-9))


def _standardize(values: np.ndarray) -> np.ndarray:
    spread = values.std()
    return (values - values.mean()) / spread if spread > 0 else np.zeros_like(values)


def choose_meter(accents: np.ndarray, pulse_seconds: float) -> tuple[int, int, int]:
    """(한 박 맥박 수, 한 마디 박 수, 마디가 시작하는 맥박 번호)를 고른다."""
    best, best_score = (1, 4, 0), -math.inf
    for (group, per_bar), meter in METERS.items():
        beat_bpm = 60.0 / (pulse_seconds * group)
        if not MIN_BEAT_BPM <= beat_bpm <= MAX_BEAT_BPM or len(accents) < 2 * group * per_bar:
            continue
        if group == 2 and 60.0 / pulse_seconds <= MAX_BEAT_BPM:
            continue  # 맥박 그대로 셀 수 있으면 둘씩 묶지 않는다
        tempo_cost = TEMPO_PENALTY * math.log2(beat_bpm / COMFORT_BPM) ** 2
        for phase in range(group * per_bar):
            score = _template_fit(accents, group, per_bar, phase) - tempo_cost + METER_PRIOR[meter]
            if score > best_score:
                best, best_score = (group, per_bar, phase), score
    return best


def _template_fit(accents: np.ndarray, group: int, per_bar: int, phase: int) -> float:
    """셈 패턴과 박자 본보기(마디 첫 박 2, 다른 박 시작 1, 나머지 0)의 상관계수(-1~1)."""
    index = np.arange(len(accents)) - phase
    template = np.where(index % (group * per_bar) == 0, 2.0, np.where(index % group == 0, 1.0, 0.0))
    if template.std() == 0 or accents.std() == 0:
        return 0.0
    return float(np.corrcoef(accents, template)[0, 1])


def bar_positions(beat_accents: np.ndarray, per_bar: int, first: int = 0) -> list[int]:
    """박마다 마디 안 위치(0=첫 박)를 정한다. 보통은 하나씩 넘어가고, 건너뛰면 감점(비터비).

    first: 전체에서 고른 마디 시작(0번 박이 마디 안 몇 번째 박 앞인지). 시작할 때 이 위치를 조금 선호한다.
    """
    count = len(beat_accents)
    if count == 0:
        return []
    strength = _standardize(beat_accents)
    emit = np.where(np.arange(per_bar) == 0, 1.0, -1.0 / max(1, per_bar - 1))  # 첫 박이면 셈이 클수록 좋음
    start_position = (-first) % per_bar
    score = np.array([strength[0] * emit[p] - (0 if p == start_position else 0.5) for p in range(per_bar)])
    back = np.zeros((count, per_bar), dtype=int)
    for i in range(1, count):
        new = np.empty(per_bar)
        for p in range(per_bar):
            options = [score[q] - (0 if (q + 1) % per_bar == p else BAR_JUMP_COST) for q in range(per_bar)]
            back[i, p] = int(np.argmax(options))
            new[p] = options[back[i, p]] + strength[i] * emit[p]
        score = new
    path = [int(np.argmax(score))]
    for i in range(count - 1, 0, -1):
        path.append(back[i, path[-1]])
    return path[::-1]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="음원의 박·박자를 분석한다 (분석기 B단계)")
    parser.add_argument("audio", help="음원 파일")
    args = parser.parse_args(argv)
    try:
        result = analyze_beats(args.audio)
    except (AudioLoadError, ValueError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    print(f"박자표 {result.time_signature}, 빠르기 ♩≈{result.tempo_bpm:.0f}, 박 {len(result.beats)}개, "
          f"마디 {len(result.downbeats)}개, 못갖춘마디 {result.pickup_beats}박")
    return 0


if __name__ == "__main__":
    sys.exit(main())
