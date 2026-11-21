"""음 이름(철자)을 조성에 맞게 고르는 모듈.

같은 소리라도 조에 따라 이름이 다르다. 가장조에서는 D♯, 내림마장조에서는 E♭로 쓴다.
- 그 조의 음계에 있는 음이면 음계의 이름을 쓴다(단조는 이끎음·올린 6음도 포함).
- 음계 밖의 음은 화성에서 하는 역할로 이름을 정한다(으뜸음에서 몇 반음 위인지로 판단).
  장조: ♯1, ♯4는 올린 음(이끎음 역할), ♭3, ♭6, ♭7은 내린 음(단조에서 빌려 온 음)
  단조: ♭2는 내린 음(나폴리 화음), ♮3, ♯4는 올린 음
  예: 사장조의 E♭(♭6), 사장조의 G♯(♯1), 가장조의 D♯(♯4)
"""

from music21 import key, pitch, scale, stream

RAISE, LOWER = 1, -1
# 으뜸음에서 몇 반음 위인지 → 올린 음으로 쓸지, 내린 음으로 쓸지
CHROMATIC_ROLE = {
    "major": {1: RAISE, 3: LOWER, 6: RAISE, 8: LOWER, 10: LOWER},
    "minor": {1: LOWER, 4: RAISE, 6: RAISE},
}
SEMITONES_PER_OCTAVE = 12


def respell_part(part: stream.Part) -> None:
    """파트의 모든 음 이름을 그 위치의 조성에 맞게 바꾼다. 소리(높이)는 바뀌지 않는다."""
    keys = sorted(part.flatten().getElementsByClass(key.Key), key=lambda k: k.offset)
    if not keys:
        return
    for element in part.flatten().notes:
        active = _key_at(keys, element.offset)
        for p in element.pitches:
            _respell(p, active)


def spell(midi_number: int, song_key: key.Key) -> pitch.Pitch:
    """MIDI 번호의 음을 조에 맞는 이름으로 만든다."""
    p = pitch.Pitch(midi=midi_number)
    _respell(p, song_key)
    return p


def _respell(p: pitch.Pitch, song_key: key.Key) -> None:
    candidates = [p, p.getEnharmonic(), p.getLowerEnharmonic(), p.getHigherEnharmonic()]
    in_scale = _scale_names(song_key)
    chosen = next((c for c in candidates if c.name in in_scale), None)
    if chosen is None:
        chosen = _chromatic_spelling(p, song_key) or p
    if chosen.nameWithOctave != p.nameWithOctave:
        p.step, p.octave = chosen.step, chosen.octave
        p.accidental = chosen.accidental


def _chromatic_spelling(p: pitch.Pitch, song_key: key.Key) -> pitch.Pitch | None:
    """음계 밖의 음을 역할(올린 음/내린 음)에 맞게, 이웃한 음계 음을 바꿔 이름 짓는다."""
    offset = (p.midi - song_key.tonic.pitchClass) % SEMITONES_PER_OCTAVE
    role = CHROMATIC_ROLE.get(song_key.mode, {}).get(offset)
    if role is None:
        return None
    neighbor_class = (p.midi - role) % SEMITONES_PER_OCTAVE  # 올린 음이면 반음 아래 음계 음
    natural_scale = song_key.getScale(song_key.mode).getPitches()
    neighbor = next((s for s in natural_scale if s.pitchClass == neighbor_class), None)
    if neighbor is None:
        return None
    spelled = neighbor.transpose("A1" if role == RAISE else "-A1")
    for octave in (p.octave - 1, p.octave, p.octave + 1):
        candidate = pitch.Pitch(spelled.name, octave=octave)
        if candidate.midi == p.midi:
            return candidate
    return None


def _scale_names(song_key: key.Key) -> frozenset[str]:
    names = {p.name for p in song_key.getScale().getPitches()}
    if song_key.mode == "minor":
        tonic = song_key.tonic
        for minor_scale in (scale.HarmonicMinorScale(tonic), scale.MelodicMinorScale(tonic)):
            names.update(p.name for p in minor_scale.getPitches())  # 기본값: 올라가는 음계
    return frozenset(names)


def _key_at(keys: list[key.Key], offset) -> key.Key:
    active = keys[0]
    for candidate in keys:
        if candidate.offset <= offset:
            active = candidate
    return active
