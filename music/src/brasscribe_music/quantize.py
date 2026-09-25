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


def snap(x: float, grids: dict[int, int], default: int = 4) -> int:
    k = int(np.floor(x + 1 / 12))
    g = grids.get(k, default)
    return int(round((k + round((x - k) * g) / g) * TICKS_PER_BEAT))


def quantize(notes: list[dict], beat_times: np.ndarray, monophonic: bool = False, auto_level: bool = True,
             coarse: list[tuple[float, float]] | None = None) -> list[QNote]:
    if not notes:
        return []
    if auto_level:
        beat_times = choose_level(np.asarray(beat_times, dtype=float), np.array([n["onset"] for n in notes]))
    bm = BeatMap(beat_times)
    on = bm.to_beats(np.array([n["onset"] for n in notes]))
    off = bm.to_beats(np.array([n["offset"] for n in notes]))
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
    out.sort(key=lambda q: (q.start, -q.pitch))
    if monophonic:
        out = _monophonize(out)
    return out


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
