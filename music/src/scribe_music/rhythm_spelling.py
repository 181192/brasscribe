"""Split notes and rests into readable, tied values that show the beat.

Brass-band parts show every beat and the middle of a 4/4 bar. So a value is
written as one symbol only when:
  - it is shorter than a beat and stays inside one beat, or is an 8th or
    dotted 8th pushed over one beat (an anticipation, also over mid-bar), or
  - it is a beat or longer, starts on a beat, and does not cross the middle
    of the bar unless it starts on the downbeat, or
  - it is a quarter on the "and" of a beat (8th-quarter-8th) inside a half bar,
and it is a plain or single-dotted value (no double dots). Anything else is
split at the first boundary it crosses and tied. Tick sums are exact, so
every bar stays complete.
"""

from __future__ import annotations

from .quantize import TICKS_PER_BEAT

BEAT = TICKS_PER_BEAT
# Plain and single-dotted values in ticks: 32nd, 16th, dotted 16th, 8th, dotted 8th, quarter,
# dotted quarter, half, dotted half, whole; plus triplet 16th, 8th and quarter.
SINGLE = {3, 6, 9, 12, 18, 24, 36, 48, 72, 96}
TRIPLET = {4, 8, 16}


def _middle(bar: int) -> int | None:
    """The strong boundary inside a bar: beat 3 in 4/4 (none in 2/4 or 3/4)."""
    beats = bar // BEAT
    return bar // 2 if beats >= 4 and beats % 2 == 0 else None


def _ok(a: int, b: int, bar: int) -> bool:
    n = b - a
    if n not in SINGLE and n not in TRIPLET:
        return False
    if n < BEAT:
        if a // BEAT == (b - 1) // BEAT:
            return True
        # An anticipation (8th or dotted 8th pushed over one beat, "16th-8th-16th"): tying it into
        # a 16th stub reads worse than the syncopation it is.
        return n in (12, 18)
    if a % BEAT:
        # The one accepted syncopation: a quarter on the "and" (8th-quarter-8th), not over mid-bar.
        mid = _middle(bar)
        return n == BEAT and a % (BEAT // 2) == 0 and (mid is None or not a < mid < b)
    mid = _middle(bar)
    return mid is None or a == 0 or not a < mid < b


def _in_bar(a: int, b: int, bar: int) -> list[tuple[int, int]]:
    if _ok(a, b, bar):
        return [(a, b)]
    mid = _middle(bar)
    if mid is not None and a < mid < b and a != 0:
        return _in_bar(a, mid, bar) + _in_bar(mid, b, bar)
    if a % BEAT:
        nxt = (a // BEAT + 1) * BEAT
        if nxt < b:
            return _in_bar(a, nxt, bar) + _in_bar(nxt, b, bar)
        # Inside one beat but not a single value (e.g. 5 ticks): largest value that fits.
        for n in sorted(SINGLE | TRIPLET, reverse=True):
            if n < b - a:
                return _in_bar(a, a + n, bar) + _in_bar(a + n, b, bar)
        return [(a, b)]
    # On a beat: the longest allowed value from here, then the rest.
    for n in sorted(SINGLE, reverse=True):
        if n < b - a and _ok(a, a + n, bar):
            return [(a, a + n)] + _in_bar(a + n, b, bar)
    return [(a, b)]


def pieces(start: int, end: int, bar: int) -> list[tuple[int, int]]:
    """Readable (start, end) pieces of [start, end) in ticks from the first bar line."""
    out: list[tuple[int, int]] = []
    s = start
    while s < end:
        b0 = (s // bar) * bar
        e = min(end, b0 + bar)
        out += [(b0 + x, b0 + y) for x, y in _in_bar(s - b0, e - b0, bar)]
        s = e
    return out
