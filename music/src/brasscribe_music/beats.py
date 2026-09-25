"""Beat-track cleanup: restore missed beats, remove inserted ones, and fix the bar phase from downbeats.

A beat tracker that drops a beat leaves a double-length interval; one that
inserts a beat splits an interval in two. Either shifts every later bar line
by a beat. Here, against the local tempo (median of the neighbouring
intervals):
  - an interval of about k beats (k = 2, 3) gets k - 1 evenly spaced beats,
    if a note starts on one of them (otherwise it is a held chord)
  - an interval under `SPLIT_RATIO` of a beat loses the beat that leaves the
    more regular pair of intervals
Free-time runs (freetime.unstable_runs) are left alone.

`clean_beats_gated` keeps the result only when the tracker's downbeat
labels agree better with it (or, without bar labels, when the problem is
systematic), so a consistent track is left as it is.

The bar phase is then chosen by the tracker's downbeat labels: the phase
(beat index mod beats per bar) that most labelled downbeats agree with. Labels
are moved with their beats, and inserted beats carry none.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass

import numpy as np

WINDOW = 8  # intervals on each side for the local tempo
MISS_TOL = 0.2  # an interval within 20% of k beats (k >= 2) is k beats
SPLIT_RATIO = 0.6  # an interval under 60% of a beat has an inserted beat


@dataclass
class CleanBeats:
    times: np.ndarray
    downbeat: np.ndarray  # bool per beat: labelled downbeat (False for restored beats)
    inserted: int
    removed: int
    applied: bool = True  # False when gated: the times and labels are the tracker's own

    def agreement(self, beats_per_bar: int) -> float:
        """Share of labelled downbeats that fall on the majority bar phase."""
        idx = np.where(self.downbeat)[0]
        if not len(idx):
            return 0.0
        return Counter(int(i) % beats_per_bar for i in idx).most_common(1)[0][1] / len(idx)

    def phase(self, beats_per_bar: int) -> int:
        """Beat index (0 <= i < beats_per_bar) of the first downbeat, by majority of the labels."""
        idx = np.where(self.downbeat)[0]
        if not len(idx):
            return 0
        return Counter(int(i) % beats_per_bar for i in idx).most_common(1)[0][0]


def _local(ibi: np.ndarray, i: int, skip: list[tuple[int, int]] | None = None) -> float:
    """Local beat length: median of the neighbouring intervals, leaving out free-time ones.

    Neighbours that are themselves about k beats (missed beats nearby) count as
    one k-th of their length, measured against the piece's median beat.
    """
    skip = skip or []
    strict = [ibi[j] for j in range(len(ibi)) if not _skip(j, skip)]
    g = float(np.median(strict)) if strict else float(np.median(ibi))
    lo, hi = max(0, i - WINDOW), min(len(ibi), i + WINDOW + 1)
    seg = [ibi[j] / max(1, round(ibi[j] / g)) for j in range(lo, hi) if j != i and not _skip(j, skip)]
    return float(np.median(seg)) if seg else g


ONSET_TOL = 0.15  # beats: a restored beat needs a note onset this close


MIN_ONSETS = 1  # notes that must start at a restored beat


def _has_onset(on: np.ndarray, t0: float, d: float, k: int) -> bool:
    beat = d / k
    for m in range(1, k):
        x = t0 + beat * m
        lo, hi = np.searchsorted(on, x - ONSET_TOL * beat), np.searchsorted(on, x + ONSET_TOL * beat, side="right")
        if hi - lo >= MIN_ONSETS:
            return True
    return False


def _skip(i: int, skip: list[tuple[int, int]]) -> bool:
    return any(a <= i < b for a, b in skip)


def clean_beats(times: np.ndarray, downbeat: np.ndarray | None = None,
                skip: list[tuple[int, int]] | None = None, onsets: np.ndarray | None = None) -> CleanBeats:
    """Restore missed and remove inserted beats outside the `skip` beat-index ranges.

    With `onsets`, a missed beat is restored only where a note starts near it:
    a long interval with no onset inside is a held chord (a fermata), and
    splitting it would add beats the music does not have.
    """
    on = np.sort(np.asarray(onsets, dtype=float)) if onsets is not None else None
    t = list(np.asarray(times, dtype=float))
    lab = list(np.zeros(len(t), bool) if downbeat is None else np.asarray(downbeat, bool))
    keep_out = [(a, b) for a, b in (skip or [])]
    removed = 0
    # Remove inserted beats first, so they do not distort the local tempo for restoring missed ones.
    i = 1
    while i < len(t) - 1:
        ibi = np.diff(t)
        if not _skip(i, keep_out) and ibi[i - 1] < SPLIT_RATIO * _local(ibi, i - 1, keep_out):
            # Drop beat i or beat i-1, whichever leaves the more even neighbourhood.
            ref = _local(ibi, i - 1, keep_out)
            left = t[i - 2] if i >= 2 else None
            cost_i = abs((t[i + 1] - t[i - 1]) - ref)
            cost_prev = abs((t[i] - left) - ref) if left is not None else np.inf
            j = i if cost_i <= cost_prev else i - 1
            # Keep a downbeat label on the survivor.
            if lab[j]:
                lab[j + 1 if j == i - 1 else j - 1] = True
            del t[j]
            del lab[j]
            keep_out = [(a - (a > j), b - (b > j)) for a, b in keep_out]
            removed += 1
            continue
        i += 1
    inserted = 0
    out_t, out_l = [t[0]], [lab[0]]
    ibi = np.diff(t)
    for i, d in enumerate(ibi):
        if not _skip(i, keep_out):
            ref = _local(ibi, i, keep_out)
            k = int(round(d / ref))
            if k >= 2 and abs(d / ref - k) <= MISS_TOL * k and (on is None or _has_onset(on, t[i], d, k)):
                for m in range(1, k):
                    out_t.append(t[i] + d * m / k)
                    out_l.append(False)
                inserted += k - 1
        out_t.append(t[i + 1])
        out_l.append(lab[i + 1])
    return CleanBeats(np.array(out_t), np.array(out_l), inserted, removed)


MIN_AGREEMENT_GAIN = 0.02  # the downbeat labels must agree this much better with the cleaned beats
MIN_EDITS_UNLABELLED = 3  # without bar information, only a systematic problem (this many edits) is fixed


def clean_beats_gated(times: np.ndarray, downbeat: np.ndarray, beats_per_bar: int,
                      skip: list[tuple[int, int]] | None = None, onsets: np.ndarray | None = None) -> CleanBeats:
    """clean_beats, applied only when the evidence says the track was wrong.

    With bars (beats_per_bar > 1) the tracker's own downbeat labels vote: the
    cleanup is kept only if more of them then fall on one bar phase (by at
    least MIN_AGREEMENT_GAIN). With one beat per bar the labels carry no bar
    information, so only a systematic problem (MIN_EDITS_UNLABELLED edits or
    more) is fixed; a single long interval is more likely a held note than a
    missed beat. Otherwise the beats are returned unchanged.
    """
    raw = CleanBeats(np.asarray(times, dtype=float), np.asarray(downbeat, bool), 0, 0, applied=False)
    c = clean_beats(times, downbeat, skip=skip, onsets=onsets)
    edits = c.inserted + c.removed
    if not edits:
        return raw
    if beats_per_bar > 1:
        ok = c.agreement(beats_per_bar) >= raw.agreement(beats_per_bar) + MIN_AGREEMENT_GAIN
    else:
        ok = edits >= MIN_EDITS_UNLABELLED
    if not ok:
        raw.inserted, raw.removed = 0, 0
        return raw
    return c
