"""Key signatures per passage: key changes where the music modulates, and the mode.

One key for a whole piece leaves modulating passages full of accidentals
(Mikkel: 6-10 per bar where it moves to A major). Here each bar gets a cost
per key signature, the share of its note duration outside that signature's
scale, and a Viterbi pass picks one signature per bar with a penalty per
change, so a change needs a sustained gain (a few bars of chromatic
neighbours do not modulate). The mode names the estimated tonic as a
degree of the signature's scale: a C-signature passage in F is F lydian.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

from .score_model import KeySig, Note

FIFTHS = range(-5, 6)
CHANGE_PENALTY = 0.5  # in bars of fully out-of-key music
MIN_BAR_WEIGHT = 1e-6

# Modes by the degree of the major scale their tonic sits on.
MODES = {0: "major", 2: "dorian", 4: "phrygian", 5: "lydian", 7: "mixolydian", 9: "minor", 11: "locrian"}


def scale(fifths: int) -> set[int]:
    tonic = (7 * fifths) % 12
    return {(tonic + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)}


def _bar_costs(notes: list[Note], bar: int, n_bars: int) -> np.ndarray:
    cost = np.zeros((n_bars, len(FIFTHS)))
    weights = [Counter() for _ in range(n_bars)]
    for n in notes:
        b = n.start // bar
        if 0 <= b < n_bars:
            weights[b][n.pitch % 12] += n.dur
    for b, w in enumerate(weights):
        total = sum(w.values())
        if total < MIN_BAR_WEIGHT:
            continue
        for j, f in enumerate(FIFTHS):
            sc = scale(f)
            cost[b, j] = sum(v for pc, v in w.items() if pc not in sc) / total
    return cost


_TONIC = {"C": 0, "C#": 1, "Db": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5, "F#": 6, "Gb": 6, "G": 7, "Ab": 8,
          "G#": 8, "A": 9, "Bb": 10, "A#": 10, "B": 11, "Cb": 11}


def _mode(notes: list[Note], fifths: int) -> tuple[str, int]:
    """(mode name, tonic pitch class): the Krumhansl-Kessler tonic, named as a mode of the signature's scale.

    E.g. a C-signature passage whose estimated key is F: F lydian.
    """
    from .spelling import key_of

    if not notes:
        return "major", (7 * fifths) % 12
    name, _ = key_of([n.start / 24 for n in notes], [n.dur / 24 for n in notes], [n.pitch for n in notes])
    tonic = _TONIC.get(name.rstrip("m"), 0)
    degree = (tonic - 7 * fifths) % 12
    if degree not in MODES:  # the tonic is not in the scale: keep the signature's own major/minor reading
        return ("minor", (7 * fifths + 9) % 12) if name.endswith("m") else ("major", (7 * fifths) % 12)
    return MODES[degree], tonic


@dataclass
class KeyPlan:
    keys: list[KeySig]
    per_bar: list[int]  # fifths per bar


def key_plan(notes: list[Note], bar: int, penalty: float = CHANGE_PENALTY, bass: list[Note] | None = None) -> KeyPlan:
    """Key signatures (at bar starts) for concert-pitch notes; tick 0 is a bar line."""
    notes = [n for n in notes if n.start >= 0]
    if not notes:
        return KeyPlan([KeySig(0, 0)], [])
    n_bars = max(n.start for n in notes) // bar + 1
    cost = _bar_costs(notes, bar, n_bars)
    # Prefer fewer sharps/flats on ties.
    cost += 1e-3 * np.abs(np.array(list(FIFTHS)))[None, :]
    k = len(FIFTHS)
    acc = cost[0].copy()
    back = np.zeros((n_bars, k), dtype=int)
    for b in range(1, n_bars):
        stay = acc
        move = acc.min() + penalty
        choose_move = move < stay
        back[b] = np.where(choose_move, int(acc.argmin()), np.arange(k))
        acc = np.minimum(stay, move) + cost[b]
    path = [int(acc.argmin())]
    for b in range(n_bars - 1, 0, -1):
        path.append(int(back[b, path[-1]]))
    path.reverse()
    per_bar = [FIFTHS[j] for j in path]
    keys = []
    for b, f in enumerate(per_bar):
        if not keys or keys[-1].fifths != f:
            seg_end = next((e for e in range(b, n_bars) if per_bar[e] != f), n_bars)
            seg = [n for n in notes + (bass or []) if b * bar <= n.start < seg_end * bar]
            mode, _ = _mode(seg, f)
            keys.append(KeySig(b * bar, f, mode))
    return KeyPlan(keys, per_bar)


# ---------------------------------------------------------------- transposition

_DEGREE = {m: d for d, m in MODES.items()}
_NAMES = {"C": 0, "B#": 0, "C#": 1, "Db": 1, "D": 2, "D#": 3, "Eb": 3, "E": 4, "Fb": 4, "F": 5, "E#": 5, "F#": 6,
          "Gb": 6, "G": 7, "G#": 8, "Ab": 8, "A": 9, "A#": 10, "Bb": 10, "B": 11, "Cb": 11}


def fifths_of_major(pc: int) -> int:
    """Key signature (-5..6 fifths) whose major tonic is pitch class `pc`."""
    return next(f for f in range(-5, 7) if (7 * f) % 12 == pc % 12)


def tonic_of(k: KeySig) -> int:
    return (7 * k.fifths + _DEGREE.get(k.mode, 0)) % 12


def transposed_key(k: KeySig, semitones: int) -> KeySig:
    """The same mode `semitones` higher: the signature follows the tonic."""
    major = (7 * k.fifths + semitones) % 12
    return KeySig(k.tick, fifths_of_major(major), k.mode)


def semitones_to(current: KeySig, target: str) -> int:
    """Semitones (-6..5) that move `current` to `target`.

    `target` is a tonic name with an optional "m" for minor (Bb, F#, Am) or
    FIFTHS[:MODE] (-2, -2:minor). Without a mode the current one is kept, so
    an F-lydian passage asked to go to Bb stays lydian.
    """
    t = target.strip()
    if t.lstrip("+-").split(":")[0].isdigit():
        f, _, mode = t.partition(":")
        mode = mode or current.mode
        tonic = (7 * int(f) + _DEGREE.get(mode, 0)) % 12
    else:
        minor = t.endswith("m") and t[:-1] in _NAMES
        tonic = _NAMES[t[:-1] if minor else t]
    n = (tonic - tonic_of(current)) % 12
    return n - 12 if n > 6 else n
