"""리듬(분석기 D단계) 문제지·정답지와 채점.

리듬 단계는 C단계에서 찾은 음(초 단위 시작·끝)을 B단계의 박에 맞춰 악보에 쓸 수 있는 위치·길이로 바꾼다.
위치·길이는 모두 4분음표 단위 분수(1 = 4분음표, 1/2 = 8분음표, 1/3 = 셋잇단 8분음표). 0은 곡의 첫 소리 자리
(못갖춘마디가 있으면 그 시작).

문제지
  - B단계 피아노 5곡(4/4, 왈츠, 6/8, 빠르기 변화, 못갖춘마디)의 음원을 다시 쓴다
  - 06_리듬_여러가지: 점음표·16분음표·셋잇단·당김음·쉼표를 담은 새 곡
정답지: answer.json — 음마다 [음높이, 위치, 길이] (분수는 "3/2"처럼 글자로)

점수
  - 위치_F1: 음높이와 위치가 정확히 같은 음의 비율(1이 만점)
  - 길이_정확도: 위치를 맞힌 음 가운데 길이도 같은 비율
  - 둘다_F1: 위치와 길이가 모두 같은 음의 비율
채점은 두 가지로 한다
  - 정답_입력: 박·음을 정답(MIDI)에서 가져와 리듬 단계만 시험
  - 실제_입력: 음원을 B·C단계로 분석한 결과로 시험(전체 흐름)

실행:
  uv run python tests/benchmark/rhythm_set.py build   # 정답지·새 곡 만들기 (B단계 build를 먼저)
  uv run python tests/benchmark/rhythm_set.py grade
"""

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import pretty_midi

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parents[1] / "src"))

import beat_set  # noqa: E402
from beat_set import C, DM, F, G, Song, q  # noqa: E402

ROOT = BENCH.parents[1]
SET_DIR = BENCH / "rhythm"
OUTPUT = ROOT / "output" / "benchmark"
DRUM_CHANNEL = 9

# 한 마디 안의 선율 리듬(위치, 길이). 쉼표는 빈 자리
PATTERNS = (
    ((0, 1), (1, 1), (2, 2)),  # 4분 4분 2분
    ((0, q(3, 2)), (q(3, 2), q(1, 2)), (2, 1), (3, 1)),  # 점4분+8분
    tuple((q(i, 4), q(1, 4)) for i in range(4)) + ((1, 1), (2, 2)),  # 16분 넷
    tuple((q(i, 3), q(1, 3)) for i in range(6)) + ((2, 2),),  # 셋잇단 8분 둘
    ((0, q(1, 2)), (q(1, 2), 1), (q(3, 2), q(1, 2)), (2, 2)),  # 당김음 8분-4분-8분
    ((0, 1), (2, 1)),  # 4분, 4분쉼표, 4분, 4분쉼표
    ((0, q(3, 4)), (q(3, 4), q(1, 4)), (1, q(3, 4)), (q(7, 4), q(1, 4)), (2, 2)),  # 점8분+16분
    ((0, 4),),  # 온음표
)
MELODY = (72, 74, 76, 77, 79, 77, 76, 74)


def mixed_rhythms() -> Song:
    notes = []
    step = 0
    for bar, (bass, _) in enumerate([C, F, G, C, DM, G, F, C] * 2):
        start = q(bar * 4)
        notes += [(bass, start, q(2), 85, 0), (bass, start + 2, q(2), 70, 0)]
        for position, length in PATTERNS[bar % len(PATTERNS)]:
            on_beat = Fraction(position).denominator == 1
            notes.append((MELODY[step % len(MELODY)], start + position, Fraction(length), 90 if on_beat else 72, 0))
            step += 1
    return Song(4, 4, ((q(0), 90.0),), q(0), 16, tuple(notes))


# 문제 이름 → (곡 정의, 음원 위치)
NEW_SONGS = {"06_리듬_여러가지": mixed_rhythms()}
PROBLEMS = {
    **{name: (beat_set.SONGS[name], beat_set.AUDIO_DIR / name / "problem.wav")
       for name in ("01_4박자_피아노", "02_3박자_왈츠", "03_8분의6박자", "04_빠르기_변화", "05_못갖춘마디")},
    **{name: (song, OUTPUT / "rhythm" / name / "problem.wav") for name, song in NEW_SONGS.items()},
}


def answer_of(song: Song) -> dict:
    notes = sorted((pitch, Fraction(start), Fraction(length))
                   for pitch, start, length, _, channel in song.notes if channel != DRUM_CHANNEL)
    notes = sorted(notes, key=lambda n: (n[1], n[0]))
    return {
        "time_signature": f"{song.numerator}/{song.denominator}",
        "pickup_quarters": str(song.pickup),
        "notes": [[p, str(s), str(length)] for p, s, length in notes],
    }


def build() -> None:
    for name, (song, audio) in PROBLEMS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        if name in NEW_SONGS:
            beat_set.write_midi(song, folder / "problem.mid")
            audio.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio)
        (folder / "answer.json").write_text(json.dumps(answer_of(song), ensure_ascii=False), encoding="utf-8")
        print(name, "음", len(answer_of(song)["notes"]))


def score(reference: list, estimate: list) -> dict:
    """[음높이, 위치, 길이] 목록 두 개를 비교한 점수. 위치·길이는 분수 또는 "3/2" 같은 글자."""

    def keyed(notes):
        return [(int(p), Fraction(s), Fraction(length)) for p, s, length in notes]

    ref, est = keyed(reference), keyed(estimate)
    ref_lengths = {}
    for p, s, length in ref:
        ref_lengths.setdefault((p, s), []).append(length)
    placed, both = 0, 0
    for p, s, length in est:
        lengths = ref_lengths.get((p, s))
        if not lengths:
            continue
        placed += 1
        if length in lengths:
            both += 1
            lengths.remove(length)
        else:
            lengths.pop()

    def f1(hits):
        return round(2 * hits / (len(ref) + len(est)), 3) if ref or est else 1.0

    return {"위치_F1": f1(placed), "길이_정확도": round(both / placed, 3) if placed else 0.0,
            "둘다_F1": f1(both), "정답_음수": len(ref), "찾은_음수": len(est)}


def true_inputs(song: Song, midi_path: Path):
    """정답 박(BeatAnalysis)과 정답 음(초 단위)."""
    from transcriber.analysis.beats import BeatAnalysis
    from transcriber.pitch import Note

    answer = beat_set.answer_of(song)
    numerator, denominator = song.numerator, song.denominator
    compound = denominator == 8 and numerator % 3 == 0
    beats = BeatAnalysis(
        beats=tuple(answer["beats"]), downbeats=tuple(answer["downbeats"]), time_signature=answer["time_signature"],
        beats_per_bar=answer["beats_per_bar"], pulses_per_beat=3 if compound else 2,
        tempo_bpm=answer["tempo_bpm"][0]["bpm"], pickup_beats=int(answer["pickup_beats"]),
    )
    midi = pretty_midi.PrettyMIDI(str(midi_path))
    notes = tuple(sorted((Note(n.start, n.end, n.pitch, n.velocity)
                          for inst in midi.instruments if not inst.is_drum for n in inst.notes),
                         key=lambda n: (n.start_seconds, n.pitch)))
    return beats, notes


def midi_of(name: str) -> Path:
    return (SET_DIR if name in NEW_SONGS else beat_set.SET_DIR) / name / "problem.mid"


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes

    def rows(result):
        return [[n.pitch, n.start, n.length] for n in result.notes]

    report = {}
    for name, (song, audio) in PROBLEMS.items():
        reference = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))["notes"]
        beats, notes = true_inputs(song, midi_of(name))
        real = quantize_notes(recognize_notes(audio)["mix"], analyze_beats(audio))
        report[name] = {"정답_입력": score(reference, rows(quantize_notes(notes, beats))),
                        "실제_입력": score(reference, rows(real))}
    (OUTPUT / "rhythm_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
