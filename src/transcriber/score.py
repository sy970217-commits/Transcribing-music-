"""박자 정리된 음으로 피아노 악보(MusicXML)를 만드는 모듈. music21을 사용한다."""

from dataclasses import dataclass
from pathlib import Path

from music21 import chord, clef, key, metadata, meter, note, stream, tempo

from transcriber.rhythm import QuantizedNote

MIDDLE_C = 60  # 가운데 도. 이 음 이상은 오른손(높은음자리표), 아래는 왼손(낮은음자리표)
DEFAULT_TIME_SIGNATURE = "4/4"


@dataclass(frozen=True)
class ScoreInfo:
    """악보 맨 위에 적을 정보와 조성.

    key_name 예: "G"(사장조), "e"(마단조, 소문자=단조). 비워 두면 자동으로 찾는다.
    """

    title: str = ""
    composer: str = ""
    lyricist: str = ""
    key_name: str | None = None


def build_score(
    notes: tuple[QuantizedNote, ...],
    tempo_bpm: float,
    info: ScoreInfo = ScoreInfo(),
    time_signature: str = DEFAULT_TIME_SIGNATURE,
    melody: tuple[QuantizedNote, ...] = (),
) -> stream.Score:
    """피아노 2단(오른손/왼손) 악보를 만든다. melody가 있으면 맨 위에 멜로디 단을 더한다."""
    if not notes and not melody:
        raise ValueError("악보로 만들 음이 없습니다.")
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
        parts.insert(0, melody_part)
    parts[0].insert(0, tempo.MetronomeMark(number=round(tempo_bpm)))

    score = stream.Score()
    for part in parts:
        score.insert(0, part)

    song_key = _resolve_key(score, info.key_name)
    for part in score.parts:
        part.insert(0, key.Key(song_key.tonic, song_key.mode))
    score.metadata = _build_metadata(info)
    return score


def key_name_of(score: stream.Score) -> str:
    """악보의 조성과 조표를 설명한다. 예: "G major, 조표 ♯ 1개"."""
    song_key = score.recurse().getElementsByClass(key.Key).first()
    if song_key is None:
        return "알 수 없음"
    if song_key.sharps > 0:
        signature = f"♯ {song_key.sharps}개"
    elif song_key.sharps < 0:
        signature = f"♭ {-song_key.sharps}개"
    else:
        signature = "없음"
    return f"{song_key.name}, 조표 {signature}"


def _resolve_key(score: stream.Score, key_name: str | None) -> key.Key:
    if not key_name:
        return score.analyze("key")
    try:
        return key.Key(key_name)
    except Exception as error:
        raise ValueError(f"알 수 없는 조성입니다: {key_name} (예: G, D, e)") from error


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
