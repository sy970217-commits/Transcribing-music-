"""박자 정리된 음으로 피아노 악보(MusicXML)를 만드는 모듈. music21을 사용한다."""

from dataclasses import dataclass
from pathlib import Path

from music21 import clef, key, metadata, meter, note, stream, tempo

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
) -> stream.Score:
    """음 목록으로 2단(오른손/왼손) 피아노 악보를 만든다."""
    if not notes:
        raise ValueError("악보로 만들 음이 없습니다.")
    if tempo_bpm <= 0:
        raise ValueError(f"템포는 0보다 커야 합니다: {tempo_bpm}")

    total_beats = max(n.start_beats + n.duration_beats for n in notes)
    right_hand = tuple(n for n in notes if n.pitch >= MIDDLE_C)
    left_hand = tuple(n for n in notes if n.pitch < MIDDLE_C)

    score = stream.Score()
    treble = _build_part(right_hand, clef.TrebleClef(), time_signature, total_beats)
    treble.insert(0, tempo.MetronomeMark(number=round(tempo_bpm)))
    score.insert(0, treble)
    score.insert(0, _build_part(left_hand, clef.BassClef(), time_signature, total_beats))

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
    raw = stream.Part()
    for quantized in hand_notes:
        raw.insert(quantized.start_beats, _to_music21_note(quantized))
    if not hand_notes:
        raw.insert(0, note.Rest(quarterLength=total_beats))

    # 같은 시간에 울리는 음을 화음으로 묶는다
    part = raw.chordify() if hand_notes else raw
    part.insert(0, part_clef)
    part.insert(0, meter.TimeSignature(time_signature))
    return part


def _to_music21_note(quantized: QuantizedNote) -> note.Note:
    music21_note = note.Note(quantized.pitch, quarterLength=quantized.duration_beats)
    music21_note.volume.velocity = quantized.velocity
    return music21_note
