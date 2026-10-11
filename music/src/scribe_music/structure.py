"""Rehearsal marks at section boundaries, from changes in the layers' energy.

Each bar gets a feature vector: the level of every layer (solo, orchestra,
bass, drums; dB relative to the layer's loud level, silence floored). A
section boundary is where the mean of the next `SPAN` bars differs most from
the mean of the previous `SPAN` bars (a layer enters or stops, the band gets
louder or softer). Boundaries are picked greedily by that novelty, at least
`MIN_GAP` bars apart, and a gap longer than `MAX_GAP` bars gets its best
boundary as well, so a conductor always has a letter nearby. The end of a
free-time passage ("a tempo") is always a boundary. Letters run A, B, C...
"""

from __future__ import annotations

import string

import numpy as np

from .energy import Envelope

SPAN = 4  # bars on each side
MIN_GAP = 8
MAX_GAP = 24
FLOOR_DB = -45.0
MIN_NOVELTY = 6.0  # dB (Euclidean over layers): smaller changes are not a new section


def bar_features(envs: list[Envelope], bars: list[tuple[int, float, float]]) -> np.ndarray:
    return np.array([[max(FLOOR_DB, e.mean_level(t0, t1)) for e in envs] for _, t0, t1 in bars])


def novelty(features: np.ndarray, span: int = SPAN) -> np.ndarray:
    n = len(features)
    out = np.zeros(n)
    for b in range(span, n - span + 1):
        out[b] = float(np.linalg.norm(features[b:b + span].mean(axis=0) - features[b - span:b].mean(axis=0)))
    return out


def section_starts(features: np.ndarray, forced: list[int] | None = None) -> list[int]:
    """Bar indices where rehearsal marks go (sorted; bar 0 is the start and gets none)."""
    nov = novelty(features)
    n = len(nov)
    chosen = sorted({b for b in (forced or []) if 0 < b < n})

    def free(b: int) -> bool:
        return all(abs(b - c) >= MIN_GAP for c in chosen) and b >= MIN_GAP // 2 and b <= n - MIN_GAP // 2

    for b in np.argsort(-nov):
        if nov[b] < MIN_NOVELTY:
            break
        if free(int(b)):
            chosen.append(int(b))
            chosen.sort()
    # Fill long stretches without a letter with their most novel bar.
    changed = True
    while changed:
        changed = False
        edges = [0] + sorted(chosen) + [n]
        for a, z in zip(edges, edges[1:]):
            inner = range(a + MIN_GAP, z - MIN_GAP + 1)
            if z - a > MAX_GAP and len(inner):
                chosen.append(max(inner, key=lambda b: nov[b]))
                changed = True
                break
    return sorted(set(chosen))


def letters(n: int) -> list[str]:
    abc = string.ascii_uppercase.replace("I", "")  # no I: it reads like 1
    return [abc[i] if i < len(abc) else abc[i // len(abc) - 1] + abc[i % len(abc)] for i in range(n)]
