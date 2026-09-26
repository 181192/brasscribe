"""Written durations and staccato from performed note lengths.

Two steps:

1. Where a note really ends. Transcribers end sustained notes early: the
   SwiftF0 adapter's note segmentation drops frames whose voicing confidence
   dips, which on a separated, reverberant solo stem leaves only the attack.
   `contour_offsets` follows the frame-level SwiftF0 contour instead: the note
   lasts while the contour stays on its pitch and loud enough, up to the next
   onset.

2. What to write. Per voice, a note is *held* (written until the next onset)
   when it was played for at least `LEGATO_RATIO` of the time to the next
   onset and the silence before that onset is at most `MAX_HELD_GAP`;
   otherwise it is *detached* and written as the readable value nearest its
   performed length, followed by a rest. Both thresholds were picked by a
   coarse sweep on the score-aligned URMP brass and ChoraleBricks notes
   (eval `duration_bench`); scores there write the full inter-onset interval
   for most notes played longer than half of it and almost never for shorter
   ones. A note whose performed length is under half its written length gets
   a staccato mark.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .quantize import TICKS_PER_BEAT, BeatMap, QNote

LEGATO_RATIO = 0.5
MAX_HELD_GAP = 18  # ticks (a dotted 8th): a longer silence is written as a rest
STACCATO_RATIO = 0.5
# Readable written lengths in ticks (24 per beat): 16th, triplet 8th, 8th, triplet quarter, dotted 8th,
# quarter, dotted quarter, half, dotted half, whole.
READABLE = (6, 8, 12, 16, 18, 24, 36, 48, 72, 96)

FRAME = 0.016  # SwiftF0 frame period (s)

# contour_offsets settings for a separated stem. Mega-53's solo stem keeps a sustained
# tone's pitch but pushes its level 40-75 dB under the attack (on Mikkel the mix shows the
# same notes held 1.5-2 s at a normal level), so the default level gate cuts them short.
SEPARATED_STEM = {"drop_db": 80.0, "floor_db": -115.0, "max_hole": 0.25}


@dataclass
class Contour:
    """Frame-level monophonic pitch track (SwiftF0 output)."""

    t: np.ndarray
    midi: np.ndarray  # fractional MIDI pitch; nan where no pitch
    loudness_db: np.ndarray

    @staticmethod
    def load(path: Path) -> Contour:
        d = np.load(path)
        hz = d["pitch_hz"].astype(float)
        with np.errstate(divide="ignore", invalid="ignore"):
            midi = np.where(hz > 0, 69 + 12 * np.log2(hz / 440.0), np.nan)
        return Contour(d["t"].astype(float), midi, d["loudness_db"].astype(float))


def contour_offsets(c: Contour, notes: list[tuple[float, int]], tol: float = 0.6, drop_db: float = 60.0,
                    floor_db: float = -100.0, max_hole: float = 0.1, attack: float = 0.12) -> list[float]:
    """End time of each (onset_s, pitch) note, following the contour.

    A frame belongs to the note when its pitch is within `tol` semitones of
    the note (octave errors of the tracker are folded) and its loudness is
    above both `floor_db` and the note's attack peak minus `drop_db`. Holes of
    up to `max_hole` seconds are bridged. A note never extends past the next
    onset in `notes` (which must be one voice, sorted by onset). Notes with no
    matching frame keep a single frame's length.
    """
    out = []
    onsets = [o for o, _ in notes]
    for i, (on, p) in enumerate(notes):
        limit = onsets[i + 1] if i + 1 < len(notes) else c.t[-1] + FRAME if len(c.t) else on
        a = int(np.searchsorted(c.t, on - FRAME / 2))
        b = int(np.searchsorted(c.t, limit - FRAME / 2))
        if b <= a:
            out.append(on + FRAME)
            continue
        m, db = c.midi[a:b], c.loudness_db[a:b]
        dev = np.abs(((m - p) + 6) % 12 - 6)  # octave-folded distance in semitones
        near = np.nan_to_num(dev, nan=99.0) <= tol
        head = near & (c.t[a:b] < on + attack)
        peak = float(db[head].max()) if head.any() else float(db[: max(1, int(attack / FRAME))].max())
        ok = near & (db >= max(floor_db, peak - drop_db))
        end = on + FRAME
        hole = 0.0
        for k in range(len(ok)):
            if ok[k]:
                end = c.t[a + k] + FRAME
                hole = 0.0
            else:
                hole += FRAME
                if hole > max_hole and end > on + FRAME:
                    break
                if hole > max_hole + attack:  # nothing found near the onset
                    break
        out.append(float(min(end, limit)))
    return out


@dataclass
class Written:
    dur: int  # written length in ticks
    performed: float  # performed length in ticks (unsnapped)
    staccato: bool


STUB_PENALTY = 0.35  # log-length units: prefer a slightly off length to a 16th tied over a beat


def _stub(start: int, end: int) -> bool:
    """The written note would cross a beat and end on a 16th tied from it."""
    return start // TICKS_PER_BEAT != (end - 1) // TICKS_PER_BEAT and end % TICKS_PER_BEAT in (6, 18) \
        and end % TICKS_PER_BEAT < end - start


def _readable(performed: float, room: int | None, start: int = 0) -> int:
    cands = [c for c in READABLE if room is None or c <= room]
    if room is not None and room not in cands and room <= READABLE[-1]:
        cands.append(room)
    if not cands:
        return max(1, room or 1)
    p = max(performed, 1.0)
    return min(cands, key=lambda c: (abs(np.log(c / p)) + STUB_PENALTY * _stub(start, start + c), -c))


def written_durations(notes: list[QNote], bm: BeatMap | None = None, legato_ratio: float = LEGATO_RATIO,
                      max_held_gap: float = MAX_HELD_GAP, staccato_ratio: float = STACCATO_RATIO,
                      hold_within: int = 0, min_detached: int = 0) -> list[Written]:
    """Written length and staccato flag per note of one voice (chords share an onset), in input order.

    Performed length comes from onset_s/offset_s through `bm` when given
    (unsnapped), else from the quantized start/end. `hold_within` (ticks)
    writes every note whose next onset is at most that far away up to it, so a
    detached 8th-note run reads as staccato 8ths instead of 16ths and 16th
    rests, and `min_detached` is the shortest value a detached note gets
    (an 8th with a staccato reads easier than a 16th and a rest). Both are
    part-writing choices: scores write either, and duration_bench measures
    the defaults (0).
    """
    if not notes:
        return []
    starts = sorted({q.start for q in notes})
    nxt = dict(zip(starts, starts[1:]))
    if bm is not None:
        on = bm.to_beats(np.array([q.onset_s for q in notes]))
        off = bm.to_beats(np.array([q.offset_s for q in notes]))
        perf = list(np.maximum(off - on, 0.0) * TICKS_PER_BEAT)
    else:
        perf = [float(q.end - q.start) for q in notes]
    out = []
    for q, p in zip(notes, perf):
        n = nxt.get(q.start)
        room = None if n is None else n - q.start
        if room is not None and (room <= hold_within or (p >= legato_ratio * room and room - p <= max_held_gap)):
            dur = room
        else:
            dur = _readable(p, room, q.start)
            if dur < min_detached:
                dur = min(min_detached, room) if room is not None else min_detached
        out.append(Written(int(dur), float(p), p < staccato_ratio * dur))
    return out


def apply_written(notes: list[QNote], bm: BeatMap | None = None, **kw) -> list[tuple[QNote, Written]]:
    """Set each note's end to its written length; returns (note, Written) pairs sorted by start."""
    notes = sorted(notes, key=lambda q: q.start)
    res = written_durations(notes, bm, **kw)
    for q, w in zip(notes, res):
        q.end = q.start + w.dur
    return list(zip(notes, res))
