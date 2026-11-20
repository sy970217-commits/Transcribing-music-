"""박자 정리된 음으로 피아노 악보(MusicXML)를 만드는 모듈. music21을 사용한다."""

import math
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from music21 import chord, clef, key, metadata, meter, note, stream, tempo

from transcriber.lyrics import attach_lyrics
from transcriber.rhythm import QuantizedNote

MIDDLE_C = 60  # 가운데 도. 이 음 이상은 오른손(높은음자리표), 아래는 왼손(낮은음자리표)
DEFAULT_TIME_SIGNATURE = "4/4"
KEY_WINDOW_MEASURES = 4  # 조성을 이 마디 수씩 끊어서 찾는다
MIN_KEY_RUN_WINDOWS = 3  # 같은 조표가 3창(12마디) 이상 이어져야 조바꿈으로 인정
MIN_NOTES_FOR_KEY = 8  # 한 창에 음이 이보다 적으면 조성을 판단하지 않는다


@dataclass(frozen=True)
class ScoreInfo:
    """악보 맨 위에 적을 정보와 조성.

    key_name 예: "G"(사장조), "e"(마단조, 소문자=단조). 비워 두면 자동으로 찾는다.
    """

    title: str = ""
    composer: str = ""
    lyricist: str = ""
    key_name: str | None = None
    lyrics: tuple[str, ...] = ()  # 멜로디에 붙일 음절. lyrics.parse_lyrics로 만든다


def build_score(
    notes: tuple[QuantizedNote, ...],
    tempo_bpm: float,
    info: ScoreInfo = ScoreInfo(),
    time_signature: str = DEFAULT_TIME_SIGNATURE,
    melody: tuple[QuantizedNote, ...] = (),
) -> stream.Score:
    """피아노 2단(오른손/왼손) 악보를 만든다. melody가 있으면 맨 위에 멜로디 단을 더한다.

    info.lyrics(음절 목록)가 있으면 멜로디 음표에 차례로 붙인다.
    """
    if not notes and not melody:
        raise ValueError("악보로 만들 음이 없습니다.")
    if info.lyrics and not melody:
        raise ValueError(
            "가사를 붙이려면 멜로디 단이 필요해요. MIDI 파일을 넣거나 --vocals를 함께 쓰세요."
        )
    if tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")

    total_beats = max(n.start_beats + n.duration_beats for n in notes + melody)
    right_hand = tuple(n for n in notes if n.pitch >= MIDDLE_C)
    left_hand = tuple(n for n in notes if n.pitch < MIDDLE_C)

    parts = [
        _build_part(right_hand, clef.TrebleClef(), time_signature, total_beats),
        _build_part(left_hand, clef.BassClef(), time_signature, total_beats),
    ]
    if melody:
        melody_part = _build_part(melody, clef.TrebleClef(), time_signature, total_beats)
        melody_part.partName = "멜로디"
        attach_lyrics(melody_part, info.lyrics)
        parts.insert(0, melody_part)
    parts[0].insert(0, tempo.MetronomeMark(number=round(tempo_bpm)))

    score = stream.Score()
    for part in parts:
        score.insert(0, part)

    bar_beats = meter.TimeSignature(time_signature).barDuration.quarterLength
    for start, song_key in _resolve_keys(notes + melody, bar_beats, info.key_name):
        for part in score.parts:
            part.insert(start, key.Key(song_key.tonic, song_key.mode))
    score.metadata = _build_metadata(info)
    return score


def key_name_of(score: stream.Score) -> str:
    """악보의 조성과 조표를 설명한다.

    예: "G major, 조표 ♯ 1개" 또는 조가 바뀌면
    "G major, 조표 ♯ 1개 → 41마디부터 A major, 조표 ♯ 3개".
    """
    first_part = score.parts.first()
    keys = list(first_part.flatten().getElementsByClass(key.Key)) if first_part else []
    if not keys:
        return "알 수 없음"
    time_signature = first_part.flatten().getElementsByClass(meter.TimeSignature).first()
    bar_beats = time_signature.barDuration.quarterLength if time_signature else 4
    descriptions = [_describe_key(keys[0])]
    for later in keys[1:]:
        measure = int(later.offset // bar_beats) + 1
        descriptions.append(f"{measure}마디부터 {_describe_key(later)}")
    return " → ".join(descriptions)


def _describe_key(song_key: key.Key) -> str:
    if song_key.sharps > 0:
        signature = f"♯ {song_key.sharps}개"
    elif song_key.sharps < 0:
        signature = f"♭ {-song_key.sharps}개"
    else:
        signature = "없음"
    return f"{song_key.name}, 조표 {signature}"


def _parse_key(key_name: str) -> key.Key:
    try:
        return key.Key(key_name)
    except Exception as error:
        raise ValueError(f"알 수 없는 조성입니다: {key_name} (예: G, D, e)") from error


def _resolve_keys(
    notes: tuple[QuantizedNote, ...], bar_beats, key_name: str | None
) -> list[tuple[Fraction, key.Key]]:
    """곡의 조성과, 중간에 조가 바뀌는 위치를 찾는다. [(시작 박, 조성), ...]

    곡을 4마디씩 잘라 조성을 찾고, 같은 조표가 12마디 이상 이어질 때만
    조바꿈으로 인정한다(잠깐 다른 조의 음이 나오는 것은 무시).
    """
    if key_name:
        return [(Fraction(0), _parse_key(key_name))]

    window = Fraction(bar_beats) * KEY_WINDOW_MEASURES
    total = max(n.start_beats + n.duration_beats for n in notes)
    window_count = math.ceil(total / window)
    window_keys = [
        _analyze_key(tuple(n for n in notes if i * window <= n.start_beats < (i + 1) * window))
        for i in range(window_count)
    ]
    change_windows = _stable_key_changes(window_keys)
    if not change_windows:
        return [(Fraction(0), _analyze_key(notes, min_notes=1))]

    boundaries = [i * window for i in change_windows] + [total + 1]
    return [
        (start, _analyze_key(tuple(n for n in notes if start <= n.start_beats < end), min_notes=1))
        for start, end in zip(boundaries, boundaries[1:])
    ]


def _analyze_key(notes: tuple[QuantizedNote, ...], min_notes: int = MIN_NOTES_FOR_KEY):
    if len(notes) < min_notes:
        return None
    sample = stream.Stream()
    for quantized in notes:
        sample.append(note.Note(quantized.pitch, quarterLength=quantized.duration_beats))
    return sample.analyze("key")


def _smooth_signatures(window_keys: list) -> list[int | None]:
    """각 창의 조표를 앞뒤 창과 다수결로 정한다. 한 창만 잘못 읽힌 것을 바로잡는다."""
    signatures = [k.sharps if k is not None else None for k in window_keys]
    smoothed: list[int | None] = []
    for index, own in enumerate(signatures):
        neighbors = [s for s in signatures[max(0, index - 1) : index + 2] if s is not None]
        if not neighbors:
            smoothed.append(None)
            continue
        counts = Counter(neighbors)
        best = max(counts.values())
        winners = [s for s, c in counts.items() if c == best]
        smoothed.append(own if own in winners else winners[0])
    return smoothed


def _stable_key_changes(window_keys: list) -> list[int]:
    """조표가 오래 이어지는 구간의 시작 창 번호들. 첫 값은 항상 0."""
    runs: list[list] = []  # [시작 창 번호, 길이, 조표(♯ 수)]
    for index, sharps in enumerate(_smooth_signatures(window_keys)):
        if sharps is None:
            if runs:
                runs[-1][1] += 1
            continue
        if runs and runs[-1][2] == sharps:
            runs[-1][1] += 1
        else:
            runs.append([index, 1, sharps])

    changes: list[tuple[int, int]] = []  # (시작 창 번호, 조표)
    for start, length, sharps in runs:
        if length < MIN_KEY_RUN_WINDOWS or (changes and changes[-1][1] == sharps):
            continue
        changes.append((start if changes else 0, sharps))
    return [start for start, _ in changes]


def _build_metadata(info: ScoreInfo) -> metadata.Metadata:
    score_metadata = metadata.Metadata()
    score_metadata.title = info.title
    if info.composer:
        score_metadata.composer = info.composer
    if info.lyricist:
        score_metadata.lyricist = info.lyricist
    return score_metadata


def save_musicxml(score: stream.Score, output_path: str | Path) -> Path:
    """악보를 MusicXML 파일로 저장한다. 폴더가 없으면 만든다."""
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    written = score.write("musicxml", fp=str(path))
    return Path(written)


def _build_part(
    hand_notes: tuple[QuantizedNote, ...],
    part_clef: clef.Clef,
    time_signature: str,
    total_beats,
) -> stream.Part:
    part = stream.Part()
    part.insert(0, part_clef)
    part.insert(0, meter.TimeSignature(time_signature))
    if not hand_notes:
        part.insert(0, note.Rest(quarterLength=total_beats))
        return part

    for start, duration, group in _group_by_start(hand_notes):
        part.insert(start, _to_music21_element(group, duration))
    part.makeRests(fillGaps=True, inPlace=True)
    return part


def _group_by_start(hand_notes: tuple[QuantizedNote, ...]):
    """같은 박에 시작하는 음을 한 묶음(화음)으로 모은다.

    묶음의 길이는 다음 묶음이 시작할 때까지로 자른다. 음이 겹쳐 생기는
    잘게 쪼개진 붙임줄을 막아 악보를 깔끔하게 한다.
    """
    starts = sorted({n.start_beats for n in hand_notes})
    next_starts = starts[1:] + [None]
    for start, next_start in zip(starts, next_starts):
        group = tuple(n for n in hand_notes if n.start_beats == start)
        duration = max(n.duration_beats for n in group)
        if next_start is not None:
            duration = min(duration, next_start - start)
        yield start, duration, group


def _to_music21_element(group: tuple[QuantizedNote, ...], duration) -> note.NotRest:
    pitches = sorted({n.pitch for n in group})
    element = (
        note.Note(pitches[0], quarterLength=duration)
        if len(pitches) == 1
        else chord.Chord(pitches, quarterLength=duration)
    )
    element.volume.velocity = max(n.velocity for n in group)
    return element
