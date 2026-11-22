"""멜로디·가사(분석기 I단계) 문제지·정답지와 채점.

멜로디·가사 단계는 D단계 음에서 멜로디(한 줄 선율)를 고르고, 사용자가 준 가사 글을 멜로디 음에 붙인다.

문제지(모두 새로 만든 곡, 16마디, C Am F G / C F G C)
  - 01_선율_화음: 8분음표 선율 + 박마다 화음 + 베이스
  - 02_긴음_분산화음: 2분음표 선율 + 그 아래 8분음표 분산화음(선율이 길게 울리는 동안 반주가 움직임)
  - 03_가사_구절: 2마디 구절 8개(끝에 4분쉼표) + 2분음표 화음, 새로 지은 가사(이어 부르기 '-' 포함)
정답지: answer.json — melody([음, 시작, 길이], 4분음표 단위), lyrics([시작, 글자])

점수(1이 만점)
  - 선율_F: 멜로디 음(높이 같고 시작이 1/4박 안)을 맞힌 정도
  - 가사_정확도: 정답 글자가 같은 자리(1/4박 안) 음에 붙은 비율
채점은 정답_입력(박·음을 MIDI에서)과 실제_입력(음원을 B~D단계로 분석) 두 가지로 한다.

실행:
  uv run python tests/benchmark/melody_set.py build
  uv run python tests/benchmark/melody_set.py grade
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
from structure_set import CHORDS, f_measure, phrase  # noqa: E402

SET_DIR = BENCH / "melody"
OUTPUT = chord_set.OUTPUT
NEAR = Fraction(1, 4)
BARS = [b for p in (phrase("C Am F G", 1), phrase("C F G C", 2)) * 2 for b in p]
LYRICS = "\n".join([
    "아침 햇살 창가에", "작은 새가 노래해",
    "바람 따라 흘러-", "구름 위로 날아가",
    "골목길을 지나서", "푸른 들판 너머로",
    "우리 함께 걸어가", "노을 지는 저녁-",
])


def chord_tones(name: str, low: int) -> list[int]:
    return sorted(low + (t - low) % 12 for t in CHORDS[name][1])


def song_of(notes: list, melody: list) -> tuple[Song, list]:
    return Song(4, 4, ((q(0), 100.0),), q(0), len(BARS), tuple(notes + [(p, s, l, 85, 0) for p, s, l in melody])), melody


def chords_with_eighths() -> tuple[Song, list]:
    notes, melody = [], []
    for bar, (name, line) in enumerate(BARS):
        start = q(bar * 4)
        notes.append((CHORDS[name][0] - 12, start, q(4), 70, 0))
        notes += [(p, start + beat, q(1, 2), 60, 0) for beat in range(4) for p in chord_tones(name, 55)]
        melody += [(p, start + q(i, 2), q(1, 2)) for i, p in enumerate(line)]
    return song_of(notes, melody)


def held_over_arpeggio() -> tuple[Song, list]:
    notes, melody = [], []
    for bar, (name, line) in enumerate(BARS):
        start = q(bar * 4)
        tones = chord_tones(name, 48) + [chord_tones(name, 48)[0] + 12]
        notes += [(p, start + q(i, 2), q(1, 2), 60, 0) for i, p in enumerate(tones + tones[::-1])]
        melody += [(line[0] + 7, start, q(2)), (line[4] + 7, start + 2, q(2))]
    return song_of(notes, melody)


def lyric_phrases() -> tuple[Song, list]:
    """2마디 구절: 4분음표 4개 + 4분음표 3개 + 4분쉼표."""
    notes, melody = [], []
    for bar, (name, line) in enumerate(BARS):
        start = q(bar * 4)
        notes += [(p, start + h * 2, q(2), 60, 0) for h in range(2) for p in chord_tones(name, 48)]
        count = 4 if bar % 2 == 0 else 3
        melody += [(line[i * 2], start + i, q(1)) for i in range(count)]
    return song_of(notes, melody)


SONGS = {"01_선율_화음": chords_with_eighths(), "02_긴음_분산화음": held_over_arpeggio(), "03_가사_구절": lyric_phrases()}


def answer_lyrics(melody: list) -> list:
    """정답 글자: 줄마다 구절(7음) 하나. '-'는 앞 글자를 이어 부르는 ""."""
    from transcriber.lyrics import parse_lyrics

    syllables = [s for line in LYRICS.splitlines() for s in parse_lyrics(line)]
    return [[str(start), s] for (_, start, _), s in zip(melody, syllables)]


def audio_of(name: str) -> Path:
    return OUTPUT / "melody" / name / "problem.wav"


def build() -> None:
    for name, (song, melody) in SONGS.items():
        folder = SET_DIR / name
        folder.mkdir(parents=True, exist_ok=True)
        beat_set.write_midi(song, folder / "problem.mid")
        audio_of(name).parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(beat_set.midi_to_audio(folder / "problem.mid")), audio_of(name))
        answer = {"melody": [[p, str(s), str(length)] for p, s, length in melody],
                  "lyrics": answer_lyrics(melody) if "가사" in name else []}
        (folder / "answer.json").write_text(json.dumps(answer, ensure_ascii=False), encoding="utf-8")
        print(name, f"멜로디 음 {len(melody)}개")


def pair(wanted: list, found: list, same) -> int:
    """시작이 NEAR 안이고 same(정답, 찾은 것)인 짝 수(하나씩만 짝짓는다)."""
    left, hits = list(found), 0
    for w in wanted:
        match = next((f for f in left if abs(f[0] - w[0]) <= NEAR and same(w, f)), None)
        if match is not None:
            left.remove(match)
            hits += 1
    return hits


def score(answer: dict, notes: tuple) -> dict:
    wanted = [(Fraction(s), p) for p, s, _ in answer["melody"]]
    found = [(n.start, n.pitch) for n in notes]
    words = [(Fraction(s), w) for s, w in answer["lyrics"]]
    sung = [(n.start, n.lyric) for n in notes if n.lyric is not None]
    result = {"선율_F": f_measure(pair(wanted, found, lambda w, f: w[1] == f[1]), len(found), len(wanted))}
    if words:
        result["가사_정확도"] = round(pair(words, sung, lambda w, f: w[1] == f[1]) / len(words), 3)
    return result


def grade() -> dict:
    from transcriber.analysis.beats import analyze_beats
    from transcriber.analysis.melody import analyze_melody
    from transcriber.analysis.notes import recognize_notes
    from transcriber.analysis.rhythm import quantize_notes

    report = {}
    for name, (song, _) in SONGS.items():
        answer = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))
        text = LYRICS if answer["lyrics"] else None
        beats, notes = rhythm_set.true_inputs(song, SET_DIR / name / "problem.mid")
        real_beats = analyze_beats(audio_of(name))
        real_notes = recognize_notes(audio_of(name))["mix"]
        report[name] = {
            "정답_입력": score(answer, analyze_melody(quantize_notes(notes, beats), text).notes),
            "실제_입력": score(answer, analyze_melody(quantize_notes(real_notes, real_beats), text).notes),
        }
    (OUTPUT / "melody_채점.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
