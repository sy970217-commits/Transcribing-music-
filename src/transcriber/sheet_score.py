"""분석표를 보고 피아노 악보를 만든다.

분석표에서 가져오는 것
- 박자표·빠르기·못갖춘마디(B), 음(D), 조(F), 페달(H)
- 가사 글을 줬으면 멜로디(I)를 맨 위 '멜로디' 단으로 따로 적고 가사를 붙인다.
  피아노 단에는 멜로디 음도 그대로 둔다(노래 악보에서 피아노가 멜로디를 같이 치는 것처럼).
아직 안 가져오는 것: 셈여림(H)·화음 기호(E)·조바꿈(F 두 번째 조부터)·구조(G). 이것들은 악보 코드가 따로 계산한다.
"""

from dataclasses import replace
from fractions import Fraction

from music21 import stream

from transcriber.analysis.sheet import AnalysisSheet
from transcriber.analysis.tonality import MAJOR_NAMES, MINOR_NAMES, KeySegment
from transcriber.lyrics import HOLD
from transcriber.meters import TimeSignatureChange
from transcriber.pedals import PedalSpan
from transcriber.rhythm import QuantizedNote
from transcriber.score import ScoreInfo, build_score

DEFAULT_VELOCITY = 80


def pickup_shift(sheet: AnalysisSheet) -> Fraction:
    """못갖춘마디가 있으면 첫 마디를 쉼표로 채워 온마디로 만든다. 모든 위치를 이만큼 뒤로 민다."""
    beats = sheet.beats
    if beats.pickup_beats <= 0:
        return Fraction(0)
    return (beats.beats_per_bar - beats.pickup_beats) * sheet.rhythm.beat_quarters


def key_name_of(segment: KeySegment) -> str:
    """분석표의 조 → 악보용 조 이름. 예: Bb 장조 → "B-", 올림다 단조 → "c#"."""
    if segment.mode == "minor":
        name = MINOR_NAMES[segment.tonic].lower()
    else:
        name = MAJOR_NAMES[segment.tonic]
    return name[0] + name[1:].replace("b", "-")


def melody_part_of(sheet: AnalysisSheet, shift: Fraction) -> tuple[tuple[QuantizedNote, ...], tuple[str, ...]]:
    """멜로디 음과 음절들. 가사가 하나도 없고 목소리도 따로 나누지 않았으면 멜로디 단을 만들지 않는다.

    (섞인 소리에서 고른 멜로디는 틀리기 쉽지만, 나눈 목소리 트랙의 멜로디는 가사가 없어도 따로 적을 만하다.)
    """
    notes = sheet.melody.notes
    no_lyrics = all(n.lyric is None for n in notes)
    if no_lyrics and sheet.accompaniment is None:
        return (), ()
    loudness = {(n.start, n.pitch): n.velocity for n in sheet.rhythm.notes}
    melody = tuple(
        QuantizedNote(n.pitch, loudness.get((n.start, n.pitch), DEFAULT_VELOCITY), n.start + shift, n.length)
        for n in notes
    )
    lyrics = () if no_lyrics else tuple(HOLD if n.lyric is None else n.lyric for n in notes)
    return melody, lyrics


def score_from_sheet(sheet: AnalysisSheet, info: ScoreInfo = ScoreInfo()) -> stream.Score:
    shift = pickup_shift(sheet)
    melody, lyrics = melody_part_of(sheet, shift)
    # 멜로디 단이 있고 목소리를 따로 나눴으면, 피아노 단에는 목소리를 뺀 반주만 적는다(멜로디가 두 번 적히지 않게)
    backing = sheet.accompaniment if melody and sheet.accompaniment is not None else sheet.rhythm
    piano = tuple(QuantizedNote(n.pitch, n.velocity, n.start + shift, n.length) for n in backing.notes)
    if info.key_name is None and sheet.key.keys:
        info = replace(info, key_name=key_name_of(sheet.key.keys[0]))
    if lyrics:
        info = replace(info, lyrics=lyrics)
    return build_score(
        piano,
        sheet.beats.tempo_bpm * float(sheet.rhythm.beat_quarters),  # 악보 빠르기는 4분음표 기준
        info,
        time_signatures=(TimeSignatureChange(Fraction(0), sheet.rhythm.time_signature),),
        melody=melody,
        pedals=tuple(PedalSpan(p.start + shift, p.end + shift) for p in sheet.expression.pedals),
    )
