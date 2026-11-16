"""What the engine itself suspects about a job's beat, so an app can offer the correction unprompted.

A job's beat grid comes from a beat tracker, and the tracker is the main reason a note is written in the wrong
place: on brass ensembles under half of the notes land on their written position with tracked beats, against
0.95 and more with the true ones. A player can put the grid right (profiles.beat_correction), but only when
the app asks. The hints say where to ask: each is a code, with the correction it suggests when there is one.

They are read from what was written (the grid, the bar, the notes on it), so they cost nothing and describe
the score the player is looking at. They are suspicions, not findings: a hint is worth a question to the
player, never a change on its own.
"""

from __future__ import annotations

import json
from fractions import Fraction
from pathlib import Path

import numpy as np

# The codes, in the order they are reported.
TEMPO_GUESSED = "tempo_guessed"  # under two beats were tracked: the grid is a guess from the notes
TEMPO_SLOW = "tempo_slow"  # the written beat is slower than TEMPO_RANGE: the beat may be twice (or three times) as fast
TEMPO_FAST = "tempo_fast"  # faster than TEMPO_RANGE: the beat may be half as fast
NOTES_FAST = "notes_fast"  # most notes are a quarter of a beat apart or less: the beat may be twice as fast
NOTES_SLOW = "notes_slow"  # most notes are two beats apart or more: the beat may be half as fast
IN_THREE = "in_three"  # the notes divide a slow beat in three: it may be a bar of three counted in one
HELD_NOTES = "held_notes"  # long stretches with no new note: held notes the tracker may have counted through
UNEVEN_BARS = "uneven_bars"  # bars with far more notes than the others: beats may be missing there
DOWNBEAT_UNSURE = "downbeat_unsure"  # another beat of the bar carries more than the first: the bar may start there
TRACKERS_DISAGREE = "trackers_disagree"  # the two beat trackers put their beats in different places
CODES = (TEMPO_GUESSED, TEMPO_SLOW, TEMPO_FAST, NOTES_FAST, NOTES_SLOW, IN_THREE, HELD_NOTES, UNEVEN_BARS,
         DOWNBEAT_UNSURE, TRACKERS_DISAGREE)

TEMPO_RANGE = (50.0, 220.0)  # BPM of the written beat outside which the level is in doubt
FAST_IOI = 0.25  # beats: the median distance between onsets at or under which the notes are fast for the beat
SLOW_IOI = 2.0  # and at or over which they are slow for it
HELD_BEATS = 4.5  # a gap between onsets of this many written beats or more may be a held note
HELD_MAX = 12  # spans reported
UNEVEN_RATIO = 2.5  # a bar with this many times the median bar's onsets
UNEVEN_MIN = 8  # and at least this many
UNEVEN_MAX = 12  # bars reported
DOWNBEAT_RATIO = 1.25  # another beat of the bar with this many times the first beat's weight
DOWNBEAT_BARS = 4  # bars needed to say anything about the downbeat
AGREE_S = 0.07  # two trackers' beats this close are the same beat
AGREE_SHARE = 0.8  # under this share of shared beats the trackers disagree


def agreement(a: np.ndarray, b: np.ndarray) -> float:
    """Share of beats that both trackers have (within AGREE_S), of the beats either has: 1.0 for the same grid,
    about a half when one counts twice as fast."""
    a, b = np.sort(np.asarray(a, dtype=float)), np.sort(np.asarray(b, dtype=float))
    if not len(a) or not len(b):
        return 0.0

    def found(x: np.ndarray, y: np.ndarray) -> int:
        k = np.clip(np.searchsorted(y, x), 1, len(y) - 1) if len(y) > 1 else np.zeros(len(x), int)
        near = np.minimum(np.abs(y[k - 1] - x), np.abs(y[k] - x)) if len(y) > 1 else np.abs(y[0] - x)
        return int(np.sum(near <= AGREE_S))

    return (found(a, b) + found(b, a)) / (len(a) + len(b))


def hints(beat_times, first_downbeat: int, beats_per_bar: int, onsets_s, *, tempo_estimated: bool = False,
          trackers: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
    """The hints for one written score: its beat grid (`beat_times`, with `first_downbeat` the index a bar
    starts at, negative when the first bar starts before the first beat, and `beats_per_bar`) and the times
    its notes were heard at. `trackers`: the two trackers' own beat times, when the job has both.

    Returns {"tempo_bpm", "beats_per_bar", "hints": [{"code", ...}]}; a hint may carry `level` (the level a
    correction would choose, counted from the written beat), `spans` ([[start_s, end_s]]), `bars` (numbers,
    from 1), `first_downbeat_s` and `score` (what was measured)."""
    from scribe_music.quantize import SLOW_BPM, BeatMap, in_three

    t = np.asarray(beat_times, dtype=float)
    on = np.unique(np.round(np.sort(np.asarray(onsets_s, dtype=float)), 3))
    out: list[dict] = []
    if len(t) < 2:
        return {"tempo_bpm": None, "beats_per_bar": int(beats_per_bar), "hints": out}
    bpm = float(60 / np.median(np.diff(t)))
    if tempo_estimated:
        out.append({"code": TEMPO_GUESSED})
    three = bool(len(on)) and bpm < SLOW_BPM and in_three(t, on)
    if bpm < TEMPO_RANGE[0]:
        out.append({"code": TEMPO_SLOW, "level": "triple" if three else "double", "score": round(bpm, 1)})
    elif bpm > TEMPO_RANGE[1]:
        out.append({"code": TEMPO_FAST, "level": "half", "score": round(bpm, 1)})
    at = BeatMap(t).to_beats(on) if len(on) else np.zeros(0)
    ioi = np.diff(at)
    ioi = ioi[ioi > 0.08]
    if len(ioi) >= 8:
        typical = float(np.median(ioi))
        if typical <= FAST_IOI and bpm <= TEMPO_RANGE[1] / 2:
            out.append({"code": NOTES_FAST, "level": "double", "score": round(typical, 2)})
        elif typical >= SLOW_IOI and bpm >= TEMPO_RANGE[0] * 2:
            out.append({"code": NOTES_SLOW, "level": "half", "score": round(typical, 2)})
    if three and bpm >= TEMPO_RANGE[0]:
        out.append({"code": IN_THREE, "level": "triple"})
    gaps = np.where(np.diff(at) >= HELD_BEATS)[0]
    if len(gaps):
        longest = gaps[np.argsort(-np.diff(at)[gaps], kind="stable")[:HELD_MAX]]
        out.append({"code": HELD_NOTES, "spans": [[round(float(on[i]), 3), round(float(on[i + 1]), 3)] for i in sorted(longest)]})
    per_bar = max(1, int(beats_per_bar))
    bar = np.floor((np.floor(at + 1 / 12) - first_downbeat) / per_bar).astype(int) if len(at) else np.zeros(0, int)
    if len(bar):
        counts = np.bincount(bar - bar.min())
        full = counts[counts > 0]
        crowded = np.where((counts >= UNEVEN_RATIO * np.median(full)) & (counts >= UNEVEN_MIN))[0] + bar.min()
        if len(crowded):  # bar 1 starts on the first downbeat
            out.append({"code": UNEVEN_BARS, "bars": [int(b + 1) for b in crowded[:UNEVEN_MAX]]})
        if per_bar > 1 and len(full) >= DOWNBEAT_BARS:
            # What starts on each beat of the bar: a note counts one, and as much again as it stands alone before
            # the next (up to two beats), as long notes start on strong beats.
            near = np.abs(at - np.round(at)) <= 0.2
            length = np.minimum(2.0, np.diff(at, append=at[-1] + 1.0))
            place = (np.round(at).astype(int) - first_downbeat) % per_bar
            weight = np.array([float(np.sum((1.0 + length)[near & (place == p)])) for p in range(per_bar)])
            best = int(np.argmax(weight))
            if best != 0 and weight[best] >= DOWNBEAT_RATIO * max(weight[0], 1e-9):
                k = first_downbeat + best
                k += per_bar * max(0, -(k // per_bar)) if k < 0 else 0
                if k < len(t):
                    out.append({"code": DOWNBEAT_UNSURE, "first_downbeat_s": round(float(t[k]), 3),
                                "score": round(float(weight[best] / max(weight[0], 1e-9)), 2)})
    if trackers is not None:
        share = agreement(trackers[0], trackers[1])
        if share < AGREE_SHARE:
            out.append({"code": TRACKERS_DISAGREE, "score": round(share, 2)})
    return {"tempo_bpm": round(bpm, 1), "beats_per_bar": per_bar, "hints": out}


def of_score(doc: dict, *, trackers: tuple[np.ndarray, np.ndarray] | None = None) -> dict:
    """hints() for a written score as JSON: a Composition (composition.json) or a tab's notes (tab-notes.json,
    bass-notes.json). Notes without a heard time (an arranged harmony) are placed by where they are written."""
    from scribe_music.quantize import BeatMap

    notes = [n for v in doc["voices"] for n in v["notes"]] if "voices" in doc else list(doc["notes"])
    times = doc.get("beat_times") or []
    first = int(doc.get("first_downbeat", 0))
    per_beat = int(doc.get("ticks_per_beat", 24))
    meter = doc["meters"][0]["beats"] if doc.get("meters") else doc.get("meter", {}).get("beats", 4)
    onsets = [n["onset_s"] for n in notes if n.get("onset_s") is not None]
    written = [n["start"] for n in notes if n.get("onset_s") is None]
    if written and len(times) >= 2:
        onsets += list(BeatMap(np.asarray(times, dtype=float)).to_seconds(first + np.asarray(written, dtype=float) / per_beat))
    return hints(times, first, int(meter), onsets, tempo_estimated=bool(doc.get("tempo_estimated")), trackers=trackers)


FILE = "beat-hints.json"
THIS = Path(__file__).resolve()


# The level the engine chose from the notes, by how many written beats there are to one it was given.
CHOSEN = {1: "as-tracked", 2: "double", 3: "triple"}
LEVELS = ("as-tracked", "double", "half", "triple", "third")  # scribe_music.beats.LEVELS


def chosen_level(given: np.ndarray, written) -> str:
    """The level of the `written` beat grid against the beats the notes were put on (`given`: the tracker's, or
    a correction's): as-tracked, double or triple. By the typical beat's length, as cleaning the beats up and
    writing a passage in free time change their number."""
    given, written = np.asarray(given, dtype=float), np.asarray(written, dtype=float)
    if len(given) < 2 or len(written) < 2:
        return CHOSEN[1]
    ratio = float(np.median(np.diff(given)) / np.median(np.diff(written)))
    return CHOSEN.get(int(round(ratio)), CHOSEN[1])


SPEEDS = {"as-tracked": Fraction(1), "double": Fraction(2), "triple": Fraction(3), "half": Fraction(1, 2), "third": Fraction(1, 3)}


def level_to_send(written: str, suggested: str) -> str | None:
    """The level a correction names to follow a hint. A hint's level is counted from the written beat, a
    correction's from the tracked one: on a score written on `double`, a hint of `half` is `as-tracked`.
    None when no level says it (twice as fast as double)."""
    speed = SPEEDS[written] * SPEEDS[suggested]
    return next((name for name, s in SPEEDS.items() if s == speed), None)


def _times(path: Path) -> np.ndarray:
    return np.loadtxt(path, ndmin=2)[:, 0] if path.read_text().strip() else np.zeros(0)


def write(out: Path, doc: dict, read: Path, tracked: Path | None = None, other: Path | None = None) -> dict:
    """Write `out`/beat-hints.json for the score `doc`, written on the beats of `read`: the hints, and `level`,
    the level the engine chose from the notes. `tracked` and `other`: the two trackers' beat files, when the job
    has both."""
    trackers = (_times(tracked), _times(other)) if tracked is not None and other is not None else None
    found = of_score(doc, trackers=trackers)
    found["level"] = chosen_level(_times(read), doc.get("beat_times") or [])
    (out / FILE).write_text(json.dumps(found, indent=1))
    return found
