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


def choose_grids(onset_beats: np.ndarray) -> dict[int, int]:
    """Pick a subdivision per beat index that minimizes squared snap error + complexity."""
    by_beat: dict[int, list[float]] = {}
    for x in onset_beats:
        # Onsets just before a beat belong to that beat's downbeat slot.
        k = int(np.floor(x + 1 / 12))
        by_beat.setdefault(k, []).append(x - k)
    choice = {}
    for k, fracs in by_beat.items():
        f = np.array(fracs)
        best = min(GRIDS, key=lambda g: np.sum((f - np.round(f * g) / g) ** 2) + GRIDS[g] * len(f))
        choice[k] = best
    return choice


def snap(x: float, grids: dict[int, int], default: int = 4) -> int:
    k = int(np.floor(x + 1 / 12))
    g = grids.get(k, default)
    return int(round((k + round((x - k) * g) / g) * TICKS_PER_BEAT))


def quantize(notes: list[dict], beat_times: np.ndarray, monophonic: bool = False) -> list[QNote]:
    if not notes:
        return []
    bm = BeatMap(beat_times)
    on = bm.to_beats(np.array([n["onset"] for n in notes]))
    off = bm.to_beats(np.array([n["offset"] for n in notes]))
    grids = choose_grids(on)
    out = []
    for n, a, b in zip(notes, on, off):
        start = snap(a, grids)
        end = snap(b, grids)
        unit = TICKS_PER_BEAT // grids.get(int(np.floor(a + 1 / 12)), 4)
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
