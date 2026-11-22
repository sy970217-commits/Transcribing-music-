"""구조(분석기 G단계) 문제지·정답지와 채점.

구조 단계는 D단계 음을 보고, 곡에서 되풀이되는 부분(A, B …)이 어디인지 찾는다.

문제지(모두 새로 만든 곡. 구절 = 4마디, 마디마다 베이스·화음·8분음표 선율)
  - 01_AABA: 8마디 부분 A A B A
  - 02_ABAB: 절(A)과 후렴(B)이 번갈아
  - 03_전주_후주: 전주 C, 본문 A A, 후주 D처럼 한 번만 나오는 부분이 앞뒤에
  - 04_같은코드_다른선율: 코드는 같고 선율만 다른 두 부분 A B A B
  - 05_못갖춘마디: 한 박 못갖춘마디로 시작하는 A A B A(4마디 부분)
정답지: answer.json — 부분마다 [시작, 끝, 이름] (4분음표 단위)

점수(1이 만점)
  - 경계_F: 부분이 바뀌는 곳을 맞힌 정도(1박 안이면 맞음)
  - 이름_짝_F: 두 시점(박마다)이 같은 부분인지 아닌지를 맞힌 정도. 이름 글자가 달라도 묶음이 같으면 맞음
채점은 정답_입력(박·음을 MIDI에서)과 실제_입력(음원을 B~D단계로 분석) 두 가지로 한다.

실행:
  uv run python tests/benchmark/structure_set.py build
  uv run python tests/benchmark/structure_set.py grade
"""

import json
import random
import shutil
import sys
from fractions import Fraction
from itertools import combinations
from pathlib import Path

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parents[1] / "src"))

import beat_set  # noqa: E402
import chord_set  # noqa: E402
import rhythm_set  # noqa: E402
from beat_set import Song, q  # noqa: E402

SET_DIR = BENCH / "structure"
OUTPUT = chord_set.OUTPUT
SCALE = (0, 2, 4, 5, 7, 9, 11)
# 코드: (근음, 3화음 음이름들)
CHORDS = {"C": (48, (0, 4, 7)), "Dm": (50, (2, 5, 9)), "Em": (52, (4, 7, 11)), "F": (41, (5, 9, 0)),
          "G": (43, (7, 11, 2)), "Am": (45, (9, 0, 4))}


def phrase(chords: str, seed: int) -> list:
    """4마디 구절: 마디마다 (코드 이름, 8분음표 선율 8음). 선율은 seed로 정해지는 음계 걸음."""
    rng = random.Random(seed)
    bars, pitch = [], 72
    for name in chords.split():
        tones = CHORDS[name][1]
        melody = []
        for eighth in range(8):
            if eighth % 2 == 0:  # 박에서는 코드 음
                pitch = min((p for p in range(pitch - 6, pitch + 7) if p % 12 in tones and 64 <= p <= 84),
                            key=lambda p: (abs(p - pitch - rng.choice((-4, -2, 2, 4))), p))
            else:  # 뒷박은 음계 이웃 음
                pitch = next(p for p in (pitch + rng.choice((1, 2)), pitch - 1, pitch - 2) if p % 12 in SCALE)
            melody.append(pitch)
        bars.append((name, tuple(melody)))
    return bars


def build_song(phrases: list, pickup: Fraction = q(0)) -> Song:
    notes = [(72, q(0), pickup, 80, 0)] if pickup else []
    for bar, (name, melody) in enumerate(b for p in phrases for b in p):
        root, tones = CHORDS[name]
        start = pickup + bar * 4
        notes.append((root - 12, start, q(4), 90, 0))
        for beat in range(4):
            notes += [(55 + (t - 55) % 12, start + beat, q(1), 70, 0) for t in tones]
        notes += [(p, start + q(i, 2), q(1, 2), 90, 0) for i, p in enumerate(melody)]
    return Song(4, 4, ((q(0), 100.0),), pickup, sum(len(p) for p in phrases), tuple(notes))


V1, V2 = phrase("C Am F G", 1), phrase("C F G C", 2)  # 절(8마디)
C1, C2 = phrase("F G Em Am", 3), phrase("Dm G C C", 4)  # 후렴(8마디)
INTRO, OUTRO = phrase("Am F C G", 5), phrase("F G C C", 6)
SAME1, SAME2 = phrase("C Am F G", 7), phrase("C F G C", 8)  # V1·V2와 코드만 같다


def sections(*parts) -> list:
    """(이름, 구절 수)들 → [시작, 끝, 이름] (4분음표 단위)."""
    rows, at = [], 0
    for label, count in parts:
        rows.append((at, at + count * 16, label))
        at += count * 16
    return rows


SONGS = {
    "01_AABA": (build_song([V1, V2, V1, V2, C1, C2, V1, V2]), sections(("A", 2), ("A", 2), ("B", 2), ("A", 2))),
    "02_ABAB": (build_song([V1, V2, C1, C2, V1, V2, C1, C2]), sections(("A", 2), ("B", 2), ("A", 2), ("B", 2))),
    "03_전주_후주": (build_song([INTRO, V1, V2, V1, V2, OUTRO]),
                   sections(("C", 1), ("A", 2), ("A", 2), ("D", 1))),
    "04_같은코드_다른선율": (build_song([V1, V2, SAME1, SAME2, V1, V2, SAME1, SAME2]),
                      sections(("A", 2), ("B", 2), ("A", 2), ("B", 2))),
    "05_못갖춘마디": (build_song([V1, V1, C1, V1], q(1)),
                  [(0, 17, "A"), (17, 33, "A"), (33, 49, "B"), (49, 65, "A")]),
}


def audio_of(name: str) -> Path:
    return OUTPUT / "structure" / name / "problem.wav"


def build() -> None:
    for name, (song, answer) in SONGS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        beat_set.write_midi(song, folder / "problem.mid")
        audio_of(name).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio_of(name))
        rows = [[str(Fraction(s)), str(Fraction(e)), label] for s, e, label in answer]
        (folder / "answer.json").write_text(json.dumps({"sections": rows}, ensure_ascii=False), encoding="utf-8")
        print(name, " ".join(label for _, _, label in answer))


def f_measure(hits: int, found: int, wanted: int) -> float:
    return round(2 * hits / (found + wanted), 3) if found + wanted else 1.0


def boundary_f(reference: list, estimate: list) -> float:
    """곡 처음·끝을 뺀 경계를 1박(4분음표 1개) 안에서 짝지어 F값."""
    wanted = [Fraction(s) for s, _, _ in reference[1:]]
    found = [Fraction(s) for s, _, _ in estimate[1:]]
    left, hits = list(found), 0
    for b in wanted:
        match = next((f for f in left if abs(f - b) <= 1), None)
        if match is not None:
            left.remove(match)
            hits += 1
    return f_measure(hits, len(found), len(wanted))


def label_at(rows: list, time: Fraction) -> str | None:
    return next((label for s, e, label in rows if Fraction(s) <= time < Fraction(e)), None)


def pair_f(reference: list, estimate: list) -> float:
    """박마다 이름을 보고, 두 박이 같은 이름인 짝을 얼마나 맞혔는지 F값."""
    end = Fraction(reference[-1][1])
    times = [Fraction(t) + Fraction(1, 2) for t in range(int(end))]
    ref = [label_at(reference, t) for t in times]
    est = [label_at(estimate, t) for t in times]
    pairs = list(combinations(range(len(times)), 2))
    wanted = {p for p in pairs if ref[p[0]] == ref[p[1]]}
    found = {p for p in pairs if est[p[0]] is not None and est[p[0]] == est[p[1]]}
    return f_measure(len(wanted & found), len(found), len(wanted))


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes
    from transcriber.analysis.structure import analyze_structure

    def rows(rhythm, beats):
        return [[s.start, s.end, s.label] for s in analyze_structure(rhythm, beats).sections]

    report = {}
    for name, (song, _) in SONGS.items():
        reference = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))["sections"]
        beats, notes = rhythm_set.true_inputs(song, SET_DIR / name / "problem.mid")
        real_beats = analyze_beats(audio_of(name))
        report[name] = {}
        for kind, estimate in (("정답_입력", rows(quantize_notes(notes, beats), beats)),
                               ("실제_입력", rows(quantize_notes(recognize_notes(audio_of(name))["mix"], real_beats),
                                                real_beats))):
            report[name][kind] = {"경계_F": boundary_f(reference, estimate), "이름_짝_F": pair_f(reference, estimate),
                                  "찾은_부분": " ".join(str(r[2]) for r in estimate)}
    (OUTPUT / "structure_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
