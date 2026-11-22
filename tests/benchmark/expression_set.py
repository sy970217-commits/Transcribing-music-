"""표현(분석기 H단계) 문제지·정답지와 채점.

표현 단계는 음원 소리와 D단계 음, E단계 코드를 보고 셈여림(p, f, <, >)과 오른쪽 페달 밟는 곳을 찾는다.

문제지(모두 새로 만든 곡, 마디마다 베이스 온음표 + 8분음표 분산화음 또는 선율)
  - 01_셈여림: 4마디씩 p → f → mp → ff
  - 02_점점: p → 점점 세게(<) → f → 점점 여리게(>) → p
  - 03_페달_분산화음: 앞 8마디는 마디마다 페달, 뒤 8마디는 페달 없이 짧게
  - 04_페달_선율: 선율 + 4분음표 화음. 앞 8마디는 마디마다 페달, 뒤 8마디는 페달 없음
정답지: answer.json — marks(마디마다 셈여림 글자 또는 < >), pedals([시작, 끝], 4분음표 단위)

점수(1이 만점)
  - 셈여림_정확도: 마디마다 글자(< > 포함)가 맞은 비율
  - 한단계_안: 글자 마디 중 한 단계 안(p와 mp 등)으로 맞은 비율
  - 페달_정확도: 4분음표의 1/4 칸마다 밟음·뗌이 맞은 비율
  - 페달_F: 페달을 밟는 곳을 반 박 안에서 맞힌 정도
채점은 정답_입력(박·음을 MIDI에서, 소리는 음원에서)과 실제_입력(음원을 B~E단계로 분석) 두 가지로 한다.

실행:
  uv run python tests/benchmark/expression_set.py build
  uv run python tests/benchmark/expression_set.py grade
"""

import json
import shutil
import sys
from fractions import Fraction
from pathlib import Path

import mido

BENCH = Path(__file__).resolve().parent
sys.path.insert(0, str(BENCH))
sys.path.insert(0, str(BENCH.parents[1] / "src"))

import beat_set  # noqa: E402
import chord_set  # noqa: E402
import rhythm_set  # noqa: E402
from beat_set import Song, q  # noqa: E402
from structure_set import CHORDS, f_measure, phrase  # noqa: E402

from transcriber.analysis.expression import LEVELS, level_for  # noqa: E402

SET_DIR = BENCH / "expression"
OUTPUT = chord_set.OUTPUT
GRID = Fraction(1, 4)
PROGRESSION = ["C", "Am", "F", "G"] * 4
PEDAL_LIFT = Fraction(1, 16)  # 마디 끝보다 이만큼 먼저 페달을 뗀다


def arpeggio_song(velocities: list[int]) -> Song:
    """마디마다 베이스 온음표 + 8분음표 분산화음(같은 음이 겹치지 않게 위로)."""
    notes = []
    for bar, name in enumerate(PROGRESSION):
        root, tones = CHORDS[name]
        start, velocity = q(bar * 4), velocities[bar]
        notes.append((root - 12, start, q(4), velocity, 0))
        pitches = sorted({55 + (t - 55) % 12 + 12 * octave for octave in range(3) for t in tones})[:8]
        for i, pitch in enumerate(pitches):
            notes.append((pitch, start + q(i, 2), q(1, 2), velocity, 0))
    return Song(4, 4, ((q(0), 100.0),), q(0), len(PROGRESSION), tuple(notes))


def melody_song() -> Song:
    """선율 8분음표 + 박마다 화음 + 베이스."""
    notes = []
    for bar, (name, melody) in enumerate(b for p in (phrase("C Am F G", 1), phrase("C F G C", 2)) * 2 for b in p):
        root, tones = CHORDS[name]
        start = q(bar * 4)
        notes.append((root - 12, start, q(4), 80, 0))
        for beat in range(4):
            notes += [(55 + (t - 55) % 12, start + beat, q(1, 2), 70, 0) for t in tones]
        notes += [(p, start + q(i, 2), q(1, 2), 80, 0) for i, p in enumerate(melody)]
    return Song(4, 4, ((q(0), 100.0),), q(0), 16, tuple(notes))


STEADY = [70] * 16
PEDAL_FIRST_HALF = [(q(b * 4), q(b * 4 + 4)) for b in range(8)]
SONGS = {
    "01_셈여림": (arpeggio_song([48] * 4 + [92] * 4 + [63] * 4 + [110] * 4), []),
    "02_점점": (arpeggio_song([48] * 4 + [60, 72, 84] + [96] * 3 + [84, 72, 60] + [48] * 3), []),
    "03_페달_분산화음": (arpeggio_song(STEADY), PEDAL_FIRST_HALF),
    "04_페달_선율": (melody_song(), PEDAL_FIRST_HALF),
}
MARKS = {"01_셈여림": ["p"] * 4 + ["f"] * 4 + ["mp"] * 4 + ["ff"] * 4,
         "02_점점": ["p"] * 4 + ["<"] * 3 + ["f"] * 3 + [">"] * 3 + ["p"] * 3}


def answer_marks(name: str, song: Song) -> list[str]:
    if name in MARKS:
        return MARKS[name]
    bars = [[v for _, s, _, v, _ in song.notes if b * 4 <= s < b * 4 + 4] for b in range(song.bars)]
    return [level_for(sum(v) / len(v)) for v in bars]


def write_pedals(path: Path, spans: list) -> None:
    """MIDI 파일에 오른쪽 페달(조절 신호 64번) 밟기·떼기를 넣는다."""
    midi = mido.MidiFile(path)
    track, now, events = midi.tracks[1], 0, []
    for message in track:
        now += message.time
        events.append((now, message))
    for start, end in spans:
        events.append((round(start * beat_set.TICKS), mido.Message("control_change", control=64, value=127)))
        events.append((round((end - PEDAL_LIFT) * beat_set.TICKS), mido.Message("control_change", control=64, value=0)))
    messages, now = [], 0
    for tick, message in sorted(events, key=lambda e: e[0]):
        messages.append(message.copy(time=tick - now))
        now = tick
    midi.tracks[1] = mido.MidiTrack(messages)
    midi.save(path)


def audio_of(name: str) -> Path:
    return OUTPUT / "expression" / name / "problem.wav"


def build() -> None:
    for name, (song, pedals) in SONGS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        beat_set.write_midi(song, folder / "problem.mid")
        write_pedals(folder / "problem.mid", pedals)
        audio_of(name).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio_of(name))
        answer = {"marks": answer_marks(name, song), "pedals": [[str(s), str(e)] for s, e in pedals]}
        (folder / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        print(name, " ".join(answer["marks"]), f"페달 {len(pedals)}번")


def marks_by_bar(dynamics: tuple, bars: int) -> list[str | None]:
    return [next((d.mark for d in dynamics if d.start <= b * 4 + 2 < d.end), None) for b in range(bars)]


def on_at(spans: list, time: Fraction) -> bool:
    return any(Fraction(s) <= time < Fraction(e) for s, e in spans)


def score(answer: dict, dynamics: tuple, pedals: list, end: Fraction) -> dict:
    wanted, found = answer["marks"], marks_by_bar(dynamics, len(answer["marks"]))
    names = [name for name, _ in LEVELS]
    letters = [(w, f) for w, f in zip(wanted, found) if w not in "<>"]
    near = sum(1 for w, f in letters if f in names and abs(names.index(w) - names.index(f)) <= 1)
    steps = int(end / GRID)
    reference = answer["pedals"]
    same = sum(on_at(reference, i * GRID) == on_at(pedals, i * GRID) for i in range(steps))
    downs, left, hits = [Fraction(s) for s, _ in reference], [Fraction(s) for s, _ in pedals], 0
    for down in downs:
        match = next((f for f in left if abs(f - down) <= Fraction(1, 2)), None)
        if match is not None:
            left.remove(match)
            hits += 1
    return {"셈여림_정확도": round(sum(w == f for w, f in zip(wanted, found)) / len(wanted), 3),
            "한단계_안": round(near / len(letters), 3) if letters else 1.0,
            "페달_정확도": round(same / steps, 3), "페달_F": f_measure(hits, len(pedals), len(downs)),
            "찾은_셈여림": " ".join(str(f) for f in found)}


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.expression import analyze_expression, measure_sounds
    from transcriber.analysis.harmony import analyze_harmony
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes

    def run(notes, beats, audio):
        rhythm = quantize_notes(notes, beats)
        sounds = measure_sounds(audio, notes, beats)
        result = analyze_expression(rhythm, analyze_harmony(rhythm, beats), beats, sounds)
        return result.dynamics, [(p.start, p.end) for p in result.pedals]

    report = {}
    for name, (song, _) in SONGS.items():
        answer = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))
        beats, notes = rhythm_set.true_inputs(song, SET_DIR / name / "problem.mid")
        real_beats = analyze_beats(audio_of(name))
        end = q(song.bars * 4)
        report[name] = {
            "정답_입력": score(answer, *run(notes, beats, audio_of(name)), end),
            "실제_입력": score(answer, *run(recognize_notes(audio_of(name))["mix"], real_beats, audio_of(name)), end),
        }
    (OUTPUT / "expression_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
