"""분석기 A단계: 소리 분리. 섞인 음원을 악기별 소리(트랙)로 나눈다. Demucs(소리 분리 AI)를 사용한다.

나누는 트랙(모델마다 다름):
- htdemucs (기본, 4개): vocals(목소리) · drums(드럼) · bass(베이스) · other(나머지: 피아노·기타 등)
- htdemucs_6s (6개): 위에 guitar(기타) · piano(피아노)가 따로 나온다 (처음 쓸 때 모델을 내려받음)

결과는 output/<곡 이름>/분리/<모델>/ 아래에 트랙마다 wav로 저장하고, 같은 곡을 다시 분석하면
저장된 결과를 그대로 쓴다(분리는 몇 분씩 걸리므로).
트랙마다 '들림 정도'(곡 구간 중 그 트랙 소리가 충분히 큰 구간의 비율)도 함께 적는다.

실행: uv run separate 곡.wav [--model htdemucs_6s]
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

DEFAULT_MODEL = "htdemucs"
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
# 곡을 5초씩 잘라, 트랙 소리 크기가 섞인 소리의 10% 이상인 구간의 비율을 '들림 정도'로 본다
PRESENCE_WINDOW_SECONDS = 5.0
MIN_ENERGY_RATIO = 0.1
PRESENT_SHARE = 0.2  # 들림 정도가 이 이상이면 '이 악기가 있다'

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
    mix = _mono(source)
    presence = {name: round(stem_presence(_mono(path), mix), 3) for name, path in stems.items()}
    result = Separation(source=source, model=model, stems={k: Path(v) for k, v in stems.items()}, presence=presence)
    _save_summary(result, target)
    return result


def stem_presence(stem: np.ndarray, mix: np.ndarray, sample_rate: int = 22050) -> float:
    """곡 구간 중 트랙 소리가 섞인 소리의 MIN_ENERGY_RATIO 이상인 구간의 비율(0~1)."""
    window = int(PRESENCE_WINDOW_SECONDS * sample_rate)
    length = min(len(stem), len(mix))
    checked = loud = 0
    for start in range(0, length, window):
        mix_energy = _energy(mix[start : start + window])
        if mix_energy <= 0:
            continue
        checked += 1
        loud += _energy(stem[start : start + window]) >= MIN_ENERGY_RATIO * mix_energy
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
    saved = json.loads(summary_path.read_text(encoding="utf-8"))
    return Separation(source=source, model=model, stems=stems, presence=saved.get("presence", {}))


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
