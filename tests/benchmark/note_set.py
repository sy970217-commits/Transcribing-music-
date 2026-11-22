"""음 인식(분석기 C단계) 문제지·정답지와 채점.

문제지: A·B단계에서 만든 음원을 다시 쓴다
  - 피아노 독주 3곡(B단계 01~03): 화음·리듬을 잘 찾는지
  - 여러 악기 2곡(A단계 01·03): 소리 분리 뒤 트랙마다 음을 잘 찾는지
정답지: answer.json — 트랙마다 음 목록 [음높이(MIDI 번호), 시작(초), 끝(초)]. 곡을 만든 MIDI에서 뽑는다.

점수(mir_eval 음 단위 채점)
  - 시작_F1: 음높이가 같고 시작이 ±0.05초 안이면 맞음. 맞힌 비율(1이 만점)
  - 길이까지_F1: 끝 시각도 음 길이의 20%(최소 0.05초) 안이어야 맞음

실행:
  uv run python tests/benchmark/note_set.py build   # 정답지 만들기 (A·B단계 build를 먼저)
  uv run python tests/benchmark/note_set.py grade
"""

import json
import sys
from pathlib import Path

import numpy as np
import pretty_midi

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

BENCH = Path(__file__).resolve().parent
SET_DIR = BENCH / "notes"
OUTPUT = ROOT / "output" / "benchmark"

# 문제 이름 → (음원, {트랙: 정답 MIDI들}, 소리 분리를 쓰는지)
PROBLEMS = {
    "01_피아노_4박자": ("beats/01_4박자_피아노/problem.wav", {"piano": ["beats/01_4박자_피아노/problem.mid"]}, False),
    "02_피아노_왈츠": ("beats/02_3박자_왈츠/problem.wav", {"piano": ["beats/02_3박자_왈츠/problem.mid"]}, False),
    "03_피아노_8분의6": ("beats/03_8분의6박자/problem.wav", {"piano": ["beats/03_8분의6박자/problem.mid"]}, False),
    "04_노래와_피아노": (
        "separation/01_노래와_피아노/problem.wav",
        {"vocals": ["separation/01_노래와_피아노/answer_vocals.mid"],
         "piano": ["separation/01_노래와_피아노/answer_piano.mid"]},
        True,
    ),
    "05_밴드": (
        "separation/03_밴드/problem.wav",
        {"vocals": ["separation/03_밴드/answer_vocals.mid"],
         "piano": ["separation/03_밴드/answer_piano.mid"],
         "bass": ["separation/03_밴드/answer_bass.mid"]},
        True,
    ),
}


def notes_of(midi_path: Path) -> list[list[float]]:
    """MIDI의 음(드럼 제외) → [음높이, 시작, 끝]"""
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = [[n.pitch, round(n.start, 4), round(n.end, 4)] for inst in midi.instruments if not inst.is_drum for n in inst.notes]
    return sorted(notes, key=lambda n: (n[1], n[0]))


def build() -> None:
    for name, (audio, tracks, separated) in PROBLEMS.items():
        answer = {
            "음원": f"output/benchmark/{audio}",
            "소리_분리": separated,
            "트랙": {track: sorted((n for m in mids for n in notes_of(BENCH / m)), key=lambda n: (n[1], n[0]))
                     for track, mids in tracks.items()},
        }
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        print(name, {t: len(n) for t, n in answer["트랙"].items()})


def score(reference: list, estimate: list) -> dict:
    """음 목록 두 개를 비교한 점수."""
    import mir_eval

    def arrays(notes):
        if not notes:
            return np.zeros((0, 2)), np.zeros(0)
        data = np.array(notes, dtype=float)
        return data[:, 1:3], np.array([pretty_midi.note_number_to_hz(p) for p in data[:, 0]])

    ref_iv, ref_hz = arrays(reference)
    est_iv, est_hz = arrays(estimate)
    if len(est_hz) == 0:
        return {"시작_F1": 0.0, "길이까지_F1": 0.0, "정답_음수": len(reference), "찾은_음수": 0}
    onset = mir_eval.transcription.precision_recall_f1_overlap(ref_iv, ref_hz, est_iv, est_hz, offset_ratio=None)
    full = mir_eval.transcription.precision_recall_f1_overlap(ref_iv, ref_hz, est_iv, est_hz)
    return {"시작_F1": round(onset[2], 3), "정밀도": round(onset[0], 3), "재현율": round(onset[1], 3),
            "길이까지_F1": round(full[2], 3), "정답_음수": len(reference), "찾은_음수": len(estimate)}


def grade() -> dict:
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.separation import separate

    report = {}
    for name in PROBLEMS:
        answer = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))
        audio = ROOT / answer["음원"]
        separation = separate(audio, audio.parent / "결과") if answer["소리_분리"] else None
        found = recognize_notes(audio, separation)
        report[name] = {}
        for track, reference in answer["트랙"].items():
            estimate = found.get(track, found.get("mix", ()))
            report[name][track] = score(reference, [[n.pitch, n.start_seconds, n.end_seconds] for n in estimate])
    (OUTPUT / "notes_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
