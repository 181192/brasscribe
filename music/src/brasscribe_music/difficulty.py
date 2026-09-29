"""Difficulty modes for an arrangement: faithful, standard, easier.

faithful  the arrangement as the arranger wrote it (no change).
standard  16th runs merged into 8ths where the harmony allows (the dropped
          note is not a chord tone), every part folded into its reading range.
easier    non-solo parts at most 8th-note rhythm (16th runs merged, keeping
          the chord tone), every part in its easy range (the reading range
          with the top EASY_TOP_TRIM semitones cut), and the solo's 16th runs
          merged too, keeping the notes that shape the contour (turning points).
Key changes are thinned for easier in the key plan (KEY_CHANGE_PENALTY).

All transforms run on the arranged parts (concert pitch, ticks), so they
apply to any lineup and to both arrangers.
"""

from __future__ import annotations

from dataclasses import replace

from .instruments import Part
from .score_model import Note
from .trills import collapse_trills

MODES = ("faithful", "standard", "easier")
EASY_TOP_TRIM = 4  # semitones taken off the top of the reading range
SIXTEENTH = 6
EIGHTH = 12
KEY_CHANGE_PENALTY = {"faithful": None, "standard": None, "easier": 1.0}  # None: the key plan's default
SOLO_PART = "Solo Cornet"  # the band lineups' lead; apply_difficulty reads lineup.lead


def easy_range(part: Part) -> tuple[int, int]:
    lo, hi = part.instrument.preferred
    return lo, max(lo + 12, hi - EASY_TOP_TRIM)


def mode_range(part: Part, mode: str) -> tuple[int, int]:
    """The range a mode keeps a part in: the easy range for easier, else the reading range."""
    return easy_range(part) if mode == "easier" else part.instrument.preferred


def _harmony_at(parts: dict[str, list[Note]], tick: int, exclude: str) -> set[int]:
    return {n.pitch % 12 for name, notes in parts.items() if name != exclude for n in notes
            if n.start <= tick < n.end and name != "Percussion"}


def _merge_sixteenths(notes: list[Note], chord_at, always: bool, keep_contour: bool = False) -> list[Note]:
    """Merge 16th pairs (onsets x and x+6 inside one 8th) into one 8th.

    The kept pitch: the turning point of the line when keep_contour, else the
    chord tone, else the first. Unless `always`, a pair is merged only when
    the dropped note is not a chord tone (a passing or neighbour note).
    """
    notes = sorted(notes, key=lambda n: n.start)
    out: list[Note] = []
    i = 0
    while i < len(notes):
        a = notes[i]
        b = notes[i + 1] if i + 1 < len(notes) else None
        pair = b is not None and a.start % EIGHTH == 0 and b.start == a.start + SIXTEENTH and a.dur <= SIXTEENTH
        if not pair:
            out.append(a)
            i += 1
            continue
        chord = chord_at(a.start)
        prev = out[-1].pitch if out else None
        nxt = notes[i + 2].pitch if i + 2 < len(notes) else None

        def turning(n: Note) -> bool:
            return prev is not None and nxt is not None and (n.pitch - prev) * (nxt - n.pitch) < 0

        if keep_contour and (turning(a) or turning(b)):
            keep, drop = (b, a) if turning(b) and not turning(a) else (a, b)
        elif a.pitch % 12 in chord or b.pitch % 12 not in chord:
            keep, drop = a, b
        else:
            keep, drop = b, a
        if not always and drop.pitch % 12 in chord and drop.pitch % 12 != keep.pitch % 12:
            out.append(a)
            i += 1
            continue
        end = max(a.end, b.end, a.start + EIGHTH)
        out.append(replace(keep, start=a.start, dur=end - a.start, sources=list(keep.sources),
                           articulations=list(keep.articulations)))
        i += 2
    # A merged note never runs into the next onset.
    for x, y in zip(out, out[1:]):
        if x.end > y.start:
            x.dur = y.start - x.start
    return out


def _min_eighth(notes: list[Note]) -> list[Note]:
    """Every note at least an 8th long and on the 8th grid (merging notes that land on one 8th)."""
    by_slot: dict[int, Note] = {}
    for n in sorted(notes, key=lambda n: n.start):
        slot = (n.start // EIGHTH) * EIGHTH
        if slot not in by_slot:
            by_slot[slot] = replace(n, start=slot, dur=max(EIGHTH, n.end - slot), sources=list(n.sources),
                                    articulations=list(n.articulations))
    out = [by_slot[s] for s in sorted(by_slot)]
    for x, y in zip(out, out[1:]):
        if x.end > y.start:
            x.dur = y.start - x.start
    return out


def _fold(notes: list[Note], lo: int, hi: int) -> list[Note]:
    """Octave-fold notes outside [lo, hi] to the octave inside it nearest the previous note."""
    out, prev = [], None
    for n in sorted(notes, key=lambda n: n.start):
        p = n.pitch
        if not lo <= p <= hi:
            opts = [p % 12 + 12 * k for k in range(11) if lo <= p % 12 + 12 * k <= hi]
            if opts:
                p = min(opts, key=lambda x: (abs(x - (prev if prev is not None else (lo + hi) / 2)), x))
        out.append(replace(n, pitch=p, sources=list(n.sources), articulations=list(n.articulations)))
        prev = p
    return out


def trills_default(mode: str) -> bool:
    """Trill notation by default: at standard and easier; faithful writes alternations out unless asked."""
    return mode != "faithful"


def apply_difficulty(parts: dict[str, list[Note]], lineup, mode: str,
                     only: tuple[str, ...] | None = None, trills: bool | None = None) -> dict[str, list[Note]]:
    """Parts rewritten for a difficulty mode (faithful returns them unchanged, unless `trills`).

    `trills` (default: trills_default) writes sustained two-note alternations as trills (trills.collapse_trills),
    before the 16th merges. With `only`, just those parts are rewritten; every entry of `parts` (also one that is
    not a part of the lineup) still counts for the harmony the 16th merges read.
    """
    if mode not in MODES:
        raise ValueError(f"difficulty must be one of {MODES}")
    if trills is None:
        trills = trills_default(mode)
    if mode == "faithful" and not trills:
        return parts
    out = dict(parts)
    for part in lineup.parts:
        name = part.name
        if only is not None and name not in only:
            continue
        notes = parts.get(name, [])
        if not notes or part.instrument.clef == "percussion":
            continue
        if trills:
            notes = collapse_trills(notes)
            if mode == "faithful":
                out[name] = notes
                continue

        def chord_at(t: int, name=name) -> set[int]:
            return _harmony_at(parts, t, name)

        solo = name == lineup.lead
        # Four-part lineups voice their inner parts straight into the mode's range (arranger.voice_satb);
        # folding one of them on its own could cross it over its neighbour.
        fold = not (lineup.satb and name not in (lineup.lead, lineup.bass))
        if mode == "standard":
            notes = _merge_sixteenths(notes, chord_at, always=False)
            if fold:
                notes = _fold(notes, *part.instrument.preferred)
        else:
            notes = _merge_sixteenths(notes, chord_at, always=True, keep_contour=solo)
            if not solo:
                notes = _min_eighth(notes)
            if fold:
                notes = _fold(notes, *easy_range(part))
        out[name] = notes
    return out
