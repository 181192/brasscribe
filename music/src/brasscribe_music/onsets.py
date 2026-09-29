"""Pitch-change onsets from the SwiftF0 contour: notes the segmentation merged, and glides it split off.

SwiftF0's note segmentation (80 ms hold) keeps a slurred trill or a slurred fast run as one note: without a
re-articulation the only onset is the pitch change, and the segmentation pays for every note, twice for a
return to the previous pitch. The contour still holds the notes. `contour_notes` rereads each SwiftF0 note
on the contour, on the piece's own tuning:

1. Plateaus: runs of at least MIN_RUN frames (48 ms) within TIGHT semitones of one semitone, voiced (SwiftF0
   confidence above 0.5, or a pitch at all when the contour carries no confidence).
2. A note splits at every change of plateau semitone when the plateaus look like notes, not like vibrato:
   - one step or a run in one direction (a scale): the plateaus cover at least STEP_DWELL of the note (a
     single semitone step also needs both plateaus SEMITONE_STEP_FRAMES long: a bend or a vibrato swing
     otherwise);
   - alternation at a whole tone or more: DWELL of the note;
   - alternation at a semitone (a trill, or a lip vibrato that swings down a semitone): TRILL_DWELL of the
     note and at least TRILL_CHANGES changes;
   - alternation wider than ALT_MAX_SPAN (a fifth): never. At an octave the tracker flips octaves on held
     notes (C5 especially), and that is indistinguishable from an octave lip slur here.
   An alternation splits only while its plateaus are short (median at most ALT_MAX_FRAMES) and every pitch
   holds MIN_SHARE of them: slower ones the segmentation already splits, and blips are not notes.
   Before that, a glide at either end of the note is set aside (`_without_glides`): the scoop, rip, fall or
   doit passing through the semitones on its way into or out of the held note.
   Vibrato and a scoop never hold still on the other pitch long enough: the thresholds are set on the
   eval set's vibrato (centred and one-sided, to 150 c), scoop, fall, doit and rip controls, dry, in a hall
   and separated (docs/plan/fast-notes.md).
3. Octave flips: in three or more touching SwiftF0 notes alternating by exactly an octave, the tracker often
   heard one note in two octaves. The run's octave is the one nearer the notes around it (else the one held
   longer); a note in the other octave folds into its neighbour unless Basic Pitch has it too (within
   CONFIRM_TOL), which keeps an octave lip slur. A run of held notes (all FLIP_MAX or longer: a slurred
   octave) stays as it is.
4. Glides: a short note (under GLIDE_MAX) touching a neighbour (the next one first), that is mostly slide
   (plateaus under GLIDE_DWELL of it) and slides toward that neighbour at GLIDE_SLOPE or faster (a passing
   note in a fast slurred run slides more slowly), is the scoop or rip into
   it or the fall or doit off it, and goes: the next note starts where its scoop starts, the previous one
   ends where its fall ends.

Split notes are marked "split" (the solo line keeps them down to 30 ms). The Rust core has the same rules
(onsets.rs).
"""

from __future__ import annotations

import numpy as np

TIGHT = 0.25
MIN_RUN = 3
STEP_DWELL = 0.7
SEMITONE_STEP_FRAMES = 5
DWELL = 0.7
TRILL_DWELL = 0.85
TRILL_CHANGES = 4
ALT_MAX_FRAMES = 16
ALT_MAX_SPAN = 7
MIN_SHARE = 0.25  # in an alternation, each pitch holds at least this share of the plateau frames (not a blip)
GLIDE_FRAMES = 5
GLIDE_STEP = 3
GLIDE_CHAIN_DWELL = 0.6
GLIDE_SLOPE = 22.0  # semitones per second: the controls' rips and falls slide 25-75, fast Mikkel notes under 20
FLIP_MAX = 0.3
CONFIRM_TOL = 0.05
GLIDE_MAX = 0.2
GLIDE_DWELL = 0.3
GLIDE_GAP = 0.03
CONFIDENT = 0.5
FRAME = 0.016


def tuning(midi: np.ndarray, voiced: np.ndarray) -> float:
    """The piece's offset from A440 in semitones (-0.5..0.5): circular mean of the voiced frames' fractions."""
    m = midi[voiced]
    if len(m) == 0:
        return 0.0
    ang = 2 * np.pi * m
    return float(np.arctan2(np.sum(np.sin(ang)), np.sum(np.cos(ang))) / (2 * np.pi))


def _voiced(c) -> np.ndarray:
    ok = np.isfinite(c.midi)
    if c.confidence is not None:
        ok &= c.confidence > CONFIDENT
    return ok


def plateaus(x: np.ndarray, ok: np.ndarray) -> list[tuple[int, int, int]]:
    """(first frame, end frame, semitone) of each run of >= MIN_RUN frames within TIGHT of one semitone."""
    s = np.round(np.nan_to_num(x, nan=-1000.0))
    tight = ok & (np.abs(np.nan_to_num(x, nan=-1000.0) - s) <= TIGHT)
    out, a = [], -1
    for i in range(len(x) + 1):
        if i < len(x) and tight[i] and a >= 0 and s[i] == s[a]:
            continue
        if a >= 0 and i - a >= MIN_RUN:
            out.append((a, i, int(s[a])))
        a = i if i < len(x) and tight[i] else -1
    return out


def _splits(pl: list[tuple[int, int, int]], n_frames: int) -> bool:
    """Do these plateaus (of one note, n_frames long) look like several notes?"""
    sems = [p[2] for p in pl]
    changes = sum(1 for a, b in zip(sems, sems[1:]) if a != b)
    if changes == 0:
        return False
    dwell = sum(b - a for a, b, _ in pl) / max(1, n_frames)
    steps = [b - a for a, b in zip(sems, sems[1:]) if a != b]
    if all(d > 0 for d in steps) or all(d < 0 for d in steps):
        if len(steps) == 1 and abs(steps[0]) == 1 and min(b - a for a, b, _ in pl) < SEMITONE_STEP_FRAMES:
            return False  # one semitone step: a bend or a vibrato swing unless both pitches really hold
        return dwell >= STEP_DWELL
    if float(np.median([b - a for a, b, _ in pl])) > ALT_MAX_FRAMES:
        return False
    held: dict[int, int] = {}
    for a, b, s in pl:
        held[s] = held.get(s, 0) + b - a
    if min(held.values()) < MIN_SHARE * sum(held.values()):
        return False
    span = max(sems) - min(sems)
    if span > ALT_MAX_SPAN:
        return False
    if span == 1:
        return dwell >= TRILL_DWELL and changes >= TRILL_CHANGES
    return dwell >= DWELL


def _without_glides(pl: list[tuple[int, int, int]]) -> list[tuple[int, int, int]]:
    """The plateaus without a glide at either end: a chain of short plateaus (<= GLIDE_FRAMES each) moving in one
    direction by at most GLIDE_STEP semitones a step, next to a held plateau (> 2 * GLIDE_FRAMES), that either
    moves by semitones or holds still for under GLIDE_CHAIN_DWELL of its span (a scoop, rip, fall or doit
    passing through the semitones; a slurred scale into a held note holds each of its notes)."""
    pl = list(pl)
    for _ in range(2):
        k = len(pl)
        while k > 0 and pl[k - 1][1] - pl[k - 1][0] <= GLIDE_FRAMES:
            k -= 1
        if 0 < k < len(pl) and pl[k - 1][1] - pl[k - 1][0] > 2 * GLIDE_FRAMES:
            steps = [b[2] - a[2] for a, b in zip(pl[k - 1:], pl[k:])]
            span = pl[-1][1] - pl[k][0]
            dwell = sum(q - p for p, q, _ in pl[k:]) / max(1, span)
            if all(0 < abs(d) <= GLIDE_STEP for d in steps) and (all(d > 0 for d in steps) or all(d < 0 for d in steps)) \
                    and (all(abs(d) == 1 for d in steps) or dwell < GLIDE_CHAIN_DWELL):
                pl = pl[:k]
        pl.reverse()
    return pl


def split_note(n: dict, c, tau: float, voiced: np.ndarray) -> list[dict]:
    """One SwiftF0 note as the notes its contour plateaus show (itself when they do not)."""
    a = int(np.searchsorted(c.t, n["onset"] - FRAME / 2))
    b = int(np.searchsorted(c.t, n["offset"] - FRAME / 2))
    if b - a < 2 * MIN_RUN:
        return [n]
    x = c.midi[a:b] - tau
    pl = _without_glides(plateaus(x, voiced[a:b]))
    if not _splits(pl, b - a):
        return [n]
    # The note's own plateau (the longest in total) carries the tracker's pitch; the others keep their interval.
    total: dict[int, int] = {}
    for p, q, s in pl:
        total[s] = total.get(s, 0) + q - p
    main = max(sorted(total), key=lambda s: total[s])
    delta = n["pitch"] - main
    out = [{**n, "pitch": pl[0][2] + delta, "split": True}]
    for (p0, q0, s0), (p1, _, s1) in zip(pl, pl[1:]):
        if s1 == s0:
            continue
        on = (float(c.t[a + q0 - 1]) + FRAME + float(c.t[a + p1])) / 2
        out[-1]["offset"] = on
        out.append({**n, "pitch": s1 + delta, "onset": on, "split": True})
    out[-1]["offset"] = n["offset"]
    return out


def _slope(n: dict, c, voiced: np.ndarray) -> float:
    """Pitch slope (semitones per second) across a note: the median of its last third of voiced frames minus the
    median of its first third, over two thirds of its voiced span; 0 with fewer than 4 voiced frames."""
    a = int(np.searchsorted(c.t, n["onset"] - FRAME / 2))
    b = int(np.searchsorted(c.t, n["offset"] - FRAME / 2))
    idx = [i for i in range(a, b) if voiced[i]]
    if len(idx) < 4:
        return 0.0
    k = len(idx) // 3
    head = np.median(c.midi[idx[:k]])
    tail = np.median(c.midi[idx[-k:]])
    span = float(c.t[idx[-1]] - c.t[idx[0]])
    return float((tail - head) / (span * 2 / 3)) if span > 0 else 0.0


def _glide(n: dict, c, tau: float, voiced: np.ndarray, toward: int | None) -> bool:
    """A short note that is mostly slide and slides toward the neighbour it touches (`toward`: +1 up, -1 down)
    at GLIDE_SLOPE or faster: the scoop or rip into that neighbour, or the fall or doit off it."""
    if n["offset"] - n["onset"] >= GLIDE_MAX:
        return False
    a = int(np.searchsorted(c.t, n["onset"] - FRAME / 2))
    b = int(np.searchsorted(c.t, n["offset"] - FRAME / 2))
    if b <= a:
        return False
    pl = plateaus(c.midi[a:b] - tau, voiced[a:b])
    return (toward is not None and sum(q - p for p, q, _ in pl) / (b - a) < GLIDE_DWELL
            and _slope(n, c, voiced) * toward >= GLIDE_SLOPE)


def _confirmed(n: dict, others: list[dict]) -> bool:
    """Another transcriber (Basic Pitch) has this pitch within CONFIRM_TOL of the note's onset."""
    return any(o["pitch"] == n["pitch"] and abs(o["onset"] - n["onset"]) <= CONFIRM_TOL for o in others)


def octave_flips(notes: list[dict], others: list[dict] | None = None) -> list[dict]:
    """Runs of >= 3 touching notes alternating by exactly 12 semitones: the notes in the other octave that no
    other transcriber confirms fold into their neighbours (see the module docstring)."""
    others = others or []
    out, i = [], 0
    while i < len(notes):
        j = i
        while j + 1 < len(notes) and abs(notes[j + 1]["pitch"] - notes[j]["pitch"]) == 12 \
                and notes[j + 1]["onset"] - notes[j]["offset"] <= GLIDE_GAP:
            j += 1
        run = notes[i: j + 1]
        if j - i < 2 or all(n["offset"] - n["onset"] >= FLIP_MAX for n in run):
            out += run
            i = j + 1
            continue
        held: dict[int, float] = {}
        for n in run:
            held[n["pitch"]] = held.get(n["pitch"], 0.0) + n["offset"] - n["onset"]
        # The octave nearer the notes around the run (a melody rarely leaps an octave and back), else the one
        # held longer.
        around = [notes[k]["pitch"] for k in (i - 1, j + 1) if 0 <= k < len(notes)]
        pitch = min(held, key=lambda p: (sum(abs(p - q) for q in around), -held[p], p))
        folded: list[dict] = []
        for n in run:
            keep = n["pitch"] == pitch or _confirmed(n, others)
            if not keep and folded:
                folded[-1] = {**folded[-1], "offset": n["offset"]}
            elif keep and folded and folded[-1]["pitch"] == n["pitch"] and not _confirmed(n, others):
                folded[-1] = {**folded[-1], "offset": n["offset"]}
            else:
                folded.append(n if keep else {**n, "pitch": pitch})
        out += folded
        i = j + 1
    return out


def contour_notes(notes: list[dict], c, others: list[dict] | None = None) -> list[dict]:
    """SwiftF0 notes (one voice, sorted by onset) with the contour's pitch-change onsets, without octave flips and
    glides. `others`: another transcriber's notes (Basic Pitch), which keep an octave note they confirm."""
    if c is None or not notes:
        return notes
    notes = octave_flips(notes, others)
    voiced = _voiced(c)
    tau = tuning(c.midi, voiced)
    kept: list[dict] = []
    carry = None  # the onset of a glide into the next note: the note starts where its scoop or rip starts
    for i, n in enumerate(notes):
        prev_end = notes[i - 1]["offset"] if i else -1.0
        next_on = notes[i + 1]["onset"] if i + 1 < len(notes) else float("inf")
        touch_prev = n["onset"] - prev_end <= GLIDE_GAP
        touch_next = next_on - n["offset"] <= GLIDE_GAP
        # the way a glide into the next note (or off the previous one) moves
        toward = (int(np.sign(notes[i + 1]["pitch"] - n["pitch"])) if touch_next else
                  int(np.sign(n["pitch"] - notes[i - 1]["pitch"])) if touch_prev else None)
        if (touch_prev or touch_next) and _glide(n, c, tau, voiced, toward or None):
            if touch_next:
                carry = n["onset"] if carry is None else carry
            elif kept:
                kept[-1] = {**kept[-1], "offset": n["offset"]}
            continue
        kept.append({**n, "onset": carry} if carry is not None else n)
        carry = None
    out = []
    for n in kept:
        out += split_note(n, c, tau, voiced)
    return out
