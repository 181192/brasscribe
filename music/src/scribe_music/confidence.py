"""Calibrated note confidence and the review marks ("?") drawn from it.

A solo note's confidence is the probability that it is right (pitch and onset
match the score), estimated from:
  - which transcribers found it (SwiftF0, MuScriptor, Basic Pitch): the
    agreement class
  - how long it is (short blips are the typical false note)
  - how strongly the SwiftF0 contour supports it: mean voicing confidence of
    the frames near the note's pitch over its first 0.3 s
  - whether the solo was separated from a mix (a stem) or recorded alone
The model is a logistic regression fitted by eval/brasscribe_eval/confidence_bench.py
on notes with ground truth (Mega-53 solo stems of ChoraleBricks and Slakh
songs, and every URMP and ChoraleBricks single part) and stored in
calibration.json next to this file. The bench checks it on a held-out half.

Marks: a note is marked "?" when its probability of being wrong is at least
MARK_RISK, boxed when at least VERY_RISK. Neighbouring marked notes in one
bar (at most one unmarked note between them) form one review group with a
single mark.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np

CALIBRATION = Path(__file__).with_name("calibration.json")
SUPPORT_WINDOW = 0.3  # s of the note's start over which the contour's voicing is averaged
SUPPORT_TOL = 1.0  # semitones between the contour and the note's pitch

FEATURES = ("bias", "mus", "bp", "mus_bp", "log_dur", "support", "no_contour", "separated",
            "sep_support", "sep_voted")


@dataclass
class Model:
    weights: dict[str, float]
    mark_risk: float
    very_risk: float
    # Per input, the range seen in training ([5th, 95th] percentile): inputs are clamped to it, so a
    # recording unlike the training material (e.g. much shorter notes) is not extrapolated into certainty
    # or doom.
    ranges: dict[str, tuple[float, float]] | None = None

    @staticmethod
    def load(path: Path = CALIBRATION) -> Model:
        d = json.loads(path.read_text())
        return Model(d["weights"], d["mark_risk"], d["very_risk"],
                     {k: tuple(v) for k, v in d.get("ranges", {}).items()} or None)


def support(contour, onset: float, pitch: int) -> float | None:
    """Mean SwiftF0 voicing confidence near `pitch` over the note's first SUPPORT_WINDOW s (None: no contour)."""
    if contour is None:
        return None
    t = contour.t
    a, b = np.searchsorted(t, onset), np.searchsorted(t, onset + SUPPORT_WINDOW)
    if b <= a:
        return 0.0
    m = contour.midi[a:b]
    conf = contour.confidence[a:b] if getattr(contour, "confidence", None) is not None else np.ones(b - a)
    dev = np.abs(((m - pitch) + 6) % 12 - 6)
    near = np.nan_to_num(dev, nan=99.0) <= SUPPORT_TOL
    return float(np.mean(np.where(near, conf, 0.0)))


def features(sources: set[str], duration: float, sup: float | None, separated: bool = False) -> dict[str, float]:
    """Model inputs for one solo note. `separated`: the solo was separated from a mix (stem), not recorded alone."""
    mus, bp = float("mus" in sources), float("bp" in sources)
    return {"bias": 1.0, "mus": mus, "bp": bp, "mus_bp": mus * bp,
            "log_dur": math.log(max(duration, 0.02)), "support": sup if sup is not None else 0.0,
            "no_contour": 0.0 if sup is not None else 1.0, "separated": float(separated),
            "sep_support": float(separated) * (sup if sup is not None else 0.0),
            "sep_voted": float(separated) * max(mus, bp)}


CLAMPED = ("log_dur", "support", "sep_support")


def p_correct(x: dict[str, float], model: Model) -> float:
    if model.ranges:
        x = {k: min(max(v, model.ranges[k][0]), model.ranges[k][1]) if k in model.ranges else v for k, v in x.items()}
    z = sum(model.weights.get(k, 0.0) * v for k, v in x.items())
    return 1.0 / (1.0 + math.exp(-z))


# ---------------------------------------------------------------- review groups


@dataclass
class ReviewGroup:
    start: int  # tick of the first marked note
    end: int  # tick after the last marked note
    notes: int  # marked notes in the group
    very: bool  # any of them very unsure


PHRASE_BREAK = 24  # ticks (a beat) of silence between marked notes that ends a phrase
MAX_GROUP_BARS = 2  # a group spans at most this many bars


def review_groups(notes: list[tuple[int, int, float]], bar: int, mark_below: float, very_below: float,
                  max_gap_notes: int = 1) -> list[ReviewGroup]:
    """Group marked notes (start, end, confidence) of one voice for review.

    A marked note joins the previous group when at most `max_gap_notes`
    unmarked notes lie between them, no phrase break (a beat or more of
    silence) separates them, and the group stays within MAX_GROUP_BARS bars.
    Each group gets one mark and one review item ("bars 12-13, 6 notes").
    """
    notes = sorted(notes)
    groups: list[ReviewGroup] = []
    unmarked = 0  # unmarked notes since the last marked one
    phrase_break = False  # a beat or more of silence since the last marked note
    prev_end = None
    for s, e, c in notes:
        if prev_end is not None and s - prev_end >= PHRASE_BREAK:
            phrase_break = True
        if c < mark_below:
            g = groups[-1] if groups else None
            if g is not None and unmarked <= max_gap_notes and not phrase_break and \
                    s // bar - g.start // bar < MAX_GROUP_BARS:
                g.end, g.notes, g.very = max(g.end, e), g.notes + 1, g.very or c < very_below
            else:
                groups.append(ReviewGroup(s, e, 1, c < very_below))
            unmarked, phrase_break = 0, False
        else:
            unmarked += 1
        prev_end = max(prev_end, e) if prev_end is not None else e
    return groups
