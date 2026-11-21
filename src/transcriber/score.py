"""박자 정리된 음으로 피아노 악보(MusicXML)를 만드는 모듈. music21을 사용한다."""

import math
from collections import Counter
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from music21 import (
    bar,
    chord,
    clef,
    dynamics,
    expressions,
    instrument,
    key,
    layout,
    metadata,
    meter,
    note,
    pitch,
    stream,
    tempo,
)

from transcriber.lyrics import attach_lyrics
from transcriber.rhythm import QuantizedNote
from transcriber.meters import (
    TimeSignatureChange,
    bar_length,
    measure_number_at,
    normalize_changes,
    parse_time_signature,
)
from transcriber.dynamics_marks import DynamicMark, plan_dynamics
from transcriber.engraving import place_marks
from transcriber.page_layout import apply_page_layout
from transcriber.pedals import PedalSpan, attach_pedals
from transcriber.spelling import respell_part
from transcriber.tempo_marks import TempoChange, TempoMark, plan_tempo_marks
from transcriber.voices import VoicedChord, split_voices

MIDDLE_C = 60  # 가운데 도. 이 음 이상은 오른손(높은음자리표), 아래는 왼손(낮은음자리표)
KEY_WINDOW_MEASURES = 4  # 조성을 이 마디 수씩 끊어서 찾는다
MIN_KEY_RUN_WINDOWS = 3  # 같은 조표가 3창(12마디) 이상 이어져야 조바꿈으로 인정
MIN_NOTES_FOR_KEY = 8  # 한 창에 음이 이보다 적으면 조성을 판단하지 않는다
KEY_FIT_TOLERANCE = 0.01  # 가장 잘 맞는 위치와 1% 안쪽 차이면 "거의 똑같이 잘 맞음"


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
    time_signature: str | None = None  # 예: "3/4". 정하면 곡 전체에 이 박자표 하나를 쓴다
    measures_per_line: int = 4  # 한 줄에 그릴 마디 수


def build_score(
    notes: tuple[QuantizedNote, ...],
    tempo_bpm: float,
    info: ScoreInfo = ScoreInfo(),
    time_signatures: tuple[TimeSignatureChange, ...] = (),
    melody: tuple[QuantizedNote, ...] = (),
    tempo_changes: tuple[TempoChange, ...] = (),
    pedals: tuple[PedalSpan, ...] = (),
    allow_voices: bool = False,
) -> stream.Score:
    """피아노 2단(오른손/왼손) 악보를 만든다. melody가 있으면 맨 위에 멜로디 단을 더한다.

    info.lyrics(음절 목록)가 있으면 멜로디 음표에 차례로 붙인다.
    time_signatures가 없으면 4/4로 쓴다. info.time_signature를 정하면 그것을 쓴다.
    allow_voices=True면 피아노 단에서 길게 누른 음을 2성부로 따로 적는다(MIDI처럼 음 길이가 정확할 때).
    """
    if info.time_signature:
        time_signatures = (TimeSignatureChange(beat=Fraction(0), text=info.time_signature),)
    signatures = normalize_changes(time_signatures)
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

    # 피아노는 한 악기의 두 단(높은음자리표·낮은음자리표, 중괄호로 묶음)으로 만든다
    parts = [
        _build_part(right_hand, clef.TrebleClef(), signatures, total_beats, allow_voices, staff=True),
        _build_part(left_hand, clef.BassClef(), signatures, total_beats, allow_voices, staff=True),
    ]
    for piano_part in parts:
        piano_part.insert(0, instrument.Piano())
    # 페달 표시는 피아노 아래 단(왼손) 밑에 적는다. 왼손 음이 없으면 오른손에.
    attach_pedals(parts[1] if left_hand else parts[0], pedals)
    first_bar = bar_length(signatures[0].text)
    # 피아노 셈여림은 오른손 단에 한 번만 적는다(두 단에 같이 적용되는 관례)
    if notes:
        _attach_dynamics(parts[0] if right_hand else parts[1], plan_dynamics(notes, first_bar))
    if melody:
        melody_part = _build_part(melody, clef.TrebleClef(), signatures, total_beats)
        # 노래 멜로디는 합창 "아~" 소리(General MIDI 52번)로 연주한다
        melody_part.insert(0, instrument.Choir())
        melody_part.partName = "멜로디"
        attach_lyrics(melody_part, info.lyrics)
        _attach_dynamics(melody_part, plan_dynamics(melody, first_bar))
        parts.insert(0, melody_part)
    parts[0].insert(0, tempo.MetronomeMark(number=round(tempo_bpm)))
    # 조성·빠르기 판단은 첫 박자표의 마디 길이를 기준으로 한다(대부분의 곡은 박자표가 하나)
    bar_beats = first_bar
    for mark in plan_tempo_marks(tempo_changes, total_beats, bar_beats):
        if mark.kind == "fermata":
            # 피아노 낮은음자리표 단은 위 단과 2칸만 떨어져 있어 위에 둘 자리가 없으므로 빼고,
            # 멜로디와 피아노 위 단에만 위쪽으로 하나씩 붙인다
            for part in parts[:-1]:
                _attach_fermata(part, mark.beat, mark.end_beat)
            continue
        parts[0].insert(mark.beat, _tempo_element(mark))

    score = stream.Score()
    for part in parts:
        score.insert(0, part)
    treble_staff, bass_staff = parts[-2], parts[-1]
    score.insert(
        0,
        layout.StaffGroup(
            [treble_staff, bass_staff], name="Piano", abbreviation="Pno.", symbol="brace", barTogether=True
        ),
    )

    for start, song_key in _resolve_keys(notes + melody, bar_beats, info.key_name, melody):
        for part in score.parts:
            part.insert(start, key.Key(song_key.tonic, song_key.mode))
    for part in score.parts:
        respell_part(part)  # 가장조의 D♯처럼, 음 이름을 조에 맞게
    score.metadata = _build_metadata(info)
    return score


def _attach_dynamics(part: stream.Part, marks: tuple[DynamicMark, ...]) -> None:
    """셈여림 글자(pp~ff)와 크레셴도·디크레셴도를 파트에 넣는다. 소리 세기는 음마다 그대로 둔다."""
    notes = list(part.flatten().notes)
    for mark in marks:
        if mark.kind == "level":
            part.insert(mark.beat, dynamics.Dynamic(mark.text))
            continue
        covered = [n for n in notes if mark.beat <= n.offset < mark.end_beat]
        if covered:
            hairpin = dynamics.Crescendo if mark.kind == "crescendo" else dynamics.Diminuendo
            part.insert(0, hairpin(covered))


def _attach_fermata(part: stream.Part, start: Fraction, end: Fraction) -> None:
    """start~end 사이에 시작하는 음 중 마지막 음(곡 끝이면 마지막 음) 하나에 늘임표(𝄐)를 위쪽으로 붙인다."""
    candidates = [n for n in part.flatten().notes if start <= n.offset < end]
    if not candidates:
        return
    held = max(candidates, key=lambda n: n.offset)
    fermata = expressions.Fermata()
    fermata.type = "upright"  # 둥근 쪽이 위로 → 음표 위에 그린다
    held.expressions.append(fermata)


def _tempo_element(mark: TempoMark):
    """빠르기 표시를 악보 요소로 만든다. 숨은 빠르기는 소리만 바꾸고 눈에 보이지 않는다."""
    if mark.kind == "text":
        words = expressions.TextExpression(mark.text)
        words.style.fontStyle = "italic"
        return words
    if mark.kind == "shown":
        return tempo.MetronomeMark(number=round(mark.bpm))
    hidden = tempo.MetronomeMark()
    hidden.numberSounding = mark.bpm
    return hidden


def key_name_of(score: stream.Score) -> str:
    """악보의 조성과 조표를 설명한다.

    예: "G major, 조표 ♯ 1개" 또는 조가 바뀌면
    "G major, 조표 ♯ 1개 → 41마디부터 A major, 조표 ♯ 3개".
    """
    first_part = score.parts.first()
    keys = list(first_part.flatten().getElementsByClass(key.Key)) if first_part else []
    if not keys:
        return "알 수 없음"
    signatures = tuple(
        TimeSignatureChange(beat=Fraction(ts.offset), text=ts.ratioString)
        for ts in first_part.flatten().getElementsByClass(meter.TimeSignature)
    )
    descriptions = [_describe_key(keys[0])]
    for later in keys[1:]:
        measure = measure_number_at(later.offset, signatures)
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
    notes: tuple[QuantizedNote, ...],
    bar_beats,
    key_name: str | None,
    melody: tuple[QuantizedNote, ...] = (),
) -> list[tuple[Fraction, key.Key]]:
    """곡의 조성과, 중간에 조가 바뀌는 위치를 찾는다. [(시작 박, 조성), ...]

    곡을 4마디씩 잘라 조성을 찾고, 같은 조표가 12마디 이상 이어질 때만
    조바꿈으로 인정한다(잠깐 다른 조의 음이 나오는 것은 무시).
    """
    if key_name:
        return [(Fraction(0), _parse_key(key_name))]

    window = Fraction(bar_beats) * KEY_WINDOW_MEASURES
    total = max(n.start_beats + n.duration_beats for n in notes)
    phrase_starts = _phrase_starts(melody)
    window_count = math.ceil(total / window)
    window_keys = [
        _analyze_key(tuple(n for n in notes if i * window <= n.start_beats < (i + 1) * window))
        for i in range(window_count)
    ]
    change_windows = _stable_key_changes(window_keys)
    if not change_windows:
        return [(Fraction(0), _analyze_key(notes, min_notes=1))]

    rough = _keys_between([i * window for i in change_windows], notes, total)
    refined_starts = [Fraction(0)]
    for (_, old_key), (start, new_key) in zip(rough, rough[1:]):
        refined = _refine_change(notes, phrase_starts, old_key, new_key, start, Fraction(bar_beats))
        refined_starts.append(max(refined, refined_starts[-1] + Fraction(bar_beats)))
    return _keys_between(refined_starts, notes, total)


def _keys_between(starts: list, notes: tuple[QuantizedNote, ...], total) -> list:
    boundaries = list(starts) + [total + 1]
    return [
        (start, _analyze_key(tuple(n for n in notes if start <= n.start_beats < end), min_notes=1))
        for start, end in zip(boundaries, boundaries[1:])
    ]


def _refine_change(
    notes: tuple[QuantizedNote, ...],
    phrase_starts: frozenset,
    old_key: key.Key,
    new_key: key.Key,
    rough_start: Fraction,
    bar_beats: Fraction,
) -> Fraction:
    """4마디 단위로 찾은 조바꿈 위치를 마디 단위로 다듬는다.

    앞쪽 음은 옛 조에, 뒤쪽 음은 새 조에 가장 잘 맞는 마디를 고른다. 거의 똑같이
    잘 맞는 마디가 여럿이면(조바꿈 직전의 다리 마디들), 멜로디 프레이즈가 시작되는
    마디를, 없으면 가장 늦은 마디를 고른다. 새 조표는 새 단락 첫머리에 붙기 때문이다.
    """
    span = bar_beats * KEY_WINDOW_MEASURES
    candidates = [
        rough_start + bar_beats * step
        for step in range(-KEY_WINDOW_MEASURES, KEY_WINDOW_MEASURES + 1)
        if rough_start + bar_beats * step > 0
    ]
    nearby = tuple(n for n in notes if rough_start - 2 * span <= n.start_beats < rough_start + 2 * span)
    old_scale, new_scale = _scale_pitch_classes(old_key), _scale_pitch_classes(new_key)

    def fit(boundary: Fraction) -> Fraction:
        return sum(
            (n.duration_beats for n in nearby
             if (n.pitch % 12) in (old_scale if n.start_beats < boundary else new_scale)),
            Fraction(0),
        )

    scores = {c: fit(c) for c in candidates}
    best = max(scores.values())
    near_best = [c for c, s in scores.items() if s >= best * (1 - KEY_FIT_TOLERANCE)]
    at_phrase = [c for c in near_best if any(c <= p < c + bar_beats for p in phrase_starts)]
    return max(at_phrase or near_best)


def _scale_pitch_classes(song_key: key.Key) -> frozenset:
    return frozenset(p.pitchClass for p in song_key.getScale().getPitches())


def _phrase_starts(melody: tuple[QuantizedNote, ...]) -> frozenset:
    """멜로디가 쉼표(1박 이상) 뒤에 다시 시작하는 박들."""
    starts = []
    previous_end = None
    for n in sorted(melody, key=lambda n: n.start_beats):
        if previous_end is None or n.start_beats - previous_end >= 1:
            starts.append(n.start_beats)
        previous_end = max(previous_end or 0, n.start_beats + n.duration_beats)
    return frozenset(starts)


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


def save_musicxml(score: stream.Score, output_path: str | Path, measures_per_line: int = 4) -> Path:
    """악보를 MusicXML 파일로 저장한다. 폴더가 없으면 만든다.

    마디로 나눈 뒤, 조표나 박자표가 바뀌기 직전 마디 끝에 겹세로줄(‖)을 긋는다.
    measures_per_line: 한 줄에 그릴 마디 수(1 이상).
    """
    if measures_per_line < 1:
        raise ValueError(f"한 줄 마디 수는 1 이상이어야 합니다: {measures_per_line}")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    notated = score.makeNotation()
    for part in notated.parts:
        _add_double_barlines(part)
        _number_voices(part)
        _show_needed_accidentals(part)
    place_marks(notated)  # 기호가 겹치지 않게: 피아노 두 단 사이에는 두지 않는다
    written = Path(notated.write("musicxml", fp=str(path)))
    apply_page_layout(written, measures_per_line)  # 용지·줄 바꿈·마디 폭·단 간격
    return written


def _show_needed_accidentals(part: stream.Part) -> None:
    """임시표(♯ ♭ ♮)는 꼭 필요한 곳에만 보이게 한다.

    음마다 '지금 그 음(같은 이름·같은 옥타브)에 적용되는 값'과 비교한다.
    적용되는 값은 조표, 또는 같은 마디 앞에서 나온 임시표다. 다를 때만 표시한다.
    - 앞 마디의 임시표를 알려 주는 표시(친절 임시표)는 쓰지 않는다.
    - 다른 옥타브의 같은 음에는 영향을 주지 않는다.
    - 붙임줄로 이어지는 음에는 표시하지 않는다.
    """
    for measure in part.getElementsByClass(stream.Measure):
        # 이 마디 맨 앞의 조표(1마디, 조바꿈 마디), 없으면 앞에서 이어지는 조표
        signature = measure.keySignature or measure.getContextByClass(key.KeySignature)
        from_signature = {p.step: p.alter for p in signature.alteredPitches} if signature else {}
        in_effect: dict[tuple[str, int], float] = {}
        for element in sorted(measure.recurse().notes, key=lambda e: e.getOffsetInHierarchy(measure)):
            continues_tie = element.tie is not None and element.tie.type in ("continue", "stop")
            for p in element.pitches:
                position = (p.step, p.octave)
                expected = in_effect.get(position, from_signature.get(p.step, 0.0))
                in_effect[position] = p.alter
                needed = p.alter != expected and not continues_tie
                if needed and p.accidental is None:
                    p.accidental = pitch.Accidental("natural")
                if p.accidental is not None and p.alter == 0 and not needed:
                    p.accidental = None  # 필요 없는 제자리표는 아예 지운다
                elif p.accidental is not None:
                    p.accidental.displayStatus = needed


def _number_voices(part: stream.Part) -> None:
    """마디 안의 성부 번호를 1, 2로 맞춘다(music21은 0부터 매겨서 Finale 등이 헷갈릴 수 있음)."""
    for measure in part.getElementsByClass(stream.Measure):
        for number, voice in enumerate(measure.voices, start=1):
            voice.id = number


def _add_double_barlines(part: stream.Part) -> None:
    measures = list(part.getElementsByClass(stream.Measure))
    for previous, measure in zip(measures, measures[1:]):
        starts_new_section = any(
            element.offset == 0
            for element in measure.getElementsByClass((key.KeySignature, meter.TimeSignature))
        )
        if starts_new_section and previous.rightBarline is None:
            previous.rightBarline = bar.Barline("double")


def _build_part(
    hand_notes: tuple[QuantizedNote, ...],
    part_clef: clef.Clef,
    signatures: tuple[TimeSignatureChange, ...],
    total_beats,
    allow_voices: bool = False,
    staff: bool = False,
) -> stream.Part:
    # staff=True: 피아노처럼 여러 단으로 된 악기의 한 단(PartStaff)
    part = stream.PartStaff() if staff else stream.Part()
    part.insert(0, part_clef)
    for change in signatures:
        part.insert(change.beat, parse_time_signature(change.text))
    if not hand_notes:
        part.insert(0, note.Rest(quarterLength=total_beats))
        return part

    if allow_voices:
        upper, lower = split_voices(hand_notes)
        if lower:
            part.insert(0, _voice_stream("1", upper, lower, total_beats, hide_all_rests=False))
            part.insert(0, _voice_stream("2", lower, upper, total_beats, hide_all_rests=True))
            return part

    for start, duration, group in _group_by_start(hand_notes):
        part.insert(start, _to_music21_element(group, duration))
    part.makeRests(fillGaps=True, inPlace=True)
    return part


def _voice_stream(
    voice_id: str,
    chords: tuple[VoicedChord, ...],
    other: tuple[VoicedChord, ...],
    total_beats,
    hide_all_rests: bool,
) -> stream.Voice:
    """한 성부를 만든다. 빈 곳은 쉼표로 채우되, 다른 성부가 울리는 동안의 쉼표는 숨긴다."""
    voice = stream.Voice(id=voice_id)
    cursor = Fraction(0)
    for chord_ in chords:
        if chord_.start > cursor:
            voice.insert(cursor, _filler_rest(cursor, chord_.start, other, hide_all_rests))
        voice.insert(chord_.start, _to_music21_element(chord_.notes, chord_.duration))
        cursor = max(cursor, chord_.start + chord_.duration)
    if cursor < total_beats:
        voice.insert(cursor, _filler_rest(cursor, Fraction(total_beats), other, hide_all_rests))
    return voice


def _filler_rest(start, end, other: tuple[VoicedChord, ...], hide: bool) -> note.Rest:
    rest = note.Rest(quarterLength=end - start)
    other_sounding = any(c.start < end and c.start + c.duration > start for c in other)
    if hide or other_sounding:
        rest.style.hideObjectOnPrint = True
    return rest


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
    if len(pitches) > 1 and any(n.rolled for n in group):
        element.expressions.append(expressions.ArpeggioMark())  # 펼친 화음 ≀
    return element
