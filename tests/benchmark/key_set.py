"""조성(분석기 F단계) 문제지·정답지와 채점.

조성 단계는 D단계 음과 E단계 코드를 보고, 곡이 무슨 조(C major, A minor …)인지와 중간에 조가 바뀌는 곳을 찾는다.

문제지
  - E단계 7곡(모두 다장조)을 다시 쓴다
  - 08_내림마장조: 플랫 3개 조
  - 09_가단조: 단조. 이끎음 솔#(E7)이 나온다. 다장조와 조표가 같아 헷갈리기 쉽다
  - 10_조바꿈: 다장조 8마디 → 사장조 8마디(9마디 Am이 두 조에 다 있는 연결 코드)
정답지: answer.json — 조마다 [시작, 끝, 이름] (4분음표 단위, 예: "C major", "A minor")

점수(4분음표의 1/4 칸마다 비교해 맞은 시간의 비율, 1이 만점)
  - 조성_정확도: 으뜸음과 장·단조까지 맞으면
  - 조표_정확도: 조표만 맞으면(다장조와 가단조처럼 조표가 같은 조는 맞은 것으로 친다)
채점은 정답_입력(박·음을 MIDI에서)과 실제_입력(음원을 B~E단계로 분석) 두 가지로 한다.

실행:
  uv run python tests/benchmark/key_set.py build   # 정답지·새 곡 만들기 (E단계 build를 먼저)
  uv run python tests/benchmark/key_set.py grade
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
import chord_set  # noqa: E402
import rhythm_set  # noqa: E402
from beat_set import Song, q  # noqa: E402

from transcriber.chord_names import NOTE_NAMES  # noqa: E402

SET_DIR = BENCH / "keys"
OUTPUT = chord_set.OUTPUT
GRID = Fraction(1, 4)
MAJOR, HARMONIC_MINOR = (0, 2, 4, 5, 7, 9, 11), (0, 2, 3, 5, 7, 8, 11)

# 코드: (베이스 음, 위 음들)
EB, CM_, AB, BB7 = (39, (55, 58, 63)), (48, (55, 60, 63)), (44, (56, 60, 63)), (46, (56, 62, 65))
AM_, DM_, E7, F_ = (45, (57, 60, 64)), (50, (57, 62, 65)), (40, (56, 59, 62)), (41, (57, 60, 65))
C_, G7_, G_, D7, EM_ = (48, (55, 60, 64)), (43, (53, 59, 62)), (43, (55, 59, 62)), (50, (54, 60, 62)), (40, (55, 59, 64))


def scale_up(pitch: int, tonic: int, steps: tuple) -> int:
    """pitch 바로 위의 음계 음."""
    return next(p for p in range(pitch + 1, pitch + 13) if (p - tonic) % 12 in steps)


def key_song(bars: list) -> Song:
    """bars = 마디마다 (코드, 으뜸음, 음계). 베이스는 온음표, 화음은 박마다, 위 선율은 박마다 코드 음 + 뒷박 음계 음."""
    notes = []
    for bar, ((bass, tones), tonic, steps) in enumerate(bars):
        start = q(bar * 4)
        notes.append((bass, start, q(4), 90, 0))
        for beat in range(4):
            at = start + beat
            notes += [(p, at, q(1), 75 if beat else 85, 0) for p in tones]
            top = tones[beat % 3] + 12
            notes += [(top, at, q(1, 2), 90, 0), (scale_up(top, tonic, steps), at + q(1, 2), q(1, 2), 70, 0)]
    return Song(4, 4, ((q(0), 100.0),), q(0), len(bars), tuple(notes))


def in_key(chords: list, tonic: int, steps: tuple) -> list:
    return [(chord, tonic, steps) for chord in chords]


NEW_SONGS = {
    "08_내림마장조": key_song(in_key([EB, CM_, AB, BB7, EB, AB, BB7, EB], 3, MAJOR)),
    "09_가단조": key_song(in_key([AM_, DM_, E7, AM_, F_, DM_, E7, AM_], 9, HARMONIC_MINOR)),
    "10_조바꿈": key_song(in_key([C_, AM_, F_, G7_, C_, F_, G7_, C_], 0, MAJOR)
                         + in_key([AM_, D7, G_, EM_, C_, D7, G_, G_], 7, MAJOR)),
}
NEW_KEYS = {"08_내림마장조": [(0, 32, "Eb major")], "09_가단조": [(0, 32, "A minor")],
            "10_조바꿈": [(0, 32, "C major"), (32, 64, "G major")]}


def song_end(song: Song) -> Fraction:
    return max(start + length for _, start, length, _, _ in song.notes)


PROBLEMS = {name: (song, audio, [(0, song_end(song), "C major")])
            for name, (song, _, audio) in chord_set.PROBLEMS.items()}
PROBLEMS |= {name: (song, OUTPUT / "keys" / name / "problem.wav", NEW_KEYS[name]) for name, song in NEW_SONGS.items()}


def midi_of(name: str) -> Path:
    return SET_DIR / name / "problem.mid" if name in NEW_SONGS else chord_set.midi_of(name)


def build() -> None:
    for name, (song, audio, keys) in PROBLEMS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        if name in NEW_SONGS:
            beat_set.write_midi(song, folder / "problem.mid")
            audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio)
        answer = {"keys": [[str(Fraction(s)), str(Fraction(e)), k] for s, e, k in keys]}
        (folder / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        print(name, [k for _, _, k in keys])


def signature_of(name: str) -> int:
    """조 이름 → 조표(샵 수, 플랫은 음수). 예: 'G major' → 1, 'A minor' → 0."""
    tonic, mode = name.split()
    pitch = NOTE_NAMES.index(tonic[0]) + tonic[1:].count("#") - tonic[1:].count("b")
    major_tonic = (pitch + (3 if mode == "minor" else 0)) % 12
    sharps = major_tonic * 7 % 12
    return sharps - 12 if sharps > 6 else sharps


def key_at(segments: list, time: Fraction) -> str | None:
    return next((k for s, e, k in segments if Fraction(s) <= time < Fraction(e)), None)


def score(reference: list, estimate: list) -> dict:
    first, last = Fraction(reference[0][0]), Fraction(reference[-1][1])
    steps = int((last - first) / GRID)
    exact = same_signature = 0
    for i in range(steps):
        ref, est = key_at(reference, first + i * GRID), key_at(estimate, first + i * GRID)
        exact += ref == est
        same_signature += est is not None and signature_of(ref) == signature_of(est)
    return {"조성_정확도": round(exact / steps, 3), "조표_정확도": round(same_signature / steps, 3)}


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes
    from transcriber.analysis.tonality import analyze_key

    def rows(rhythm, beats):
        return [[k.start, k.end, k.name] for k in analyze_key(rhythm, analyze_harmony(rhythm, beats), beats).keys]

    report = {}
    for name, (song, audio, _) in PROBLEMS.items():
        reference = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))["keys"]
        beats, notes = rhythm_set.true_inputs(song, midi_of(name))
        real_beats = analyze_beats(audio)
        report[name] = {
            "정답_입력": score(reference, rows(quantize_notes(notes, beats), beats)),
            "실제_입력": score(reference, rows(quantize_notes(recognize_notes(audio)["mix"], real_beats), real_beats)),
        }
    (OUTPUT / "key_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
