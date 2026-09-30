"""Trill notation: a sustained two-pitch alternation written as one note with a trill mark.

A trill is a run of at least MIN_NOTES notes (MIN_NOTES - 1 changes, three full cycles) that
- alternate between exactly two pitches a semitone or a whole tone apart (A B A B ...),
- each follow the previous one without a gap (at most MAX_GAP) and within MAX_STEP seconds, and
- come one every MAX_IOI seconds or faster (the run's median IOI: performed timing jitters).
A held last note (longer than MAX_STEP, or than a 16th on the page) is where the trill resolves, not part of it.

It is written as one note on the lower pitch (the main note: the lower note of a lip or valve trill), from the
run's first onset to its last note's end, with `Note.trill` the semitones up to the auxiliary. The writers spell
the auxiliary from the key of the written part: the next letter up, with an accidental mark only where the key
signature does not already give it. Playback plays the main note.

Two places write a trill:
- `with_trills`, in the transcription at standard and easier: those modes keep SwiftF0's simpler line, where a
  slurred trill is one or two notes. The runs are found on the contour-split line (onsets.contour_notes) and
  replace the notes they cover; every other note stays as it was.
- `collapse_trills`, in the arrangement (difficulty.apply_difficulty): written-out alternations in a part, as
  faithful writes them, become trills at standard and easier, and at faithful when asked for.
The Rust core has the same rules (trills.rs).
"""

from __future__ import annotations

from dataclasses import replace

MIN_NOTES = 7
MAX_IOI = 0.15  # seconds, the run's median IOI: about 7 notes per second or faster
MAX_STEP = 0.2  # seconds, any one IOI of the run
MAX_GAP = 0.05  # seconds between one note's end and the next onset
MAX_IOI_TICKS = 6  # without performed times: 16ths or faster
MAX_GAP_TICKS = 6  # written notes touch within a 16th
STEPS = (1, 2)  # semitone and whole-tone trills; wider alternations (shakes, lip slurs) stay written out


def runs(pitches: list[int], linked: list[bool], held: list[bool]) -> list[tuple[int, int]]:
    """Trill runs [i, j] (inclusive) in a monophonic sequence sorted by start: maximal A B A B ... runs of at least
    MIN_NOTES notes a semitone or a whole tone apart. `linked[i]`: note i + 1 follows note i fast enough and without a
    gap; `held[i]`: note i lasts longer than a trill note (a held last note is where the trill resolves). A note the
    quantizer dropped leaves two neighbours on one pitch (A B A A B): at most two notes in a row on one pitch count as
    one turn of the alternation, and the run needs MIN_NOTES - 1 turns."""
    n = len(pitches)
    # turns: maximal groups of at most 2 linked notes on one pitch, as [first, last]
    turns: list[list[int]] = []
    for k in range(n):
        if turns and pitches[k] == pitches[turns[-1][1]] and linked[k - 1] and turns[-1][1] - turns[-1][0] < 1:
            turns[-1][1] = k
        else:
            turns.append([k, k])
    out: list[tuple[int, int]] = []
    t = 0
    while t + 1 < len(turns):
        a, b = turns[t], turns[t + 1]
        if abs(pitches[a[0]] - pitches[b[0]]) not in STEPS or not linked[a[1]]:
            t += 1
            continue
        u = t + 1
        while (u + 1 < len(turns) and pitches[turns[u + 1][0]] == pitches[turns[u - 1][0]]
               and linked[turns[u][1]]):
            u += 1
        j = turns[u][1]
        if held[j]:
            if turns[u][0] == j:
                u -= 1
            j -= 1
        i = turns[t][0]
        if u - t + 1 >= MIN_NOTES - 1 and j - i + 1 >= MIN_NOTES:
            out.append((i, j))
            t = u + 1
        else:
            t += 1
    return out


def fast(onsets: list[float], i: int, j: int) -> bool:
    """The median IOI of notes i..j (the upper one of an even count) is at most MAX_IOI."""
    d = sorted(onsets[k + 1] - onsets[k] for k in range(i, j))
    return d[len(d) // 2] <= MAX_IOI


def timed_runs(pitches: list[int], onsets: list[float], offsets: list[float]) -> list[tuple[int, int]]:
    """runs() on performed notes in seconds."""
    k = len(pitches)
    linked = [onsets[i + 1] - onsets[i] <= MAX_STEP and onsets[i + 1] - offsets[i] <= MAX_GAP for i in range(k - 1)] + [False]
    found = runs(pitches, linked, [offsets[i] - onsets[i] > MAX_STEP for i in range(k)])
    return [(i, j) for i, j in found if fast(onsets, i, j)]


def with_trills(line: list[dict], split: list[dict]) -> list[dict]:
    """`line` (note dicts in seconds) with each trill run of `split` (the same notes split on the contour) as one note
    {"pitch": lower, "onset", "offset", "trill": semitones}. A note of `line` inside a run goes; one that starts
    before the run ends where it starts, and one that runs on past its end starts where it ends."""
    s = sorted(split, key=lambda n: (n["onset"], n["pitch"]))
    found = timed_runs([n["pitch"] for n in s], [n["onset"] for n in s], [n["offset"] for n in s])
    if not found:
        return line
    spans = []
    for i, j in found:
        # the run's two pitches (its first two notes can be one turn on the same pitch)
        lo, hi = min(n["pitch"] for n in s[i:j + 1]), max(n["pitch"] for n in s[i:j + 1])
        spans.append({"pitch": lo, "onset": s[i]["onset"], "offset": s[j]["offset"], "trill": hi - lo})
    out = []
    for n in line:
        pieces = [dict(n)]
        for t in spans:
            nxt = []
            for p in pieces:
                if p["offset"] <= t["onset"] or p["onset"] >= t["offset"]:
                    nxt.append(p)
                    continue
                if p["onset"] < t["onset"]:
                    nxt.append({**p, "offset": t["onset"]})
                if p["offset"] > t["offset"]:
                    nxt.append({**p, "onset": t["offset"]})
            pieces = nxt
        out += pieces
    return sorted(out + spans, key=lambda n: (n["onset"], n["pitch"]))


def collapse_trills(notes: list) -> list:
    """Written notes (score_model.Note, ticks) with each trill run as one note on the lower pitch (Note.trill set).

    The notes touch on the page (within a 16th), each at most a 16th long but a held last one. The rate comes from
    the performed onsets where every note has one, else from the written grid (16ths or faster). Notes sharing an
    onset (chords) are left alone."""
    ns = sorted(notes, key=lambda n: (n.start, n.pitch))
    if len(ns) < MIN_NOTES:
        return notes
    starts = [n.start for n in ns]
    if len(set(starts)) != len(starts):
        return notes
    # On the page the notes touch (within a 16th); the rate comes from the performed onsets where every note has
    # one, else from the written grid (16ths or faster).
    touch = [ns[i + 1].start - ns[i].end <= MAX_GAP_TICKS for i in range(len(ns) - 1)]
    held = [n.dur > MAX_IOI_TICKS for n in ns]
    if all(n.onset_s is not None for n in ns):
        on = [n.onset_s for n in ns]
        linked = [t and on[i + 1] - on[i] <= MAX_STEP for i, t in enumerate(touch)] + [False]
        found = [(i, j) for i, j in runs([n.pitch for n in ns], linked, held) if fast(on, i, j)]
    else:
        linked = [t and ns[i + 1].start - ns[i].start <= MAX_IOI_TICKS for i, t in enumerate(touch)] + [False]
        found = runs([n.pitch for n in ns], linked, held)
    if not found:
        return notes
    out = []
    k = 0
    for i, j in found:
        out += ns[k:i]
        run = ns[i:j + 1]
        lo, hi = min(n.pitch for n in run), max(n.pitch for n in run)  # a first turn can repeat one pitch
        conf = max(n.confidence for n in run)  # the alternation is as sure as its best-confirmed note
        arts = [a for a in run[-1].articulations if str(getattr(a, "value", a)) == "fermata"]
        out.append(replace(run[0], pitch=lo, dur=run[-1].end - run[0].start, confidence=conf,
                           sources=list(run[0].sources), offset_s=run[-1].offset_s,
                           performed_dur=None if run[0].performed_dur is None or run[-1].performed_dur is None
                           else run[-1].start + run[-1].performed_dur - run[0].start,
                           articulations=arts, trill=hi - lo))
        k = j + 1
    return out + ns[k:]
