"""화음(분석기 E단계) 문제지·정답지와 채점.

화음 단계는 D단계에서 박에 맞춘 음(4분음표 단위 위치·길이)을 보고, 구간마다 코드(CM, Am7, CM/E …)를 정한다.

문제지
  - B단계 6곡(4/4, 왈츠, 6/8, 빠르기 변화, 못갖춘마디, 드럼 밴드)의 음원을 다시 쓴다
  - 07_화음_여러가지: 단3화음·7화음·감·증3화음·자리바꿈·한 마디에 코드 두 개·꾸밈음(코드 밖 음)을 담은 새 곡
정답지: answer.json — 코드마다 [시작, 끝, 이름] (4분음표 단위, 코드 없는 곳은 "N")

점수(4분음표의 1/4 칸마다 비교해 맞은 시간의 비율, 1이 만점)
  - 근음_정확도: 코드의 바탕음(C, A …)만 맞으면
  - 코드_정확도: 바탕음과 종류(M, m, 7 …)까지 맞으면
  - 자리바꿈까지_정확도: 맨 아래 음(/E 같은)까지 모두 맞으면
채점은 두 가지로 한다
  - 정답_입력: 박·음을 정답(MIDI)에서 가져와 화음 단계만 시험
  - 실제_입력: 음원을 B·C·D단계로 분석한 결과로 시험(전체 흐름)

실행:
  uv run python tests/benchmark/chord_set.py build   # 정답지·새 곡 만들기 (B단계 build를 먼저)
  uv run python tests/benchmark/chord_set.py grade
"""

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parents[1] / "src"))

import beat_set  # noqa: E402
import rhythm_set  # noqa: E402
from beat_set import AM, DM, G7, C, F, G, Song, q  # noqa: E402

from transcriber.chord_names import NOTE_NAMES, chord_name  # noqa: E402

ROOT = BENCH.parents[1]
SET_DIR = BENCH / "chords"
OUTPUT = ROOT / "output" / "benchmark"
NO_CHORD = "N"
GRID = Fraction(1, 4)  # 채점 칸: 16분음표

# 새 곡의 코드 진행: 마디마다 (길이, 베이스 음, 위 음들)
CM = (48, (60, 64, 67))
A_MINOR = (45, (60, 64, 69))
PROGRESSION = (
    ((4, *CM),),
    ((4, *A_MINOR),),
    ((2, 50, (60, 65, 69)), (2, 43, (59, 62, 65))),  # Dm7, G7
    ((4, 48, (64, 67, 71)),),  # CM7
    ((4, 41, (64, 69, 72)),),  # FM7
    ((2, 40, (59, 64, 67)), (2, 45, (61, 64, 67))),  # Em, A7
    ((2, 50, (62, 65, 69)), (2, 41, (62, 65, 69))),  # Dm, Dm/F
    ((4, 43, (59, 62, 65)),),  # G7
    ((2, 40, (60, 64, 67)), (2, 41, (60, 65, 69))),  # CM/E, FM
    ((2, 47, (62, 65, 71)), (2, 40, (62, 68, 71))),  # Bdim, E7
    ((4, *A_MINOR),),
    ((4, 48, (60, 64, 68)),),  # Caug
    ((4, 41, (60, 65, 68)),),  # Fm
    ((2, 48, (60, 63, 67)), (2, 47, (62, 65, 69))),  # Cm, Bm7b5
    ((2, 47, (55, 62, 67)), (2, 43, (59, 62, 65))),  # GM/B, G7
    ((4, *CM),),
)


def many_chords() -> Song:
    """홀수 마디는 박마다 화음을 누르고, 짝수 마디는 8분음표로 펼친다. 위 선율은 박마다 코드 음, 뒷박은 꾸밈음."""
    notes = []
    for bar, chords in enumerate(PROGRESSION):
        start = q(bar * 4)
        for length, bass, tones in chords:
            notes.append((bass, start, q(length), 90, 0))
            for beat in range(length):
                at = start + beat
                if bar % 2 == 0:
                    notes += [(p, at, q(1), 70 if beat else 80, 0) for p in tones]
                else:
                    notes += [(tones[i], at + q(i, 2), q(1, 2), 65, 0) for i in (0, 1)]
                top = max(tones) + 12
                notes += [(top, at, q(1, 2), 90, 0), (top + 2, at + q(1, 2), q(1, 2), 70, 0)]
            start += length
    return Song(4, 4, ((q(0), 96.0),), q(0), len(PROGRESSION), tuple(notes))


def plan_of(chords: list, bar_quarters, pickup=Fraction(0)) -> list:
    """마디마다 코드 하나인 진행 → [시작, 끝, (베이스, 위 음들)]. 못갖춘마디는 코드 없음."""
    plan = [[Fraction(0), pickup, None]] if pickup else []
    for bar, chord in enumerate(chords):
        start = pickup + bar * bar_quarters
        plan.append([start, start + bar_quarters, chord])
    return plan


def plan_of_new_song() -> list:
    plan, start = [], Fraction(0)
    for chords in PROGRESSION:
        for length, bass, tones in chords:
            plan.append([start, start + length, (bass, tones)])
            start += length
    return plan


# 문제 이름 → (곡 정의, 코드 진행, 음원 위치)
NEW_SONGS = {"07_화음_여러가지": many_chords()}
_PLANS = {
    "01_4박자_피아노": plan_of([C, AM, F, G] * 3, 4),
    "02_3박자_왈츠": plan_of([C, G7, G7, C, F, C, G7, C] * 2, 3),
    "03_8분의6박자": plan_of([C, G, AM, F] * 3, 3),
    "04_빠르기_변화": plan_of([C, AM, F, G] * 3, 4),
    "05_못갖춘마디": plan_of([C, F, G, C] * 2, 4, Fraction(1)),
    "06_드럼_밴드": plan_of([C, AM, DM, G] * 3, 4),
}
PROBLEMS = {
    **{name: (beat_set.SONGS[name], plan, beat_set.AUDIO_DIR / name / "problem.wav") for name, plan in _PLANS.items()},
    **{name: (song, plan_of_new_song(), OUTPUT / "chords" / name / "problem.wav") for name, song in NEW_SONGS.items()},
}


def answer_of(song: Song, plan: list) -> dict:
    chords = []
    for start, end, chord in plan:
        name = NO_CHORD if chord is None else chord_name((chord[0], *chord[1]))
        chords.append([str(start), str(end), name])
    return {"time_signature": f"{song.numerator}/{song.denominator}", "pickup_quarters": str(song.pickup),
            "chords": chords}


def midi_of(name: str) -> Path:
    return SET_DIR / name / "problem.mid" if name in NEW_SONGS else beat_set.SET_DIR / name / "problem.mid"


def build() -> None:
    for name, (song, plan, audio) in PROBLEMS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        if name in NEW_SONGS:
            beat_set.write_midi(song, folder / "problem.mid")
            audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio)
        answer = answer_of(song, plan)
        (folder / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        print(name, "코드", len(answer["chords"]))


def split_name(name: str) -> tuple[str, str, str]:
    """코드 이름 → (근음, 종류, 맨 아래 음). 예: 'C#m7/E' → ('C#', 'm7', 'E'), 'N' → ('N', '', 'N')"""
    if name == NO_CHORD:
        return NO_CHORD, "", NO_CHORD
    base, _, bass = name.partition("/")
    root = base[:2] if base[1:2] == "#" else base[:1]
    if root not in NOTE_NAMES:
        raise ValueError(f"코드 이름을 읽을 수 없어요: {name}")
    return root, base[len(root):], bass or root


def chord_at(segments: list, time: Fraction) -> str:
    for start, end, name in segments:
        if Fraction(start) <= time < Fraction(end):
            return name
    return NO_CHORD


def score(reference: list, estimate: list) -> dict:
    """[시작, 끝, 이름] 목록 두 개를 정답 구간 안에서 1/4박 칸마다 비교한 점수."""
    if not reference:
        return {"근음_정확도": 1.0, "코드_정확도": 1.0, "자리바꿈까지_정확도": 1.0}
    first, last = Fraction(reference[0][0]), Fraction(reference[-1][1])
    steps = int((last - first) / GRID)
    hits = [0, 0, 0]
    for i in range(steps):
        time = first + i * GRID
        ref, est = split_name(chord_at(reference, time)), split_name(chord_at(estimate, time))
        hits[0] += ref[0] == est[0]
        hits[1] += ref[:2] == est[:2]
        hits[2] += ref == est
    return {key: round(hit / steps, 3) for key, hit in zip(("근음_정확도", "코드_정확도", "자리바꿈까지_정확도"), hits)}


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes

    def rows(result):
        return [[c.start, c.end, c.name] for c in result.chords]

    report = {}
    for name, (song, _, audio) in PROBLEMS.items():
        reference = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))["chords"]
        beats, notes = rhythm_set.true_inputs(song, midi_of(name))
        real_beats = analyze_beats(audio)
        real = quantize_notes(recognize_notes(audio)["mix"], real_beats)
        report[name] = {
            "정답_입력": score(reference, rows(analyze_harmony(quantize_notes(notes, beats), beats))),
            "실제_입력": score(reference, rows(analyze_harmony(real, real_beats))),
        }
    (OUTPUT / "chord_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
