"""박·박자 분석(분석기 B단계) 문제지·정답지 만들기와 채점.

문제지: 피아노(또는 밴드) 연주 음원(problem.wav)과 그 MIDI(problem.mid)
정답지: answer.json
  - beats: 박 위치(초). 6/8은 점4분음표가 한 박
  - downbeats: 마디 첫 박 위치(초)
  - time_signature: 박자표, tempo_bpm: 박 기준 빠르기(바뀌면 구간별)

곡은 코드로 직접 만든다(저작권 없음). 음원은 output/benchmark/beats/ 에 만든다(올리지 않음).

실행:
  uv run python tests/benchmark/beat_set.py build
  uv run python tests/benchmark/beat_set.py grade
"""

import json
import shutil
import sys
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import mido

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from transcriber.render import midi_to_audio  # noqa: E402

SET_DIR = Path(__file__).resolve().parent / "beats"
AUDIO_DIR = ROOT / "output" / "benchmark" / "beats"
TICKS = 480  # 4분음표 한 개의 틱 수

C, AM, F, G, G7, DM = (
    (48, (60, 64, 67)),
    (45, (57, 60, 64)),
    (41, (57, 60, 65)),
    (43, (55, 59, 62)),
    (43, (53, 59, 62)),
    (50, (57, 62, 65)),
)


@dataclass(frozen=True)
class Song:
    """곡 정의. 위치·길이는 모두 4분음표 단위(MIDI 박)."""

    numerator: int  # 박자표 위
    denominator: int  # 박자표 아래
    tempo: tuple[tuple[Fraction, float], ...]  # (4분음표 위치, 4분음표 기준 BPM)
    pickup: Fraction  # 못갖춘마디 길이(4분음표 단위). 없으면 0
    bars: int  # 갖춘마디 수
    notes: tuple[tuple[int, Fraction, Fraction, int, int], ...]  # (음, 시작, 길이, 세기, 채널)
    programs: tuple[tuple[int, int], ...] = ((0, 0),)  # (채널, 악기)

    @property
    def bar_quarters(self) -> Fraction:
        return Fraction(self.numerator * 4, self.denominator)

    @property
    def beat_quarters(self) -> Fraction:
        """세는 박 하나의 길이. 6/8·9/8·12/8은 점4분음표(8분음표 3개)."""
        compound = self.denominator == 8 and self.numerator % 3 == 0
        return Fraction(3, 2) if compound else Fraction(4, self.denominator)


def q(*parts) -> Fraction:
    return Fraction(*parts)


def four_four_piano() -> Song:
    notes = []
    for bar, (bass, chord) in enumerate([C, AM, F, G] * 3):
        start = q(bar * 4)
        notes.append((bass, start, q(2), 90, 0))
        notes.append((bass, start + 2, q(2), 70, 0))
        for i in range(8):  # 8분음표 분산화음, 박 첫 음을 조금 세게
            pitch = chord[i % 3] + 12 * (i // 3 % 2)
            notes.append((pitch, start + q(i) / 2, q(1, 2), 80 if i % 2 == 0 else 60, 0))
    return Song(4, 4, ((q(0), 100.0),), q(0), 12, tuple(notes))


def waltz() -> Song:
    notes = []
    for bar, (bass, chord) in enumerate([C, G7, G7, C, F, C, G7, C] * 2):
        start = q(bar * 3)
        notes.append((bass, start, q(1), 95, 0))  # 쿵
        for beat in (1, 2):  # 짝 짝
            notes += [(p, start + beat, q(1, 2), 60, 0) for p in chord]
        notes.append((chord[2] + 12, start, q(3), 75, 0))  # 위 선율 한 음
    return Song(3, 4, ((q(0), 120.0),), q(0), 16, tuple(notes))


def six_eight() -> Song:
    notes = []
    for bar, (bass, chord) in enumerate([C, G, AM, F] * 3):
        start = q(bar * 3)  # 6/8 한 마디 = 4분음표 3개
        notes.append((bass, start, q(3, 2), 95, 0))
        notes.append((bass + 7, start + q(3, 2), q(3, 2), 70, 0))
        for i in range(6):  # 8분음표 6개, 1·4번째를 세게
            pitch = (chord + (chord[0] + 12,))[[0, 1, 2, 3, 2, 1][i]]
            notes.append((pitch, start + q(i) / 2, q(1, 2), 85 if i in (0, 3) else 55, 0))
    # 점4분음표 = 60 → 4분음표 = 90
    return Song(6, 8, ((q(0), 90.0),), q(0), 12, tuple(notes))


def ritardando() -> Song:
    base = four_four_piano()
    tempo = [(q(0), 100.0)]
    for i, beat in enumerate(range(24, 32)):  # 7~8마디: 한 박마다 조금씩 느려져 70까지
        tempo.append((q(beat), 100.0 - 30.0 * (i + 1) / 8))
    tempo.append((q(32), 100.0))  # 9마디부터 원래 빠르기(a tempo)
    return Song(4, 4, tuple(tempo), q(0), 12, base.notes)


def pickup() -> Song:
    notes = [(67, q(0), q(1), 85, 0)]  # 못갖춘마디: 솔 한 박
    for bar, (bass, chord) in enumerate([C, F, G, C] * 2):
        start = 1 + q(bar * 4)
        notes.append((bass, start, q(4), 90, 0))
        notes += [(p, start + b, q(1), 70 if b else 85, 0) for b in range(4) for p in chord]
        notes.append((chord[2] + 12, start, q(2), 90, 0))
    return Song(4, 4, ((q(0), 96.0),), q(1), 8, tuple(notes))


def band() -> Song:
    notes = []
    for bar, (bass, chord) in enumerate([C, AM, DM, G] * 3):
        start = q(bar * 4)
        notes += [(bass - 12, start + b, q(1), 100, 2) for b in range(4)]
        notes += [(p, start + b + q(1, 2), q(1, 2), 65, 0) for b in range(4) for p in chord]  # 뒷박 화음
        for b in range(4):
            notes.append((36 if b % 2 == 0 else 38, start + b, q(1, 2), 105 if b == 0 else 90, 9))
            notes += [(42, start + b + h, q(1, 4), 60, 9) for h in (0, q(1, 2))]
        notes.append((49, start, q(1), 90, 9))  # 마디 첫 박 심벌
    return Song(4, 4, ((q(0), 110.0),), q(0), 12, tuple(notes), ((0, 0), (2, 33), (9, 0)))


SONGS = {
    "01_4박자_피아노": four_four_piano(),
    "02_3박자_왈츠": waltz(),
    "03_8분의6박자": six_eight(),
    "04_빠르기_변화": ritardando(),
    "05_못갖춘마디": pickup(),
    "06_드럼_밴드": band(),
}


def seconds_at(position: Fraction, tempo: tuple[tuple[Fraction, float], ...]) -> float:
    """4분음표 위치 → 초."""
    total, previous = 0.0, None
    for start, bpm in tempo:
        if previous is not None:
            end = min(position, start)
            if end > previous[0]:
                total += float(end - previous[0]) * 60.0 / previous[1]
        if start >= position:
            return total
        previous = (start, bpm)
    return total + float(position - previous[0]) * 60.0 / previous[1]


def answer_of(song: Song) -> dict:
    end = song.pickup + song.bars * song.bar_quarters
    beat_positions, pos = [], song.pickup % song.beat_quarters
    while pos < end:
        beat_positions.append(pos)
        pos += song.beat_quarters
    downbeats = [song.pickup + i * song.bar_quarters for i in range(song.bars)]
    # 박 기준 빠르기 = 4분음표 BPM ÷ (한 박의 4분음표 수). 6/8에서 4분음표 90 → 점4분음표 60
    tempo_in_beats = [(float(p / song.beat_quarters), bpm / float(song.beat_quarters)) for p, bpm in song.tempo]
    return {
        "time_signature": f"{song.numerator}/{song.denominator}",
        "beats_per_bar": int(song.bar_quarters / song.beat_quarters),
        "pickup_beats": float(song.pickup / song.beat_quarters),
        "tempo_bpm": [{"beat": b, "bpm": round(bpm, 3)} for b, bpm in tempo_in_beats],
        "beats": [round(seconds_at(p, song.tempo), 4) for p in beat_positions],
        "downbeats": [round(seconds_at(p, song.tempo), 4) for p in downbeats],
    }


def write_midi(song: Song, path: Path) -> None:
    midi = mido.MidiFile(ticks_per_beat=TICKS)
    meta = [mido.MetaMessage("time_signature", numerator=song.numerator, denominator=song.denominator, time=0)]
    now = 0
    for position, bpm in song.tempo:
        tick = round(position * TICKS)
        meta.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(bpm), time=tick - now))
        now = tick
    midi.tracks.append(mido.MidiTrack(meta))
    events = [(0, 0, mido.Message("program_change", channel=ch, program=prog)) for ch, prog in song.programs]
    for pitch, start, length, velocity, channel in song.notes:
        events.append((round(start * TICKS), 2, mido.Message("note_on", note=pitch, velocity=velocity, channel=channel)))
        events.append((round((start + length) * TICKS), 1, mido.Message("note_off", note=pitch, velocity=0, channel=channel)))
    messages, now = [], 0
    for tick, _, message in sorted(events, key=lambda e: (e[0], e[1])):
        messages.append(message.copy(time=tick - now))
        now = tick
    midi.tracks.append(mido.MidiTrack(messages))
    path.parent.mkdir(parents=True, exist_ok=True)
    midi.save(path)


def build() -> None:
    for name, song in SONGS.items():
        folder = SET_DIR / name
        write_midi(song, folder / "problem.mid")
        (folder / "answer.json").write_text(json.dumps(answer_of(song), ensure_ascii=False, indent=2), encoding="utf-8")
        audio = AUDIO_DIR / name
        audio.mkdir(parents=True, exist_ok=True)
        shutil.move(str(midi_to_audio(folder / "problem.mid")), audio / "problem.wav")
        print(f"{name}: {song.numerator}/{song.denominator}, 박 {len(answer_of(song)['beats'])}개")


def grade() -> dict:
    import mir_eval

    from transcriber.analysis.beats import analyze_beats

    report = {}
    for name in SONGS:
        answer = json.loads((SET_DIR / name / "answer.json").read_text(encoding="utf-8"))
        result = analyze_beats(AUDIO_DIR / name / "problem.wav")
        beat_f = mir_eval.beat.f_measure(
            mir_eval.beat.trim_beats(__import__("numpy").array(answer["beats"])),
            mir_eval.beat.trim_beats(__import__("numpy").array(result.beats)),
        )
        down_f = mir_eval.beat.f_measure(
            __import__("numpy").array(answer["downbeats"]), __import__("numpy").array(result.downbeats)
        )
        report[name] = {
            "박_정확도": round(beat_f, 3),
            "첫박_정확도": round(down_f, 3),
            "박자표": f"{result.time_signature} (정답 {answer['time_signature']})",
            "박자표_맞음": result.time_signature == answer["time_signature"],
            "빠르기": f"{result.tempo_bpm:.1f} (정답 처음 {answer['tempo_bpm'][0]['bpm']})",
            "못갖춘마디_맞음": result.pickup_beats == answer["pickup_beats"],
        }
    out = AUDIO_DIR / "채점.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) > 1 else "build"
    build() if command == "build" else grade()
