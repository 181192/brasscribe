"""Dynamics per layer from its loudness.

Each layer's level per bar (mean power in dB relative to the layer's loud
reference, energy.Envelope) is mapped to a marking, smoothed over three bars,
and a new marking is only written when it holds for `MIN_HOLD` bars, so the
parts get a few structural dynamics rather than one per bar. Levels are
relative to the layer itself: the loudest passages of the solo are f/ff
whatever the mix does, the orchestra's own quiet passages are p.
"""

from __future__ import annotations

import numpy as np

from .energy import Envelope

# Upper edge (dB relative to the layer's loud level) of each marking, softest first.
MARKS = [("pp", -30.0), ("p", -22.0), ("mp", -15.0), ("mf", -9.0), ("f", -4.0), ("ff", 99.0)]
MIN_HOLD = 4  # bars
SILENT_DB = -45.0  # a bar this quiet has no dynamic of its own (the layer rests)


def mark_of(level_db: float) -> str:
    return next(m for m, hi in MARKS if level_db < hi)


def layer_dynamics(env: Envelope, bars: list[tuple[int, float, float]]) -> list[tuple[int, str]]:
    """(tick, marking) changes for one layer; `bars` is (start tick, start s, end s) per bar."""
    levels = np.array([env.mean_level(t0, t1) for _, t0, t1 in bars])
    active = levels > SILENT_DB
    marks: list[str | None] = []
    for i in range(len(bars)):
        win = [levels[j] for j in range(max(0, i - 1), min(len(bars), i + 2)) if active[j]]
        marks.append(mark_of(float(np.median(win))) if active[i] and win else None)
    out: list[tuple[int, str]] = []
    current = None
    i = 0
    while i < len(bars):
        m = marks[i]
        if m is None or m == current:
            i += 1
            continue
        run = 1
        while i + run < len(bars) and marks[i + run] in (m, None):
            run += 1
        if current is None or run >= MIN_HOLD:
            out.append((bars[i][0], m))
            current = m
        i += 1
    return out
