"""Pitch spelling and key estimation on concert-pitch notes.

Spelling runs on the whole ensemble at concert pitch, before any part is
transposed, so every part is spelled from the same harmonic context.
"""

from __future__ import annotations

import numpy as np
from partitura.musicanalysis import estimate_key, estimate_spelling

STEPS = "CDEFGAB"
_FIELDS = [("onset_beat", "f4"), ("duration_beat", "f4"), ("onset_quarter", "f4"), ("duration_quarter", "f4"),
           ("pitch", "i4"), ("voice", "i4"), ("id", "U16")]


def _note_array(onsets_beats: list[float], durations_beats: list[float], pitches: list[int]) -> np.ndarray:
    arr = np.zeros(len(pitches), dtype=_FIELDS)
    arr["onset_beat"] = arr["onset_quarter"] = onsets_beats
    arr["duration_beat"] = arr["duration_quarter"] = np.maximum(durations_beats, 1e-3)
    arr["pitch"] = pitches
    arr["voice"] = 1
    arr["id"] = [f"n{i}" for i in range(len(pitches))]
    return arr


def spell(onsets_beats: list[float], durations_beats: list[float], pitches: list[int]) -> list[tuple[str, int, int]]:
    """Return (step, alter, octave) per note, in input order."""
    if not pitches:
        return []
    order = np.argsort(onsets_beats, kind="stable")
    arr = _note_array(list(np.asarray(onsets_beats)[order]), list(np.asarray(durations_beats)[order]),
                      list(np.asarray(pitches)[order]))
    sp = estimate_spelling(arr)
    out: list[tuple[str, int, int]] = [("C", 0, 4)] * len(pitches)
    for k, i in enumerate(order):
        out[i] = _simplify(str(sp["step"][k]), int(sp["alter"][k]), int(sp["octave"][k]), int(pitches[i]))
    return out


_NATURAL = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def _simplify(step: str, alter: int, octave: int, midi: int) -> tuple[str, int, int]:
    """Rewrite double sharps/flats (ps13 emits them in dense chromatic runs) as a single accidental."""
    if abs(alter) < 2:
        return step, alter, octave
    pc = midi % 12
    same_side = 1 if alter > 0 else -1
    for a in (same_side, 0, -same_side):
        for st, base in _NATURAL.items():
            if (base + a) % 12 == pc:
                return st, a, (midi - a) // 12 - 1
    return step, alter, octave


def key_of(onsets_beats: list[float], durations_beats: list[float], pitches: list[int]) -> tuple[str, int]:
    """Estimate (tonic+mode like 'F' or 'Dm', fifths) with Krumhansl-Kessler profiles."""
    arr = _note_array(onsets_beats, durations_beats, pitches)
    name = estimate_key(arr)
    return name, _fifths(name)


def _fifths(name: str) -> int:
    major = {"C": 0, "G": 1, "D": 2, "A": 3, "E": 4, "B": 5, "F#": 6, "C#": 7, "F": -1, "Bb": -2, "Eb": -3,
             "Ab": -4, "Db": -5, "Gb": -6, "Cb": -7}
    if name.endswith("m"):
        # G#, D# and A# minor: `major` has no G#, D# or A# (they are Ab, Eb and Bb there).
        return _SHARP_MINOR.get(name[:-1], major.get(name[:-1], 0) - 3)
    return major.get(name, 0)


_SHARP_MINOR = {"G#": 5, "D#": 6, "A#": 7}


def name(step: str, alter: int, octave: int) -> str:
    return f"{step}{'#' * alter if alter > 0 else 'b' * -alter}{octave}"
