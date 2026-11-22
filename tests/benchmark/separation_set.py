"""소리 분리(분석기 A단계) 문제지·정답지 만들기와 채점.

문제지: 여러 악기가 섞인 음원(problem.wav)
정답지: 악기마다 따로 녹음한 음원(answer_<트랙>.wav)과 정답표(answer.json: 어떤 트랙이 있어야 하는지)

곡은 코드로 직접 만든다(저작권 없음). 저장소에는 곡을 만드는 MIDI와 정답표만 올리고,
음원(wav)은 용량이 커서 output/benchmark/separation/ 에 만든다.

실행:
  uv run python tests/benchmark/separation_set.py build   # 문제지·정답지 만들기
  uv run python tests/benchmark/separation_set.py grade   # 분리해서 채점 (몇 분 걸림)
"""

import json
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path

import mido
import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from transcriber.audio_io import load_audio  # noqa: E402
from transcriber.render import midi_to_audio  # noqa: E402

SET_DIR = Path(__file__).resolve().parent / "separation"  # 저장소에 올리는 MIDI·정답표
AUDIO_DIR = ROOT / "output" / "benchmark" / "separation"  # 음원(올리지 않음)
TICKS = 480  # 한 박의 틱 수
TEMPO_BPM = 100
BARS = 8
PROGRESSION = [(48, (60, 64, 67)), (45, (57, 60, 64)), (41, (57, 60, 65)), (43, (55, 59, 62))]  # C Am F G
MELODY = [72, 74, 76, 77, 76, 74, 72, 71, 69, 71, 72, 74, 72, 71, 69, 67]  # 2박씩


@dataclass(frozen=True)
class Track:
    stem: str  # 정답 트랙 이름(vocals·drums·bass·piano)
    program: int  # 악기 번호(General MIDI)
    channel: int
    notes: tuple[tuple[int, float, float, int], ...]  # (음, 시작 박, 길이 박, 세기)


def piano_part() -> Track:
    notes = []
    for bar in range(BARS):
        bass, chord = PROGRESSION[bar % 4]
        for beat in range(4):  # 박마다 화음
            notes += [(p, bar * 4 + beat, 0.9, 70) for p in chord]
        notes.append((bass, bar * 4, 3.9, 75))
    return Track("piano", 0, 0, tuple(notes))


def voice_part() -> Track:
    return Track("vocals", 53, 1, tuple((p, i * 2, 1.9, 95) for i, p in enumerate(MELODY)))  # 53 = 사람 목소리 '우~'


def bass_part() -> Track:
    notes = []
    for bar in range(BARS):
        root = PROGRESSION[bar % 4][0] - 12
        notes += [(root, bar * 4 + b, 0.9, 100) for b in range(4)]
    return Track("bass", 33, 2, tuple(notes))


def drum_part() -> Track:
    notes = []
    for beat in range(BARS * 4):
        notes.append((36 if beat % 2 == 0 else 38, beat, 0.5, 100))  # 큰북·작은북
        notes += [(42, beat + h, 0.25, 70) for h in (0, 0.5)]  # 하이햇 8분
    return Track("drums", 0, 9, tuple(notes))


PROBLEMS = {
    "01_노래와_피아노": (voice_part(), piano_part()),
    "02_피아노만": (piano_part(),),
    "03_밴드": (voice_part(), piano_part(), bass_part(), drum_part()),
}
ALL_STEMS = ("vocals", "drums", "bass", "piano")


def model_stem(answer_stem: str, model: str) -> str:
    """정답 트랙이 그 모델에서는 어느 트랙으로 나오는지. 피아노 트랙이 없는 모델은 '나머지(other)'로 나온다."""
    from transcriber.analysis.separation import MODEL_STEMS

    stems = MODEL_STEMS[model]
    return answer_stem if answer_stem in stems else "other"


def write_midi(tracks: tuple[Track, ...], path: Path) -> None:
    song = mido.MidiFile(ticks_per_beat=TICKS)
    meta = mido.MidiTrack([mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(TEMPO_BPM), time=0)])
    song.tracks.append(meta)
    for track in tracks:
        events = []
        for pitch, start, length, velocity in track.notes:
            events.append((round(start * TICKS), 1, mido.Message("note_on", note=pitch, velocity=velocity, channel=track.channel)))
            events.append((round((start + length) * TICKS), 0, mido.Message("note_off", note=pitch, velocity=0, channel=track.channel)))
        messages = [mido.Message("program_change", program=track.program, channel=track.channel, time=0)]
        now = 0
        for tick, _, message in sorted(events, key=lambda e: (e[0], e[1])):
            messages.append(message.copy(time=tick - now))
            now = tick
        song.tracks.append(mido.MidiTrack(messages))
    path.parent.mkdir(parents=True, exist_ok=True)
    song.save(path)


def build() -> None:
    """문제마다 트랙별 MIDI → 트랙별 음원(정답) → 합친 음원(문제)을 만든다."""
    for name, tracks in PROBLEMS.items():
        audio_dir = AUDIO_DIR / name
        audio_dir.mkdir(parents=True, exist_ok=True)
        write_midi(tracks, SET_DIR / name / "problem.mid")
        answers = {}
        for track in tracks:
            midi_path = SET_DIR / name / f"answer_{track.stem}.mid"
            write_midi((track,), midi_path)
            rendered = midi_to_audio(midi_path)  # MIDI 옆에 wav가 생김 → 음원 폴더로 옮김
            answers[track.stem] = shutil.move(str(rendered), audio_dir / f"answer_{track.stem}.wav")
        stems = {stem: sf.read(path, always_2d=True) for stem, path in answers.items()}
        rate = next(iter(stems.values()))[1]
        length = max(len(data) for data, _ in stems.values())
        mix = np.zeros((length, 2), dtype=np.float64)
        for data, _ in stems.values():
            mix[: len(data), : data.shape[1]] += data
        sf.write(audio_dir / "problem.wav", np.clip(mix, -1, 1), rate)  # 문제 = 정답 트랙의 합
        answer = {
            "문제": f"{name}/problem.wav",
            "있어야_하는_트랙": sorted(answers),
            "없어야_하는_트랙": sorted(set(ALL_STEMS) - set(answers)),
            "트랙_설명": {t.stem: f"악기 번호 {t.program} (채널 {t.channel + 1})" for t in tracks},
        }
        (SET_DIR / name / "answer.json").write_text(json.dumps(answer, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"{name}: 문제 1개, 정답 트랙 {sorted(answers)}")


def si_sdr(estimate: np.ndarray, reference: np.ndarray) -> float:
    """정답과 얼마나 비슷한지(dB, 클수록 좋음). 소리 크기 차이는 무시한다."""
    length = min(len(estimate), len(reference))
    est, ref = estimate[:length], reference[:length]
    scale = np.dot(est, ref) / (np.dot(ref, ref) + 1e-12)
    target = scale * ref
    return float(10 * np.log10((np.dot(target, target) + 1e-12) / (np.dot(est - target, est - target) + 1e-12)))


def leakage_db(estimate: np.ndarray, mix: np.ndarray) -> float:
    """없어야 하는 트랙에 새어 나온 소리 크기(섞인 소리 대비 dB, 작을수록 좋음)."""
    return float(10 * np.log10((np.mean(estimate**2) + 1e-12) / (np.mean(mix**2) + 1e-12)))


def grade(model: str = "htdemucs_6s") -> dict:
    from transcriber.analysis.separation import separate

    report = {}
    for name in PROBLEMS:
        answer = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))
        problem = AUDIO_DIR / name / "problem.wav"
        result = separate(problem, AUDIO_DIR / name / "결과", model)
        mix = load_audio(problem).samples
        scores = {}
        used = set()
        for stem in answer["있어야_하는_트랙"]:
            out = model_stem(stem, model)
            used.add(out)
            reference = load_audio(AUDIO_DIR / name / f"answer_{stem}.wav").samples
            scores[stem] = {"닮음_dB": round(si_sdr(load_audio(result.stems[out]).samples, reference), 1),
                            "있다고_판단": result.present(out)}
        for out in result.stems:  # 정답에 없는 트랙(그 모델의 나머지 트랙 포함)은 비어 있어야 한다
            if out not in used:
                scores[out] = {"새어나옴_dB": round(leakage_db(load_audio(result.stems[out]).samples, mix), 1),
                               "있다고_판단": result.present(out)}
        report[name] = scores
    out = AUDIO_DIR / f"채점_{model}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    if command == "build":
        build()
    elif command == "grade":
        grade(sys.argv[2] if len(sys.argv) > 2 else "htdemucs_6s")
    else:
        print("사용법: separation_set.py build | grade [모델]")
