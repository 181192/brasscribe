"""Beat-grid quantization: note times in seconds -> positions in beats.

Times are warped onto the detected beat grid (piecewise linear between beats),
so tempo drift is absorbed before snapping. Each beat then picks the simplest
subdivision that explains the onsets falling in it; simpler grids get a smaller
penalty so a slightly late 8th note is not turned into a 16th-triplet.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

TICKS_PER_BEAT = 24

# Subdivisions per beat and their complexity penalty (in squared-beat units, per note).
# Tuned on ChoraleBricks (performed timing vs notated positions); lower values let
# early/late on-beat notes snap to 16ths or triplets. Revalidate on busier material.
GRIDS: dict[int, float] = {1: 0.0, 2: 0.01, 4: 0.03, 3: 0.06, 6: 0.12}


@dataclass
class QNote:
    pitch: int
    start: int  # ticks from beat 0
    end: int
    onset_s: float
    offset_s: float
    confidence: float = 1.0
    articulations: tuple[str, ...] = ()  # "staccato", "fermata" (see score_model.Articulation)


class BeatMap:
    """Monotonic mapping between seconds and fractional beat index."""

    def __init__(self, beat_times: np.ndarray):
        if len(beat_times) < 2:
            raise ValueError("need at least two beats")
        self.t = np.asarray(beat_times, dtype=float)
        self.b = np.arange(len(self.t), dtype=float)

    def to_beats(self, seconds: np.ndarray) -> np.ndarray:
        s = np.asarray(seconds, dtype=float)
        out = np.interp(s, self.t, self.b)
        head, tail = self.t[1] - self.t[0], self.t[-1] - self.t[-2]
        out = np.where(s < self.t[0], (s - self.t[0]) / head, out)
        return np.where(s > self.t[-1], self.b[-1] + (s - self.t[-1]) / tail, out)

    def to_seconds(self, beats: np.ndarray) -> np.ndarray:
        x = np.asarray(beats, dtype=float)
        out = np.interp(x, self.b, self.t)
        head, tail = self.t[1] - self.t[0], self.t[-1] - self.t[-2]
        out = np.where(x < 0, self.t[0] + x * head, out)
        return np.where(x > self.b[-1], self.t[-1] + (x - self.b[-1]) * tail, out)


def choose_level(beat_times: np.ndarray, onsets: np.ndarray) -> np.ndarray:
    """Double the beat grid when the tracker locked onto half notes.

    Beat trackers often pick the slower metrical level on slow material. When
    the detected tempo is slow and notes are dense relative to the beat, the
    notated beat is almost always twice as fast. Tuned on URMP brass and
    ChoraleBricks: fixes 4 of 6 half-level tracks without false doubles.
    """
    bpm = 60 / np.median(np.diff(beat_times))
    on = np.unique(np.round(np.sort(onsets), 2))
    ioi = np.diff(BeatMap(beat_times).to_beats(on))
    ioi = ioi[ioi > 0.08]
    if len(ioi) and bpm < 90 and np.median(ioi) <= 0.3:
        mids = (beat_times[:-1] + beat_times[1:]) / 2
        return np.sort(np.concatenate([beat_times, mids]))
    return beat_times


FREE_GRIDS = (1, 2)  # inside free-time regions: quarters and 8ths only


def _in_ranges(k: int, ranges: list[tuple[float, float]] | None) -> bool:
    return bool(ranges) and any(a <= k < b for a, b in ranges)


def choose_grids(onset_beats: np.ndarray, coarse: list[tuple[float, float]] | None = None) -> dict[int, int]:
    """Pick a subdivision per beat index that minimizes squared snap error + complexity.

    Beats inside a `coarse` range [start, end) (beat indices) choose only from
    FREE_GRIDS: in proportional notation finer values would just transcribe rubato.
    """
    by_beat: dict[int, list[float]] = {}
    for x in onset_beats:
        # Onsets just before a beat belong to that beat's downbeat slot.
        k = int(np.floor(x + 1 / 12))
        by_beat.setdefault(k, []).append(x - k)
    choice = {}
    for k, fracs in by_beat.items():
        f = np.array(fracs)
        allowed = FREE_GRIDS if _in_ranges(k, coarse) else GRIDS
        best = min(allowed, key=lambda g: np.sum((f - np.round(f * g) / g) ** 2) + GRIDS[g] * len(f))
        choice[k] = best
    return choice


# Dense passages (fast runs, trills) on a monophonic line: a beat whose chosen grid would put two onsets on one
# slot picks again from these grids, 32nds included, paying COLLIDE per onset a grid cannot hold and SWITCH for
# leaving the previous beat's grid (as much as a lost onset: a run keeps one subdivision and moves a note rather
# than mixing 16ths, sextuplets and 32nds beat to beat). A tuplet or 32nd grid is offered only on evidence:
# DENSE_MIN_ONSETS onsets in the beat, all within DENSE_FIT of their slots. Beats that hold their onsets keep
# today's choice exactly.
DENSE_GRIDS: dict[int, float] = {**GRIDS, 8: 0.2}
COLLIDE = 1.0
DENSE_ERR = 10.0  # snap error weight when a dense beat chooses again: triplets are not 16ths 50 ms off
SWITCH = 1.0
DENSE_MIN_ONSETS = 3  # a tuplet or 32nd grid needs at least this many onsets in the beat ...
DENSE_FIT = 0.045  # ... every one of them within this many beats of its slot
MIN_SLOT = 0.045  # seconds: a grid of 6 or 8 whose slots are shorter than this is not offered (no 64ths on a doubled beat)


def _lost(f: np.ndarray, g: int, next_head: np.ndarray | None) -> int:
    """Onsets of one beat (fractions `f`) that grid g cannot hold: two on one slot, or one rounded onto the next
    beat's downbeat when that beat starts with an onset (`next_head`: the next beat's fractions)."""
    slots = np.round(f * g)
    lost = len(slots) - len(np.unique(slots))
    if next_head is not None and np.any(slots == g) and np.any(np.abs(next_head) < 0.5 / g):
        lost += 1
    return int(lost)


# Tuplet runs: jitter of 15 ms moves a triplet 8th past DENSE_FIT of its slot in about half the beats, so a beat on
# its own is weak evidence. A run of at least TUPLET_RUN consecutive beats that each hold exactly g onsets (3 or 6)
# is written in that tuplet when, summed over the run, the tuplet's snap error is under TUPLET_RATIO of the plain
# grid's (16ths for triplets, 32nds for sextuplets) and no onset is more than TUPLET_FIT off its slot. Straight 16ths
# never hold exactly 3 or 6 onsets a beat unless notes are missing, and then the plain grid fits them far better.
TUPLET_RUN = 2
TUPLET_RATIO = 0.25
TUPLET_FIT = 0.1
TUPLET_PLAIN = {3: 4, 6: 8}


def _sse(f: np.ndarray, g: int) -> float:
    return float(np.sum((f - np.round(f * g) / g) ** 2))


def tuplet_runs(by_beat: dict[int, list[float]], beat_seconds: np.ndarray | None = None) -> dict[int, int]:
    """Beats of the tuplet runs (see TUPLET_RUN) and their tuplet grid."""
    out: dict[int, int] = {}
    for g, plain in TUPLET_PLAIN.items():
        ks = sorted(k for k, f in by_beat.items() if len(f) == g)
        runs: list[list[int]] = []
        for k in ks:
            if runs and runs[-1][-1] == k - 1:
                runs[-1].append(k)
            else:
                runs.append([k])
        for run in runs:
            if len(run) < TUPLET_RUN:
                continue
            if beat_seconds is not None and g >= 6 and any(
                    float(beat_seconds[min(max(k, 0), len(beat_seconds) - 1)]) / g < MIN_SLOT for k in run):
                continue
            fs = [np.array(by_beat[k]) for k in run]
            if max(float(np.max(np.abs(f - np.round(f * g) / g))) for f in fs) > TUPLET_FIT:
                continue
            if sum(_sse(f, g) for f in fs) < TUPLET_RATIO * sum(_sse(f, plain) for f in fs):
                out.update({k: g for k in run})
    return out


def choose_grids_dense(onset_beats: np.ndarray, coarse: list[tuple[float, float]] | None = None,
                       beat_seconds: np.ndarray | None = None) -> dict[int, int]:
    """choose_grids; beats of a tuplet run (tuplet_runs) take its tuplet; then every beat whose grid loses onsets
    chooses again from DENSE_GRIDS (free time included)."""
    choice = choose_grids(onset_beats, coarse)
    by_beat: dict[int, list[float]] = {}
    for x in onset_beats:
        k = int(np.floor(x + 1 / 12))
        by_beat.setdefault(k, []).append(x - k)
    choice.update(tuplet_runs(by_beat, beat_seconds))
    for k in sorted(by_beat):
        f = np.array(by_beat[k])
        nxt = np.array(by_beat[k + 1]) if k + 1 in by_beat else None
        if _lost(f, choice[k], nxt) == 0:
            continue
        spb = float(beat_seconds[min(max(k, 0), len(beat_seconds) - 1)]) if beat_seconds is not None else 1.0
        best, best_cost = choice[k], np.inf
        for g, pen in DENSE_GRIDS.items():
            if g >= 6 and spb / g < MIN_SLOT:
                continue
            if g in (3, 6, 8) and (len(f) < DENSE_MIN_ONSETS or np.max(np.abs(f - np.round(f * g) / g)) > DENSE_FIT):
                continue  # no evidence for the finer grid: keep a plain one (and move a colliding note)
            cost = (DENSE_ERR * np.sum((f - np.round(f * g) / g) ** 2) + pen * len(f) + COLLIDE * _lost(f, g, nxt)
                    + (SWITCH if k - 1 in choice and g != choice[k - 1] else 0.0))
            if cost < best_cost:
                best, best_cost = g, cost
        choice[k] = best
    return choice


def snap(x: float, grids: dict[int, int], default: int = 4) -> int:
    k = int(np.floor(x + 1 / 12))
    g = grids.get(k, default)
    return int(round((k + round((x - k) * g) / g) * TICKS_PER_BEAT))


def quantize(notes: list[dict], beat_times: np.ndarray, monophonic: bool = False, auto_level: bool = True,
             coarse: list[tuple[float, float]] | None = None, dense: bool = False) -> list[QNote]:
    """Notes on the beat grid. `dense` (a monophonic line: the solo) lets beats whose grid would lose onsets choose
    a finer one (choose_grids_dense), and moves a note that still lands on a taken slot to the next free slot of
    its beat's grid, at half its confidence, instead of dropping it."""
    if not notes:
        return []
    if auto_level:
        beat_times = choose_level(np.asarray(beat_times, dtype=float), np.array([n["onset"] for n in notes]))
    bm = BeatMap(beat_times)
    on = bm.to_beats(np.array([n["onset"] for n in notes]))
    off = bm.to_beats(np.array([n["offset"] for n in notes]))
    if dense and monophonic:
        grids = choose_grids_dense(on, coarse, np.r_[np.diff(bm.t), bm.t[-1] - bm.t[-2]])
    else:
        grids = choose_grids(on, coarse)
    out = []
    for n, a, b in zip(notes, on, off):
        start = snap(a, grids)
        kb = int(np.floor(b + 1 / 12))
        end = snap(b, grids, 2 if _in_ranges(kb, coarse) else 4)
        k = int(np.floor(a + 1 / 12))
        unit = TICKS_PER_BEAT // grids.get(k, 2 if _in_ranges(k, coarse) else 4)
        end = max(end, start + unit)
        out.append(QNote(n["pitch"], start, end, n["onset"], n["offset"], n.get("confidence", 1.0)))
    if dense and monophonic:
        out.sort(key=lambda q: (q.start, q.onset_s, -q.pitch))
        return _monophonize_dense(out, grids)
    out.sort(key=lambda q: (q.start, -q.pitch))
    if monophonic:
        out = _monophonize(out)
    return out


def _monophonize_dense(notes: list[QNote], grids: dict[int, int]) -> list[QNote]:
    """_monophonize, but a note on a taken slot moves to the next slot of its beat's grid when that is free
    (before the next note), at half its confidence; only then is it dropped."""
    kept: list[QNote] = []
    for i, q in enumerate(notes):
        if kept and q.start <= kept[-1].start:
            k = int(np.floor(kept[-1].start / TICKS_PER_BEAT))
            new = kept[-1].start + TICKS_PER_BEAT // grids.get(k, 4)
            if i + 1 < len(notes) and notes[i + 1].start <= new:
                continue
            q.end = max(q.end, new + (new - kept[-1].start))
            q.start = new
            q.confidence = round(q.confidence * 0.5, 3)
        if kept and kept[-1].end > q.start:
            kept[-1].end = q.start
        kept.append(q)
    return kept


def _monophonize(notes: list[QNote]) -> list[QNote]:
    """Keep the highest note per onset and cut each note at the next onset."""
    kept: list[QNote] = []
    for q in notes:
        if kept and kept[-1].start == q.start:
            continue  # sorted by descending pitch within an onset
        if kept and kept[-1].end > q.start:
            kept[-1].end = q.start
        kept.append(q)
    return kept


def fill_gaps(notes: list[QNote], max_gap_ticks: int = TICKS_PER_BEAT, min_ratio: float = 0.0) -> list[QNote]:
    """Infer notated durations in one voice: hold each note until the next onset.

    Players release notes early (staccato, breathing), so performed lengths
    under-read the written value. A gap up to `max_gap_ticks`, or one that is
    small relative to the note (gap <= min_ratio * duration), is absorbed;
    longer gaps stay as rests.
    """
    out = sorted(notes, key=lambda q: q.start)
    starts = sorted({q.start for q in out})
    nxt = {s: n for s, n in zip(starts, starts[1:])}
    for q in out:
        n = nxt.get(q.start)
        if n is None:
            continue
        gap = n - q.end
        if 0 < gap <= max(max_gap_ticks, min_ratio * (q.end - q.start)):
            q.end = n
        elif gap < 0:
            q.end = n
    return out
