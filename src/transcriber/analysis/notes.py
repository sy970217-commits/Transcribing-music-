"""분석기 C단계: 음 인식. 음원(또는 A단계에서 나눈 트랙)에서 음의 높이·시작·끝·세기를 찾는다.

- 소리 분리 결과가 없으면 섞인 음원 전체에서 찾는다(트랙 이름 'mix').
- 있으면 음높이가 있는 트랙(목소리·피아노·베이스·기타·나머지)마다 따로 찾는다.
  드럼은 음높이가 없어 빼고, '없다'고 판단된 트랙도 뺀다.
  - 트랙마다 악기 음역 밖의 음은 버린다(새어 들어온 소리·배음 오인식 줄이기).
  - 목소리·베이스는 한 번에 한 음만 내므로 겹친 음 중 하나만 남긴다.
  - 목소리에서 틈 없이 쪼개진 같은 높이 음은 한 음으로 합친다(길게 부른 음이 여러 음으로 적히지 않게).
  - 목소리에서 앞뒤 음보다 크게 튄 음은 옥타브를 잘못 들은 것으로 보고 한 옥타브 옮긴다.
음 찾기는 Spotify Basic Pitch(transcriber.pitch)를 쓴다.

실행: uv run notes 곡.wav [--separate]
"""

import argparse
import sys
from dataclasses import replace
from pathlib import Path

from transcriber.analysis.separation import Separation, SeparationError, separate
from transcriber.audio_io import AudioLoadError
from transcriber.pitch import Note, PitchDetectionError, detect_notes

# 트랙 → (가장 낮은 음, 가장 높은 음) MIDI 번호
TRACK_RANGES = {
    "vocals": (48, 84),  # C3~C6
    "bass": (28, 64),  # E1~E4
    "guitar": (40, 88),
    "piano": (21, 108),  # 피아노 88건반
    "other": (21, 108),
}
MONOPHONIC_TRACKS = frozenset({"vocals", "bass"})
OCTAVE_FIX_TRACKS = frozenset({"vocals"})
JOIN_TRACKS = frozenset({"vocals"})
SPLIT_GAP_SECONDS = 0.02  # 같은 높이 음 사이 틈이 이보다 짧으면 길게 부른 한 음이 쪼개진 것으로 본다
OCTAVE = 12
# 앞뒤 음 모두보다 높거나(낮거나), 한쪽과는 SPIKE_BIG, 다른 쪽과는 SPIKE_SMALL 반음 이상 떨어지면 튄 음으로 본다
# (5도 뛰었다 돌아오는 7·7은 진짜 선율일 수 있어 그대로 둔다)
SPIKE_BIG = 9
SPIKE_SMALL = 7
SAME_START_SECONDS = 0.05  # 이 시간 안에 시작한 음들은 동시에 시작한 것으로 본다
# 트랙 → (음 시작 기준, 울림 기준, 가장 짧은 음 ms, 이어 붙이기). 문제지 채점으로 고름(시작_F1 평균):
# 피아노 0.85→0.91, 목소리 0.43→0.77, 베이스 0.62→0.83. 기본값(0.5, 0.4, 128)보다 확실한 시작만 잡는다
# 피아노는 소리가 서서히 작아져 음 끝이 일찍 잘린다. 분리한 피아노 트랙은 소리가 약해 울림 기준을 0.3으로
# 낮추고 이어 붙이기를 끈다(길이까지_F1 노래+피아노 0.18→0.56, 밴드 0.10→0.33)
TRACK_SETTINGS = {
    "piano": (0.7, 0.3, 58.0, False),
    "vocals": (0.7, 0.4, 58.0, True),
    "bass": (0.7, 0.5, 58.0, True),
}
MIX_SETTINGS = (0.7, 0.5, 58.0, False)  # 섞인 음원 전체(피아노 독주 기준)
DEFAULT_SETTINGS = TRACK_SETTINGS["piano"]
MIX = "mix"


def to_monophonic(notes: tuple[Note, ...]) -> tuple[Note, ...]:
    """노래는 한 번에 한 음만 낸다. 겹치는 음을 정리해 한 줄 멜로디로 만든다.

    동시에 시작한 음 중에서는 가장 센 음을 남기고, 앞 음은 다음 음이 시작할 때 끊는다.
    """
    ordered = sorted(notes, key=lambda n: (n.start_seconds, -n.velocity))
    melody: list[Note] = []
    for current in ordered:
        if melody and current.start_seconds - melody[-1].start_seconds < SAME_START_SECONDS:
            if current.velocity > melody[-1].velocity:
                melody[-1] = current
            continue
        if melody and melody[-1].end_seconds > current.start_seconds:
            previous = melody[-1]
            melody[-1] = Note(
                start_seconds=previous.start_seconds,
                end_seconds=current.start_seconds,
                pitch=previous.pitch,
                velocity=previous.velocity,
            )
        melody.append(current)
    return tuple(melody)


def join_split_notes(notes: tuple[Note, ...]) -> tuple[Note, ...]:
    """한 줄 선율에서 틈 없이 이어진 같은 높이 음을 한 음으로 합친다.

    음 찾기 AI는 길게 부른 음을 중간에 끊어 같은 음 두세 개로 적는 일이 많다. 쉬었다가 다시 부른 음은 그대로 둔다.
    """
    joined: list[Note] = []
    for current in notes:
        previous = joined[-1] if joined else None
        if previous and previous.pitch == current.pitch and current.start_seconds - previous.end_seconds < SPLIT_GAP_SECONDS:
            joined[-1] = replace(previous, end_seconds=max(previous.end_seconds, current.end_seconds))
            continue
        joined.append(current)
    return tuple(joined)


def fix_octave_jumps(notes: tuple[Note, ...]) -> tuple[Note, ...]:
    """한 줄 선율에서 앞뒤 음보다 크게 튄 음을 한 옥타브 옮긴다. 옮겨서 앞뒤 음과 더 가까워질 때만 옮긴다.

    음 찾기 AI는 목소리의 음높이를 한 옥타브 위나 아래로 잘못 듣는 일이 많다.
    """
    fixed = list(notes)
    for i in range(1, len(fixed) - 1):
        before, current, after = fixed[i - 1].pitch, fixed[i].pitch, fixed[i + 1].pitch
        up, down = current - before, current - after
        gaps = sorted((abs(up), abs(down)))
        if gaps[0] < SPIKE_SMALL or gaps[1] < SPIKE_BIG or (up > 0) != (down > 0):
            continue
        moved = current - OCTAVE if up > 0 else current + OCTAVE
        if abs(moved - before) + abs(moved - after) < abs(up) + abs(down):
            fixed[i] = replace(fixed[i], pitch=moved)
    return tuple(fixed)


def recognize_notes(audio_path: str | Path, separation: Separation | None = None) -> dict[str, tuple[Note, ...]]:
    """트랙 이름 → 음 목록(시작 순). 소리 분리가 없으면 {'mix': 전체 음}."""
    if separation is None:
        return {MIX: _detect(audio_path, MIX)}
    found = {}
    for track, path in separation.stems.items():
        if track not in TRACK_RANGES or not separation.present(track):
            continue
        found[track] = clean_track(track, _detect(path, track))
    return found


def merge_tracks(found: dict[str, tuple[Note, ...]]) -> tuple[Note, ...]:
    """트랙마다 찾은 음을 한 목록으로 합친다(시작 순). 피아노 악보는 모든 악기 음을 함께 적는다."""
    return tuple(sorted((n for notes in found.values() for n in notes), key=lambda n: (n.start_seconds, n.pitch)))


def _detect(path: str | Path, track: str) -> tuple[Note, ...]:
    settings = MIX_SETTINGS if track == MIX else TRACK_SETTINGS.get(track, DEFAULT_SETTINGS)
    onset, frame, shortest, melodia = settings
    return detect_notes(
        path, onset_threshold=onset, frame_threshold=frame, min_note_ms=shortest, melodia_trick=melodia
    ).notes


def clean_track(track: str, notes: tuple[Note, ...]) -> tuple[Note, ...]:
    """악기 음역 밖의 음을 버리고, 한 음씩 내는 악기는 겹친 음을 하나로 줄인다. 목소리는 쪼개진 음을 합치고 튄 음을 바로잡는다."""
    low, high = TRACK_RANGES.get(track, (0, 127))
    kept = tuple(n for n in notes if low <= n.pitch <= high)
    line = to_monophonic(kept) if track in MONOPHONIC_TRACKS else kept
    line = join_split_notes(line) if track in JOIN_TRACKS else line
    return fix_octave_jumps(line) if track in OCTAVE_FIX_TRACKS else line


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="음원에서 음을 찾는다 (분석기 C단계)")
    parser.add_argument("audio", help="음원 파일")
    parser.add_argument("--separate", action="store_true", help="먼저 소리를 나눠 트랙마다 찾기(몇 분 걸림)")
    args = parser.parse_args(argv)
    try:
        separation = separate(args.audio) if args.separate else None
        found = recognize_notes(args.audio, separation)
    except (AudioLoadError, SeparationError, PitchDetectionError) as error:
        print(f"오류: {error}", file=sys.stderr)
        return 1
    for track, notes in found.items():
        print(f"{track}: 음 {len(notes)}개")
    return 0


if __name__ == "__main__":
    sys.exit(main())
