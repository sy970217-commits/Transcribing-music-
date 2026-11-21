"""아르페지오(펼친 화음 ≀)를 찾는 모듈.

아르페지오는 화음을 아래에서 위로 아주 빠르게 하나씩 눌러 울린다. MIDI에서는
음들이 조금씩 늦게 시작하면서 모두 함께 계속 울리는 모양으로 나타난다.
찾은 음들은 시작을 첫 음에 맞춰 한 화음으로 만들고, rolled=True로 표시한다.
"""

from dataclasses import replace

ROLL_MIN_STEPS = 3  # 서로 다른 시작 시간이 3개 이상이어야 아르페지오로 본다
ROLL_MIN_GAP = 0.04  # 박. 이보다 가까우면 그냥 동시에 친 것
ROLL_MAX_GAP = 0.3  # 박. 이보다 멀면 펼친 화음이 아니라 따로 친 음(셋잇단음표 간격 0.33보다 좁게)
ROLL_MAX_SPREAD = 0.75  # 박. 첫 음부터 마지막 음까지 이 안에 다 울려야 한다
ROLL_LOWEST_RANGE = 12  # 첫 시작의 음 중, 다음 음에서 한 옥타브 안쪽의 음만 아르페지오에 넣는다


def mark_rolled_chords(notes: tuple) -> tuple:
    """아르페지오로 친 음들을 찾아 시작을 맞추고 rolled=True로 바꾼 새 음 목록을 돌려준다."""
    starts = sorted({n.start_beats for n in notes})
    rolled_ids: dict[int, float] = {}
    index = 0
    while index < len(starts):
        steps = _chain_from(starts, index)
        if len(steps) >= ROLL_MIN_STEPS:
            rolled_ids.update(_roll_members(notes, steps))
        index += max(1, len(steps))
    return tuple(
        replace(n, start_beats=rolled_ids[id(n)], rolled=True) if id(n) in rolled_ids else n
        for n in notes
    )


def _chain_from(starts: list[float], index: int) -> list[float]:
    """index부터, 간격이 아르페지오처럼 촘촘하게 이어지는 시작 시간들."""
    chain = [starts[index]]
    for following in starts[index + 1 :]:
        gap = following - chain[-1]
        if not (ROLL_MIN_GAP <= gap <= ROLL_MAX_GAP) or following - chain[0] > ROLL_MAX_SPREAD:
            break
        chain.append(following)
    return chain


def _roll_members(notes: tuple, steps: list[float]) -> dict[int, float]:
    first, last = steps[0], steps[-1]
    later = [n for n in notes if n.start_beats in steps[1:]]
    if not later:
        return {}
    lowest_later = min(n.pitch for n in later)
    opening = [n for n in notes if n.start_beats == first and n.pitch >= lowest_later - ROLL_LOWEST_RANGE]
    members = opening + later
    still_sounding = all(n.end_beats > last for n in members)
    ascending = all(
        max(n.pitch for n in members if n.start_beats == a) < min(n.pitch for n in members if n.start_beats == b)
        for a, b in zip(steps, steps[1:])
        if any(n.start_beats == a for n in members)
    )
    if not (opening and still_sounding and ascending):
        return {}
    return {id(n): first for n in members}
