"""분석기 A단계: 소리 분리. 섞인 음원을 악기별 소리(트랙)로 나눈다. Demucs(소리 분리 AI)를 사용한다.

나누는 트랙(모델마다 다름):
- htdemucs_6s (기본, 6개): vocals(목소리) · drums(드럼) · bass(베이스) · guitar(기타) · piano(피아노) · other(나머지)
- htdemucs (4개): vocals · drums · bass · other(나머지: 피아노·기타 등)
문제지 채점(tests/benchmark)에서 노래+피아노 곡의 목소리 닮음이 2.4 → 8.4dB, 피아노가 -0.5 → 7.3dB로
htdemucs_6s가 훨씬 잘 나눠서 기본으로 쓴다.

결과는 output/<곡 이름>/분리/<모델>/ 아래에 트랙마다 wav로 저장하고, 같은 곡을 다시 분석하면
저장된 결과를 그대로 쓴다(분리는 몇 분씩 걸리므로).
트랙마다 '들림 정도'(곡 구간 중 그 트랙 소리가 충분히 큰 구간의 비율)도 함께 적는다.

실행: uv run separate 곡.wav [--model htdemucs]
"""

import argparse
import json
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from transcriber.audio_io import AudioLoadError, load_audio, validate_audio_path

DEFAULT_MODEL = "htdemucs_6s"
MODEL_STEMS = {
    "htdemucs": ("vocals", "drums", "bass", "other"),
    "htdemucs_ft": ("vocals", "drums", "bass", "other"),
    "htdemucs_6s": ("vocals", "drums", "bass", "guitar", "piano", "other"),
}
STEM_NAMES_KO = {
    "vocals": "목소리",
    "drums": "드럼",
    "bass": "베이스",
    "guitar": "기타",
    "piano": "피아노",
    "other": "나머지 악기",
}
DEFAULT_OUTPUT_DIR = Path("output")
SUMMARY_FILE = "분리정보.json"
# 곡을 5초씩 잘라, 트랙 소리가 섞인 소리 대비 기준 이상인 구간의 비율을 '들림 정도'로 본다.
# 기준(문제지 채점으로 정함):
# - 이름 있는 트랙(목소리·피아노·베이스·드럼·기타 등): 0.1%(-30dB). 악기가 있으면 -15dB 이상,
#   없으면 -50dB 이하로 뚜렷이 갈린다. 드럼·베이스가 큰 곡의 작은 피아노도 '있음'으로 잡는다
# - 6트랙 모델의 other(나머지): 16%(-8dB). 피아노·목소리에서 새어 나온 소리가 모이는 곳이라
#   악기가 없어도 -12dB쯤 되므로 크게 들릴 때만 '있음'
PRESENCE_WINDOW_SECONDS = 5.0
MIN_ENERGY_RATIO = 0.001
RESIDUAL_MIN_ENERGY_RATIO = 0.16
PRESENT_SHARE = 0.2  # 들림 정도가 이 이상이면 '이 악기가 있다'
# 곡 평균 소리의 1%도 안 되는 거의 조용한 구간(곡 끝 잔향 등)은 세지 않는다.
# 그런 구간에서는 아주 작은 새어 나온 소리도 '섞인 소리의 10% 이상'이 되어 악기가 있다고 잘못 판단한다
SILENT_RATIO = 0.01

# (음원 경로, 결과 폴더, 모델 이름) → {트랙 이름: wav 경로}
Separator = Callable[[Path, Path, str], dict[str, Path]]


class SeparationError(Exception):
    """소리 분리에 실패했을 때 쓰는 오류."""


@dataclass(frozen=True)
class Separation:
    """소리 분리 결과."""

    source: Path
    model: str
    stems: dict[str, Path]  # 트랙 이름 → wav 경로
    presence: dict[str, float] = field(default_factory=dict)  # 트랙 이름 → 들림 정도(0~1)

    def present(self, name: str) -> bool:
        """그 트랙(악기)이 곡에 있다고 볼 수 있는지."""
        return self.presence.get(name, 0.0) >= PRESENT_SHARE


def separate(
    audio_path: str | Path,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    model: str = DEFAULT_MODEL,
    separator: Separator | None = None,
) -> Separation:
    """음원을 트랙별로 나눈다. 이미 나눠 둔 결과가 있으면 다시 하지 않는다."""
    source = validate_audio_path(audio_path)
    if model not in MODEL_STEMS:
        raise SeparationError(f"모르는 모델이에요: {model} (쓸 수 있는 모델: {', '.join(MODEL_STEMS)})")
    target = Path(output_dir) / source.stem / "분리" / model
    cached = _load_cached(source, target, model)
    if cached is not None:
        return cached

    stems = (separator or _demucs_separator)(source, target, model)
    missing = [name for name in MODEL_STEMS[model] if name not in stems or not Path(stems[name]).is_file()]
    if missing:
        raise SeparationError(f"분리된 트랙이 없어요: {', '.join(missing)}")
    result = _with_presence(source, model, {k: Path(v) for k, v in stems.items()})
    _save_summary(result, target)
    return result


def _with_presence(source: Path, model: str, stems: dict[str, Path]) -> Separation:
    """트랙마다 들림 정도를 계산한다(저장된 분리 결과에도 매번 새로 계산해 판단 기준이 바뀌어도 맞게)."""
    mix = _mono(source)
    presence = {
        name: round(stem_presence(_mono(path), mix, min_ratio=presence_ratio(name, model)), 3)
        for name, path in stems.items()
    }
    return Separation(source=source, model=model, stems=stems, presence=presence)


def presence_ratio(name: str, model: str) -> float:
    """트랙마다 '들린다'고 볼 기준. 피아노 트랙이 따로 있는 모델의 other는 새어 나온 소리 모음이라 엄격하게."""
    if name == "other" and "piano" in MODEL_STEMS.get(model, ()):
        return RESIDUAL_MIN_ENERGY_RATIO
    return MIN_ENERGY_RATIO


def stem_presence(
    stem: np.ndarray, mix: np.ndarray, sample_rate: int = 22050, min_ratio: float = MIN_ENERGY_RATIO
) -> float:
    """곡 구간 중 트랙 소리가 섞인 소리의 min_ratio 이상인 구간의 비율(0~1)."""
    window = int(PRESENCE_WINDOW_SECONDS * sample_rate)
    length = min(len(stem), len(mix))
    silent = SILENT_RATIO * _energy(mix[:length])
    checked = loud = 0
    for start in range(0, length, window):
        mix_energy = _energy(mix[start : start + window])
        if mix_energy <= silent or mix_energy <= 0:
            continue
        checked += 1
        loud += _energy(stem[start : start + window]) >= min_ratio * mix_energy
    return loud / checked if checked else 0.0


def _energy(samples: np.ndarray) -> float:
    return float(np.mean(np.square(samples))) if len(samples) else 0.0


def _mono(path: Path) -> np.ndarray:
    return load_audio(path).samples


def _load_cached(source: Path, target: Path, model: str) -> Separation | None:
    summary_path = target / SUMMARY_FILE
    if not summary_path.is_file() or summary_path.stat().st_mtime < source.stat().st_mtime:
        return None
    stems = {name: target / f"{name}.wav" for name in MODEL_STEMS[model]}
    if not all(path.is_file() for path in stems.values()):
        return None
    return _with_presence(source, model, stems)


def _save_summary(result: Separation, target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    summary = {
        "source": str(result.source),
        "model": result.model,
        "stems": {name: str(path) for name, path in result.stems.items()},
        "presence": result.presence,
    }
    (target / SUMMARY_FILE).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")


def _demucs_separator(source: Path, target: Path, model: str) -> dict[str, Path]:
    """Demucs로 나누고 결과 wav를 target 폴더로 옮긴다."""
    from demucs.separate import main as demucs_main  # 무거운 라이브러리라 필요할 때만 불러온다

    target.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        demucs_main(["-n", model, "-o", work, str(source)])
        produced = Path(work) / model / source.stem
        stems = {}
        for name in MODEL_STEMS[model]:
            moved = target / f"{name}.wav"
            shutil.move(str(produced / f"{name}.wav"), moved)
            stems[name] = moved
    return stems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="음원을 악기별 소리(트랙)로 나눈다 (분석기 A단계)")
    parser.add_argument("audio", help="음원 파일(wav, mp3 등)")
    parser.add_argument("--model", default=DEFAULT_MODEL, choices=sorted(MODEL_STEMS), help="분리 모델")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR), help="결과 폴더 (기본: output)")
    args = parser.parse_args(argv)
    print(f"소리 분리 중: {args.audio} (몇 분 걸릴 수 있어요)")
    try:
        result = separate(args.audio, args.output_dir, args.model)
    except (AudioLoadError, SeparationError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    for name, path in result.stems.items():
        mark = "있음" if result.present(name) else "거의 없음"
        print(f"  {STEM_NAMES_KO.get(name, name)}({name}): 들림 {result.presence.get(name, 0):.0%} [{mark}] → {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
