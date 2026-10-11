"""Reduce dense accompaniment notes to a harmonic rhythm of pitch-class sets.

Transcribed accompaniment (strings, pads, piano) is noisy and rhythmically
busy. The arranger needs chords, not every figuration note: per beat, weight
each pitch class by sounding duration x confidence, keep the strongest few,
and merge consecutive beats with the same set into one harmony slot.
"""

from __future__ import annotations

from .quantize import TICKS_PER_BEAT
from .score_model import Note


def harmony_slots(notes: list[Note], end_tick: int, max_pcs: int = 4, rel_threshold: float = 0.35,
                  beat: int = TICKS_PER_BEAT) -> list[tuple[int, int, list[int]]]:
    """Return (start, end, pitch classes) slots covering [0, end_tick)."""
    slots: list[tuple[int, int, list[int]]] = []
    for t in range(0, end_tick, beat):
        w = [0.0] * 12
        for n in notes:
            overlap = min(n.end, t + beat) - max(n.start, t)
            if overlap > 0:
                w[n.pitch % 12] += overlap * n.confidence
        top = max(w)
        if top <= 0:
            pcs: list[int] = []
        else:
            ranked = sorted(range(12), key=lambda pc: -w[pc])
            pcs = sorted(pc for pc in ranked[:max_pcs] if w[pc] >= rel_threshold * top)
        if slots and slots[-1][2] == pcs and slots[-1][1] == t:
            slots[-1] = (slots[-1][0], t + beat, pcs)
        else:
            slots.append((t, t + beat, pcs))
    return [s for s in slots if s[2]]


def slots_to_notes(slots: list[tuple[int, int, list[int]]], confidence: float = 1.0) -> list[Note]:
    """One middle-register note per pitch class per slot (the arranger re-voices them anyway)."""
    return [Note(48 + pc, s, e - s, confidence, ["harmony"]) for s, e, pcs in slots for pc in pcs]
