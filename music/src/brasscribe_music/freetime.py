"""Free-time (rubato, ad lib.) passages: find them in the beat track, notate them proportionally.

A beat tracker run over a free-time passage still emits "beats", but they
are 1-6 s apart and irregular, and quantizing onto them turns sustained
phrases into 32nds and rests. Here:

1. `unstable_runs` finds runs of beat intervals that fit neither the piece's
   tempo nor its double or half (the tracker switching metrical level or
   dropping a beat is not free time), nor a beat split in two. A run must
   span at least `MIN_INTERVALS` intervals and `MIN_SECONDS` seconds, and
   its intervals must vary (a steady section at another tempo is not free).
   Fewer than `MIN_STABLE` stable-looking intervals inside a run do not end it.
2. `plan_free_time` replaces each run's beats with evenly spaced synthetic
   beats at a local tempo estimated from the note stream (or a tempo the user
   gives), rounded to whole bars so the strict grid resumes on a bar line at
   the first stable downbeat. Positions inside are then proportional to
   performed time and the quantizer's ordinary grid makes them readable.

The result is a new beat list, bar phase and FreeRegions for the
Composition; beats outside the runs are unchanged.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .quantize import TICKS_PER_BEAT
from .score_model import Articulation, FreeNotation, FreeRegion, Note

RATIO_TOL = 0.25  # an interval within 25% of 1/2, 1 or 2 times the piece's beat is stable
MIN_INTERVALS = 3
MIN_SECONDS = 4.0
MIN_CV = 0.2  # coefficient of variation of the run's intervals
MIN_STABLE = 4  # fewer stable intervals than this between two unstable ones do not end a run
TEMPO_RANGE = (40.0, 100.0)  # BPM for proportional notation
TARGET_IOI_BEATS = 2.0  # the local tempo makes the median gap between melody onsets a half note


def _stable(ratio: float) -> bool:
    return any(abs(ratio - m) <= RATIO_TOL * m for m in (0.5, 1.0, 2.0))


def unstable_runs(beat_times: np.ndarray) -> list[tuple[int, int]]:
    """(first, last) beat indices of each free-time run: beats first..last are irregular.

    Interval i runs from beat i to beat i+1; a run of unstable intervals i..j
    gives beats (i, j+1): beat j+1 is the first beat of the stable grid.
    """
    t = np.asarray(beat_times, dtype=float)
    if len(t) < 3:
        return []
    ibi = np.diff(t)
    ref = float(np.median(ibi))
    ratio = ibi / ref
    ok = np.array([_stable(r) for r in ratio])
    # A beat split in two (two short intervals summing to one beat) is a tracker glitch, not free time.
    for i in range(len(ibi) - 1):
        if not ok[i] and not ok[i + 1] and _stable(ratio[i] + ratio[i + 1]):
            ok[i] = ok[i + 1] = True
    # Irregular intervals can land near a multiple of the beat by chance: short stable islands
    # between unstable intervals belong to the run.
    bad = np.where(~ok)[0]
    for x, y in zip(bad, bad[1:]):
        if 1 < y - x <= MIN_STABLE:
            ok[x + 1:y] = False
    runs = []
    i = 0
    while i < len(ibi):
        if ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(ibi) and not ok[j + 1]:
            j += 1
        seg = ibi[i:j + 1]
        if j - i + 1 >= MIN_INTERVALS and seg.sum() >= MIN_SECONDS and np.std(seg) / np.mean(seg) >= MIN_CV:
            runs.append((i, j + 1))
        i = j + 1
    return runs


def local_tempo(onsets: np.ndarray, t0: float, t1: float) -> float:
    """BPM at which the median gap between distinct onsets in [t0, t1) is TARGET_IOI_BEATS, clamped to TEMPO_RANGE."""
    on = np.unique(np.round(np.sort(np.asarray(onsets, dtype=float)), 2))
    on = on[(on >= t0) & (on < t1)]
    gaps = np.diff(on)
    gaps = gaps[gaps > 0.12]
    if not len(gaps):
        return TEMPO_RANGE[0]
    bpm = 60.0 * TARGET_IOI_BEATS / float(np.median(gaps))
    return float(np.clip(bpm, *TEMPO_RANGE))


@dataclass
class FreeTimePlan:
    beat_times: np.ndarray
    first_downbeat: int  # bar phase: a bar starts on this beat index (and every beats_per_bar from it)
    spans: list[tuple[int, int, float, float, float]]  # per region: beat index start, end, start_s, end_s, BPM
    notation: FreeNotation = FreeNotation.PROPORTIONAL
    label: str = "ad lib."

    @property
    def beat_ranges(self) -> list[tuple[float, float]]:
        """[start, end) beat indices of each region (for the quantizer's coarse grids)."""
        return [(a, b) for a, b, *_ in self.spans]

    def regions(self, first_downbeat: int | None = None) -> list[FreeRegion]:
        """FreeRegions in ticks, with tick 0 at beat `first_downbeat` (default: this plan's)."""
        f = self.first_downbeat if first_downbeat is None else first_downbeat
        return [FreeRegion((a - f) * TICKS_PER_BEAT, (b - f) * TICKS_PER_BEAT, s0, s1, round(bpm, 2), self.notation,
                           self.label) for a, b, s0, s1, bpm in self.spans]


def plan_free_time(beat_times: np.ndarray, onsets: np.ndarray, beats_per_bar: int, first_downbeat: int,
                   downbeats: np.ndarray | None = None, tempo: float | None = None,
                   label: str = "ad lib.", tempo_onsets: np.ndarray | None = None) -> FreeTimePlan:
    """Replace free-time runs by bar-aligned synthetic beats.

    `downbeats` (bool per beat, e.g. Beat This! position == 1) picks where the
    strict grid resumes: the first labelled downbeat at or after the run's end.
    Without labels, bars count from `first_downbeat`. A run that starts at the
    first beat also takes in every onset before it, and then becomes the start
    of the piece (tick 0). The local tempo comes from `tempo_onsets` (the
    melody's, when known; default `onsets`); `tempo` notates every region at
    that BPM instead.
    """
    t = np.asarray(beat_times, dtype=float)
    on = np.asarray(onsets, dtype=float)
    runs = unstable_runs(t)
    if not runs:
        return FreeTimePlan(t, first_downbeat, [])

    def is_down(k: int) -> bool:
        if downbeats is not None:
            return bool(downbeats[k])
        return (k - first_downbeat) % beats_per_bar == 0

    out: list[float] = []
    spans: list[tuple[int, int, float, float, float]] = []  # new-index start, end, s0, s1, bpm
    cursor = 0
    new_first = first_downbeat
    for a, b in runs:
        # Resume at the first downbeat at or after the run's end.
        r = next((k for k in range(b, len(t)) if is_down(k)), None)
        if r is None:
            continue
        at_start = a == 0
        if not at_start:
            # Start on the last bar line at or before the run (bar numbering of the beats already emitted).
            a = max((k for k in range(cursor, a + 1) if (len(out) + k - cursor - new_first) % beats_per_bar == 0),
                    default=a)
        if a < cursor:
            continue
        s0 = float(min(t[a], on.min())) if at_start and len(on) else float(t[a])
        s1 = float(t[r])
        bpm = tempo or local_tempo(on if tempo_onsets is None else tempo_onsets, s0, s1)
        n = max(1, int(np.ceil((s1 - s0) * bpm / 60.0 / beats_per_bar))) * beats_per_bar
        bpm = n * 60.0 / (s1 - s0)
        out.extend(t[cursor:a])
        start_idx = len(out)
        out.extend(s0 + np.arange(n) * (s1 - s0) / n)
        spans.append((start_idx, start_idx + n, s0, s1, bpm))
        if at_start:
            new_first = start_idx
        cursor = r
    out.extend(t[cursor:])
    if not spans:
        return FreeTimePlan(t, first_downbeat, [])
    notation = FreeNotation.TEMPO if tempo else FreeNotation.PROPORTIONAL
    return FreeTimePlan(np.array(out), new_first, spans, notation, label)


def mark_fermatas(notes: list[Note], regions: list[FreeRegion]) -> None:
    """Fermata on the last note of a line that starts inside each free region (the cadence before a tempo)."""
    for r in regions:
        inside = [n for n in notes if r.start <= n.start < r.end]
        if inside:
            last = max(inside, key=lambda n: n.start)
            if Articulation.FERMATA not in last.articulations:
                last.articulations.append(Articulation.FERMATA)
