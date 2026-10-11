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


# ---------------------------------------------------------------- meter from the notes

MAX_DOWNBEAT_RATE = 0.5  # more labelled downbeats per beat than this: the labels carry no bar information
METERS = (2, 3, 4)
ONSET_TOL_BEATS = 0.2


@dataclass
class Meter:
    beats_per_bar: int
    first_downbeat: int  # a beat index that starts a bar
    from_labels: bool  # False: inferred from the note accents
    compound: bool = False  # beats divide in three (6/8, 9/8, 12/8 read at the dotted-quarter beat)
    strength: float = 0.0  # accent contrast of the chosen meter and phase (inferred only)
    times: np.ndarray | None = None  # beat times adjusted to the tracked bar phase (inferred only)


def downbeat_rate(downbeat: np.ndarray) -> float:
    return float(np.mean(downbeat)) if len(downbeat) else 0.0


def beat_strengths(beat_times: np.ndarray, onsets: np.ndarray, durations: np.ndarray) -> np.ndarray:
    """Accent per beat from the notes starting on it: 1 per note plus its length in beats (capped at 2),
    so long notes (agogic accents) weigh more, as they do on strong beats."""
    t = np.asarray(beat_times, dtype=float)
    ibi = np.diff(t)
    s = np.zeros(len(t))
    for on, d in zip(onsets, durations):
        k = int(np.searchsorted(t, on))
        for j in (k - 1, k):
            if 0 <= j < len(t):
                beat = ibi[min(j, len(ibi) - 1)] if len(ibi) else 1.0
                if abs(on - t[j]) <= ONSET_TOL_BEATS * beat:
                    s[j] += 1.0 + min(2.0, d / beat)
                    break
    return s


ACCENT_WEIGHT = 0.25  # weight of the note accents against the tracker's (over-frequent) downbeat labels


def infer_meter(beat_times: np.ndarray, onsets: np.ndarray, durations: np.ndarray,
                downbeat: np.ndarray | None = None, meters: tuple[int, ...] = METERS,
                accent_weight: float = ACCENT_WEIGHT, positions: np.ndarray | None = None) -> Meter:
    """Beats per bar and bar phase from the labels and the note accents.

    Even when the tracker labels most beats as downbeats, the true downbeats
    are labelled more often than the other beats; long notes also start on
    strong beats more often. For each meter m and phase p the score is how much
    beats p, p+m, ... exceed the average in label rate plus `accent_weight` x
    note accent (normalised to mean 1). The best score wins; a bar of 4 must
    also have its downbeat clearly above beat 3, else it is 2 (a longer period
    always fits noise at least as well as its factor).
    """
    t = np.asarray(beat_times, dtype=float)
    a = beat_strengths(t, onsets, durations)
    a = a / a.mean() if a.mean() > 0 else a
    lab = np.asarray(downbeat, float) if downbeat is not None else np.zeros(len(t))
    s = lab + accent_weight * a
    mean = float(s.mean()) if len(s) else 0.0

    def phase_score(m: int, p: int) -> float:
        seg = s[p::m]
        return float(seg.mean() - mean) if len(seg) else -np.inf

    best = {m: max((phase_score(m, p), p) for p in range(m)) for m in meters}
    m = max(best, key=lambda k: best[k][0])
    if m == 4 and 2 in best:
        c4, p4 = best[4]
        if phase_score(4, (p4 + 2) % 4) > 0.5 * c4:
            m = 2
    c, p = best[m]
    if m == 2 and 4 in best:
        p = p % 2
    # Compound: most onsets inside a beat fall on its thirds rather than its halves.
    frac = []
    for on in onsets:
        k = int(np.searchsorted(t, on)) - 1
        if 0 <= k < len(t) - 1:
            f = (on - t[k]) / (t[k + 1] - t[k])
            if 0.1 < f < 0.9:
                frac.append(f)
    thirds = sum(min(abs(f - 1 / 3), abs(f - 2 / 3)) < min(abs(f - 0.5), 0.1) for f in frac)
    compound = bool(frac) and thirds > 0.5 * len(frac)
    # The phase follows the labels alone (measured: the note accents choose the meter better than
    # they place the bar line); without labels, the accents.
    emission = None
    if positions is not None and m > 1:
        # Every label votes: a beat labelled k (1 = downbeat) supports bar position k - 1.
        pos = np.asarray(positions, int)
        emission = np.stack([(pos == j + 1).astype(float) for j in range(m)], axis=1)
        emission -= emission.mean(axis=0, keepdims=True)
    # Constant labels (every beat a downbeat) say nothing about the phase: then the accents decide.
    phase = lab if lab.min() != lab.max() else s
    times, first = track_bar_phase(t, phase, m, emission=emission)
    return Meter(m, first, False, compound, round(c, 3), times)


def meter_of(beat_times: np.ndarray, downbeat: np.ndarray, onsets: np.ndarray, durations: np.ndarray,
             positions: np.ndarray | None = None) -> Meter:
    """The tracker's bars when its downbeat labels give bars (a most common gap of 2 beats or more),
    else bars inferred from the labels' periodicity and the note accents (infer_meter).

    Beat This! small0 on a single instrument labels most beats as downbeats;
    taken at face value that gives bars of one beat.
    """
    idx = np.where(downbeat)[0]
    gaps = np.diff(idx)
    bpb = int(Counter(gaps).most_common(1)[0][0]) if len(gaps) else 0
    # The labels are kept whenever their most common gap is a real bar (2 beats or more), even at a
    # downbeat rate above MAX_DOWNBEAT_RATE: a 2/4 or 2/2 piece labels every second beat, and noise
    # pushes that over one in two. Measured on the URMP and ChoraleBricks single parts: re-inferring
    # those (63 parts) made 18 worse and 20 better, so they stay with their labels.
    if bpb >= 2:
        return Meter(bpb, int(idx[0]) if len(idx) else 0, True)
    return infer_meter(beat_times, onsets, durations, downbeat, positions=positions)


PHASE_JUMP_COST = 4.0  # in units of the per-beat downbeat score (a label vote is 1)


def track_bar_phase(beat_times: np.ndarray, strength: np.ndarray, beats_per_bar: int,
                    jump_cost: float = PHASE_JUMP_COST, emission: np.ndarray | None = None) -> tuple[np.ndarray, int]:
    """Follow the bar phase through the piece (Viterbi) and make the beat grid fit it.

    States are positions in the bar. From position j the next beat is j+1
    (free), or j again (the tracker inserted a beat: it is dropped), or j+2 (the
    tracker missed one: a beat is restored halfway). Both cost `jump_cost`,
    scaled down where the interval says so (short for a drop, about two beats
    for a restore) and up elsewhere. A beat in position 0 earns its downbeat
    strength (centred on the piece's mean), or `emission` gives a score per beat
    and position.
    Returns the adjusted beat times and the index of the first downbeat in them.
    """
    t = np.asarray(beat_times, dtype=float)
    m = beats_per_bar
    n = len(t)
    if n < 2 or m < 2:
        return t, 0
    e = np.asarray(strength, float) - float(np.mean(strength))
    if emission is None:
        emission = np.zeros((n, m))
        emission[:, 0] = e
    score = np.full((n, m), -np.inf)
    back = np.zeros((n, m, 2), dtype=int)  # previous state, move (0 advance, 1 stay/drop, 2 skip/insert)
    score[0] = emission[0]
    ibi = np.diff(t)
    med = float(np.median(ibi))
    for k in range(1, n):
        r = ibi[k - 1] / med
        # Where the grid changes: a beat is dropped where its interval is short (an inserted beat),
        # restored where the interval is about two beats (a missed one); elsewhere it costs more.
        drop = jump_cost * (0.25 + 2.0 * max(0.0, r - 0.5))
        restore = jump_cost * (0.25 + 2.0 * abs(r - 2.0))
        for j in range(m):
            gain = emission[k, j]
            cands = [(score[k - 1, (j - 1) % m], (j - 1) % m, 0),
                     (score[k - 1, j] - drop, j, 1),
                     (score[k - 1, (j - 2) % m] - restore, (j - 2) % m, 2)]
            best = max(cands, key=lambda c: c[0])
            score[k, j] = best[0] + gain
            back[k, j] = best[1], best[2]
    j = int(np.argmax(score[-1]))
    states, moves = [j], []
    for k in range(n - 1, 0, -1):
        pj, mv = back[k, j]
        moves.append(mv)
        j = int(pj)
        states.append(j)
    states.reverse()
    moves.reverse()  # moves[k-1] is the move into beat k
    out = [t[0]]
    pos = [states[0]]
    for k in range(1, n):
        mv = moves[k - 1]
        if mv == 1:  # inserted beat: drop it
            continue
        if mv == 2:  # missed beat: restore it halfway
            out.append((out[-1] + t[k]) / 2)
            pos.append((pos[-1] + 1) % m)
        out.append(t[k])
        pos.append(states[k])
    first = next((i for i, p in enumerate(pos) if p == 0), 0)
    return np.array(out), first


# ---------------------------------------------------------------- the solo path's bar grid

MIN_METER_STRENGTH = 0.15  # inferred meters with a weaker phase contrast keep the grid's own bars


def labels_on(new_times: np.ndarray, old_times: np.ndarray, labels: np.ndarray, fill=0) -> np.ndarray:
    """Carry per-beat labels from one beat grid to another (nearest beat within a tenth of a beat)."""
    old, new = np.asarray(old_times, float), np.asarray(new_times, float)
    out = np.full(len(new), fill, dtype=np.asarray(labels).dtype)
    if len(old) < 2 or not len(new):
        return out
    tol = 0.1 * float(np.median(np.diff(old)))
    k = np.clip(np.searchsorted(old, new), 1, len(old) - 1)
    near = np.where(np.abs(old[k - 1] - new) <= np.abs(old[k] - new), k - 1, k)
    hit = np.abs(old[near] - new) <= tol
    out[hit] = np.asarray(labels)[near[hit]]
    return out


def kept_notes(times: np.ndarray, onsets: np.ndarray, durations: np.ndarray) -> int:
    """Notes of one voice that keep an onset of their own when quantized on `times`."""
    from .quantize import quantize

    notes = [{"pitch": 60, "onset": float(o), "offset": float(o + max(d, 1e-3))} for o, d in zip(onsets, durations)]
    return len(quantize(notes, times, monophonic=True, auto_level=False)) if len(times) >= 2 and notes else 0


def solo_meter(times: np.ndarray, downbeat: np.ndarray, positions: np.ndarray, beats_per_bar: int,
               first_downbeat: int, onsets: np.ndarray, durations: np.ndarray) -> Meter:
    """Bars for a beat grid whose downbeat labels do not give bars (most common gap under 2 beats).

    `times` is the final grid (after cleanup and metrical-level choice) with the
    tracker's labels carried onto it; `beats_per_bar` and `first_downbeat` are
    what the grid gives without inference. The inferred meter replaces them
    only when its phase contrast reaches MIN_METER_STRENGTH; below that the
    grid's own bars are kept. Fitting the grid to the tracked phase must not
    merge notes: if the fitted grid keeps fewer notes apart than the input grid
    (one voice, as the solo is quantized), the input grid is kept and only the
    phase is taken from it.
    """
    downbeat = np.asarray(downbeat, bool)
    m = infer_meter(times, onsets, durations, downbeat, positions=positions)
    if m.strength < MIN_METER_STRENGTH:
        return Meter(beats_per_bar, first_downbeat, True)
    if m.times is not None and kept_notes(m.times, onsets, durations) < kept_notes(times, onsets, durations):
        phase = downbeat.astype(float) if downbeat.min() != downbeat.max() else beat_strengths(times, onsets, durations)
        _, first = track_bar_phase(times, phase, m.beats_per_bar, jump_cost=1e9)
        return Meter(m.beats_per_bar, first, False, m.compound, m.strength, np.asarray(times, float))
    return m


# A take whose beat tracker found fewer than two beats (a short, fast solo) gets a grid from its onsets instead of
# failing: the beat is the multiple of the typical inter-onset interval (the median over 50 ms) that lies within
# FALLBACK_BEAT seconds, nearest FALLBACK_PREFERRED; without one, FALLBACK_PREFERRED. It runs through the tracked
# beat (else the first onset) with bars of 4, over the take. The score says the tempo is a guess (Composition.
# tempo_estimated).
FALLBACK_MULTIPLES = (1, 2, 3, 4, 6, 8)
FALLBACK_BEAT = (0.4, 0.8)  # seconds: 75 to 150 BPM
FALLBACK_PREFERRED = 0.5  # seconds: 120 BPM
FALLBACK_MIN_IOI = 0.05


def fallback_beats(tracked: np.ndarray, onsets: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """(beat times, positions 1-4) for a take with fewer than two tracked beats (see FALLBACK_MULTIPLES)."""
    on = np.unique(np.round(np.asarray(onsets, dtype=float), 3))
    ioi = np.diff(on)
    ioi = ioi[ioi > FALLBACK_MIN_IOI]
    period = FALLBACK_PREFERRED
    if len(ioi):
        base = float(np.median(ioi))
        cands = [base * m for m in FALLBACK_MULTIPLES if FALLBACK_BEAT[0] <= base * m <= FALLBACK_BEAT[1]]
        if cands:
            period = min(cands, key=lambda p: (abs(p - FALLBACK_PREFERRED), p))
    anchor = float(tracked[0]) if len(tracked) else float(on[0]) if len(on) else 0.0
    first, last = (float(on[0]), float(on[-1])) if len(on) else (anchor, anchor)
    k = np.arange(int(np.floor((first - anchor) / period)) - 1, int(np.ceil((last - anchor) / period)) + 3)
    return anchor + k * period, k % 4 + 1
