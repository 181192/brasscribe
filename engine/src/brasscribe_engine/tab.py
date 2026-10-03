"""The tab profile: what one fretted instrument plays, written as tablature.

`instrument` chooses the instrument, and with it which sound is listened to and how its notes are read:

    bass-4, bass-5, bass-6      one line. The stages, parameters and results are the bass-tab profile's
                                (bass_tab.py), stage for stage, so the two share their cache entries.
    guitar-6, guitar-7, guitar-8
    ukulele, ukulele-baritone   chords and lines. The stages below. All of them are read from the separator's
    mandolin                    guitar stem in a song: it has no stem for a ukulele or a mandolin.

    beats                              Beat This! on the recording
    stems                              BS-RoFormer SW, as in pop-rock and bass-tab; left out when the
                                       recording is the instrument alone
    transcribe.<kind>.basic-pitch      Basic Pitch on the instrument's stem, or on the recording when it is
                                       the instrument alone (then retuned to A = 440 first: tuning.py)
    transcribe.<kind>.swift-f0         SwiftF0 on the same audio. It follows one line, so its opinion counts
                                       only where one note sounds at a time
    notes                              every note heard, cleaned (played_notes), on the beat grid with
                                       written durations; each note's confidence; meter, key and tempo
    arrange                            a string and a fret for every note, and the tab as MusicXML, from the
                                       Rust crate target-fretted
    export                             PDF and MIDI of that MusicXML through MuseScore

The instrument's tuning, capo and style are parameters of `arrange` only. The instrument itself is one of
`notes` too: its range decides which notes it can have played.

The profile's id for older apps is bass-tab, which is this profile with a bass and its own defaults.
"""

from __future__ import annotations

import bisect
import itertools
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from . import bass_tab, tuning
from . import stages as S
from .bass_tab import DOUBT, LAYOUTS, MAX_CAPO, OCTAVES, RECORDINGS, STYLES
from .dag import SOURCE, Input, Pipeline, Stage, StageContext, StageFailed

PROFILE = "tab"
THIS = Path(__file__).resolve()

# instrument -> target-fretted's preset family. A family's presets are "<family>-<tuning>", or the family's
# own name when it has one tuning.
FAMILIES = {"bass-4": "bass-4", "bass-5": "bass-5", "bass-6": "bass-6", "guitar-6": "guitar", "guitar-7": "guitar-7",
            "guitar-8": "guitar-8", "ukulele": "ukulele", "ukulele-baritone": "ukulele-baritone", "mandolin": "mandolin"}
# The tunings of each instrument, the default first. A test checks this table against the crate's presets.
TUNINGS: dict[str, tuple[str, ...]] = {
    **bass_tab.INSTRUMENTS,
    "guitar-6": ("standard", "eb-standard", "d-standard", "c-standard", "drop-d", "drop-c", "drop-b", "dadgad", "open-g",
                 "open-d", "open-e"),
    "guitar-7": ("standard", "eb-standard"),
    "guitar-8": ("standard",),
    "ukulele": ("high-g", "low-g"),
    "ukulele-baritone": ("standard",),
    "mandolin": ("standard",),
}
SINGLE_PRESET = ("ukulele-baritone", "mandolin")  # families whose one preset is the family's name


@dataclass(frozen=True)
class Heard:
    """How an instrument is listened to and its notes are read."""

    kind: str  # names the transcription stages and the voice of the composition
    stem: str  # the separator's stem that carries it in a song
    lowest: int  # the lowest pitch any tuning of the instrument reaches (MIDI)
    highest: int  # the highest fret of its top string in standard tuning
    strings: int
    # Among chords an overtone above this pitch is left out (leftovers): the 12th fret of the top string in
    # standard tuning. The rule was set on guitars (GuitarSet). A ukulele has the same fret of its own top
    # string, and only for a note with the evidence of an overtone (high_with_its_note): on rendered passages it
    # was not chosen on, that made chord precision 0.10 better and kept a melody played above the 12th fret.
    # A mandolin has none (None): there the limit changed nothing that could be measured.
    chord_high: int | None = None
    # A note below the lowest string that is the lower octave of a note in the same strum is left out
    # (fingered). Only where that was measured: a ukulele and a mandolin. On a guitar a note below the lowest
    # string is the sign of a lower tuning (the D of a drop-D power chord is the lower octave of its top
    # note), so there it always stays, flagged, and the tuning suggestions see it.
    low_octaves_out: bool = False
    # The limit of chord_high needs the evidence of an overtone (HIGH_WITH). Not on a guitar, where the limit
    # was measured without it.
    high_with_its_note: bool = False
    # A unison that a strummed open chord plays on two strings is written on both (doubled_unisons).
    unisons_doubled: bool = False
    # The stem it is read from in a song is another instrument's, which may be playing too: taken alone
    # unless the job says it is a song.
    alone_by_default: bool = False
    # The rules for overtones apart from a strum and on top of an open chord (APART_RATIO, DRAG_FRETS) apply:
    # a guitar, where they were measured. On a ukulele and a mandolin they changed notes without making the
    # held-out passages better.
    apart_overtones_out: bool = False


GUITAR_CHORD_HIGH = 76  # E5: the 12th fret of a guitar's top string in standard tuning (six, seven and eight strings alike)

# Guitar ranges: the lowest tuning offered (drop B on six strings, B standard and F# on seven and eight) to
# the 22nd or 24th fret of the top string.
HEARD = {
    "guitar-6": Heard("guitar", "guitar", 35, 86, 6, GUITAR_CHORD_HIGH, apart_overtones_out=True),
    "guitar-7": Heard("guitar", "guitar", 34, 88, 7, GUITAR_CHORD_HIGH, apart_overtones_out=True),
    "guitar-8": Heard("guitar", "guitar", 30, 88, 8, GUITAR_CHORD_HIGH, apart_overtones_out=True),
    # The separator has no stem for a ukulele or a mandolin. Rendered ones under a bass and drums came out in its
    # guitar stem almost whole (recall 0.96) and nowhere else (small_tab_bench). In a song that also has a guitar
    # the two share the stem and the tab holds both, so a song is not their default (alone_by_default).
    "ukulele": Heard("ukulele", "guitar", 55, 87, 4, 69 + 12, True, True, True, True),
    "ukulele-baritone": Heard("ukulele", "guitar", 50, 83, 4, 64 + 12, True, True, True, True),
    "mandolin": Heard("mandolin", "guitar", 55, 96, 4, None, True, False, True, True),
}
DEFAULT_LAYOUT = "tab"
DEFAULT_INSTRUMENT = "guitar-6"

# ---------------------------------------------------------------- how the notes are read (played_notes)
#
# The numbers below were set on GuitarSet's players 00 to 02 and are reported on players 03 to 05
# (eval/brasscribe_eval/guitar_tab_bench.py). Each comment says what share of the notes a rule touches
# were wrong on the players it was set on.

MIN_SECONDS = 0.06  # a shorter note is not one (as the bass line's)
# Notes that start within this of the first of them are one strum: they are written on its onset.
STRUM_SECONDS = 0.05
# A passage is chordal within CHORD_NEAR seconds of an onset where CHORD_SIZE notes start together, each
# heard at STRONG or more. Elsewhere it is a line. The two are read differently: in a chord an octave or
# a fifth over a sounding note is played on purpose, and a faint note may be a real inner voice; in a
# line the same things are overtones and leftovers.
STRONG = 0.4
CHORD_SIZE = 3
CHORD_NEAR = 1.0
# In a line: a note is left out when it is an overtone (the 2nd to 6th partial) of a lower note sounding
# through it, heard at under OVERTONE_RATIO of that note's amplitude (94% wrong), or when Basic Pitch
# heard it at under LINE_FAINT (94% wrong).
OVERTONE_RATIO = 0.6
LINE_FAINT = 0.35
# In a line a note under LINE_DOUBT that SwiftF0 did not hear at that pitch is in doubt (87% wrong).
LINE_DOUBT = 0.45
# Among chords no note is left out. A note is in doubt under CHORD_FAINT (79% wrong), or under CHORD_DOUBT
# when its pitch is not heard again within REPEAT seconds (79% wrong): a chord's notes come back with the
# next strum, a leftover does not.
CHORD_FAINT = 0.35
CHORD_DOUBT = 0.45
REPEAT = 2.0
# Among chords an overtone is told from a played note only at the top of a strum. The top note is left out
# when it is an overtone of a note under it and above the 12th fret of the top string (Heard.chord_high, on
# guitars and ukuleles; on guitars 99% wrong). It is in doubt when it is an overtone heard at under TOP_RATIO of the note
# under it and stands TOP_GAP semitones or more over the rest of the strum (84% wrong): one such note
# would otherwise move the whole chord up the neck.
#
# Every other number here is about the transcriber (how strongly and how long Basic Pitch hears a played
# note) or about intervals, not about a guitar; the instrument's own limits are in Heard.
TOP_RATIO = 0.8
# On a ukulele (Heard.high_with_its_note) a note above the 12th fret is left out only with the evidence of an
# overtone: it starts within HIGH_WITH seconds of a note it is an overtone of, and is heard at under TOP_RATIO
# of it. A melody played up there over a ringing chord starts later than the chord, or as strongly, and stays.
HIGH_WITH = 0.1
TOP_GAP = 9
# An overtone that starts apart from a strum (fewer than APART_SIZE notes start with it) is not a doubling
# played in the chord: it is left out when it is heard at under APART_RATIO of the note under it (92% wrong
# in comping, 95% in the chordal passages of single-line takes).
APART_SIZE = 3
APART_RATIO = 0.6
# A chord is fingered where all its notes can be reached, so one overtone heard on top of an open chord
# moves the whole chord up the neck: an open C comes out at the 8th fret. A player who asks for the
# open-position style has said where the chords are: there such a note (top_overtones) is left out when
# the rest of its chord is fingered DRAG_FRETS or more frets lower without it and then uses an open string
# (DRAG_OPEN_STRINGS): an open chord. Without the open string the rule took as many played notes as
# overtones out of GuitarSet's comping, whose voicings up the neck have a real note on top. In the other
# styles the note always stays.
DRAG_FRETS = 3
DRAG_OPEN_STRINGS = 1
DRAG_STYLE = "open-position"
# The whole passage an octave from where the instrument plays: more than half of its notes outside the
# instrument's range on one side, and OCTAVE_FIT of them inside it an octave the other way.
OCTAVE_FIT = 0.9


# Completing chords (completed_chords), for a job that asks for it. A strum often lacks a note its
# neighbours have: a string the pick missed, or one Basic Pitch did not hear. A note is added to a chord
# when at least COMPLETE_SHARE of the chords around it with the same pitch classes (COMPLETE_REACH on each
# side, within COMPLETE_BEATS, at least COMPLETE_NEED of them) have that pitch. It is marked as inferred
# and gets the "?". Off by default: on the held-out players' comping one added note in five was played (63 of
# 303: the players vary their voicings from strum to strum); on held-out rendered open chords seven in ten
# (32 of 45).
CHORDS = ("heard", "completed")
COMPLETE_SHARE = 0.8
COMPLETE_REACH = 3
COMPLETE_NEED = 2
COMPLETE_BEATS = 8
INFERRED = 0.3  # the confidence of a note that was not heard
DEFAULTS = {**bass_tab.DEFAULTS, "chords": "heard"}


# ---------------------------------------------------------------- options

def given(**values) -> dict:
    """The tab options a job sets, without the ones it leaves out."""
    return {k: v for k, v in values.items() if k in DEFAULTS and v is not None}


def options(params: dict) -> dict:
    """The job's options with the defaults filled in: a six-string guitar in standard tuning, heard in a song."""
    from .profiles import ARRANGEMENT_DEFAULTS

    band = [k for k, default in ARRANGEMENT_DEFAULTS.items() if params.get(k) not in (None, default)]
    if params.get("muscriptor") is False:
        band.append("muscriptor")
    if band:
        raise ValueError(f"{', '.join(band)}: the {PROFILE} profile writes tab for one instrument and takes "
                         f"{', '.join(DEFAULTS)} only")
    instrument = params.get("instrument") or DEFAULT_INSTRUMENT
    if instrument not in TUNINGS:
        raise ValueError(f"instrument must be one of {', '.join(TUNINGS)}")
    defaults = {**DEFAULTS, "instrument": instrument, "tuning": TUNINGS[instrument][0], "layout": DEFAULT_LAYOUT,
                **({"recording": "instrument"} if instrument in HEARD and HEARD[instrument].alone_by_default else {})}
    opts = {k: params[k] if params.get(k) is not None else default for k, default in defaults.items()}
    if opts["tuning"] not in TUNINGS[instrument]:
        raise ValueError(f"tuning of {instrument} must be one of {', '.join(TUNINGS[instrument])}")
    if isinstance(opts["capo"], bool) or not isinstance(opts["capo"], int) or not 0 <= opts["capo"] <= MAX_CAPO:
        raise ValueError(f"capo is a fret, 0 (none) to {MAX_CAPO}")
    for name, allowed in (("style", STYLES), ("recording", RECORDINGS), ("octave", OCTAVES), ("layout", LAYOUTS), ("chords", CHORDS)):
        if opts[name] not in allowed:
            raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    if instrument in bass_tab.INSTRUMENTS:
        if opts.pop("chords") != "heard":
            raise ValueError("chords: a bass line is one note at a time; there are no chords to complete")
    return opts


def refuse_options(profile: str, params: dict) -> None:
    """A profile that writes no tab takes none of the tab options."""
    named = [k for k in DEFAULTS if params.get(k) is not None]
    if named:
        raise ValueError(f"{', '.join(named)}: only the {PROFILE} profile takes this, not {profile}")


def preset(opts: dict) -> str:
    """target-fretted's preset id for the job's instrument and tuning."""
    family = FAMILIES[opts["instrument"]]
    return family if family in SINGLE_PRESET else f"{family}-{opts['tuning']}"


def is_tab(profile: str) -> bool:
    """`profile` writes a tab: this profile, or its id for older apps."""
    return profile in (PROFILE, bass_tab.PROFILE)


def job_options(profile: str, params: dict) -> dict:
    """The validated options of a tab job of either profile id."""
    if profile == bass_tab.PROFILE:
        if params.get("chords") not in (None, "heard"):
            raise ValueError("chords: a bass line is one note at a time; there are no chords to complete")
        return bass_tab.options(params)
    return options(params)


# ---------------------------------------------------------------- notes

def strums(raw: list[dict]) -> list[dict]:
    """`raw` with the notes of one strum on one onset: a pick crossing the strings takes a few hundredths of
    a second, and the grid would otherwise put the top of a chord on the next sixteenth."""
    out, first = [], None
    for n in sorted(raw, key=lambda n: n["onset"]):
        if first is None or n["onset"] - first > STRUM_SECONDS:
            first = n["onset"]
        out.append({**n, "onset": first, "heard_at": n["onset"]} if n["onset"] != first else n)
    return out


def sounding_with(notes: list[dict]) -> list[list[dict]]:
    """For each note of `notes` (sorted by onset), the other notes that sound while it does."""
    onsets = [n["onset"] for n in notes]
    longest = max((n["offset"] - n["onset"] for n in notes), default=0.0)
    out = []
    for n in notes:
        lo, hi = bisect.bisect_left(onsets, n["onset"] - longest), bisect.bisect_left(onsets, n["offset"])
        out.append([o for o in notes[lo:hi] if o is not n and o["offset"] > n["onset"]])
    return out


def chordal(notes: list[dict]) -> list[bool]:
    """For each note of `notes` (sorted by onset): it lies in a chordal passage (STRONG, CHORD_SIZE, CHORD_NEAR)."""
    chords, first, size = [], None, 0
    for n in notes:
        if n.get("amplitude", 1.0) < STRONG:
            continue
        if first is None or n["onset"] - first > STRUM_SECONDS:
            if size >= CHORD_SIZE:
                chords.append(first)
            first, size = n["onset"], 0
        size += 1
    if size >= CHORD_SIZE:
        chords.append(first)
    out = []
    for n in notes:
        i = bisect.bisect_left(chords, n["onset"])
        out.append(any(abs(chords[k] - n["onset"]) <= CHORD_NEAR for k in (i - 1, i) if 0 <= k < len(chords)))
    return out


def leftovers(notes: list[dict], in_chords: list[bool], chord_high: int | None = None,
              with_its_note: bool = False, apart: bool = False) -> tuple[list[int], list[int]]:
    """Indices of the notes of `notes` (sorted by onset) that were not played, and of those that may not have been.

    Left out: in a line, the faint overtones of a note sounding under them and the notes heard too faintly
    to be played ones; among chords, an overtone above `chord_high` (Heard.chord_high) when the instrument
    has one, with `with_its_note` only when it starts with the note under it and is fainter (HIGH_WITH), and a
    faint overtone that does not start with a strum when `apart` (APART_SIZE, APART_RATIO). In doubt: among chords, a faint
    overtone standing over the top of its strum (TOP_RATIO, TOP_GAP)."""
    out, doubt = [], []
    for i, (n, others) in enumerate(zip(notes, sounding_with(notes))):
        amplitude = n.get("amplitude", 1.0)
        half = n["onset"] + 0.5 * (n["offset"] - n["onset"])
        under = [low for low in others if n["pitch"] - low["pitch"] in bass_tab.OVERTONES
                 and low["onset"] <= n["onset"] + bass_tab.OVERTONE_LATE and low["offset"] >= half]

        def fainter(ratio: float) -> bool:
            return any(amplitude < ratio * low.get("amplitude", 1.0) for low in under)

        if not in_chords[i]:
            if fainter(OVERTONE_RATIO) or amplitude < LINE_FAINT:
                out.append(i)
            continue
        together = [o["pitch"] for o in others if abs(o["onset"] - n["onset"]) <= STRUM_SECONDS]
        if under and chord_high is not None and n["pitch"] > chord_high and (not with_its_note or any(
                n["onset"] - low["onset"] <= HIGH_WITH and amplitude < TOP_RATIO * low.get("amplitude", 1.0) for low in under)):
            out.append(i)
        elif apart and len(together) + 1 < APART_SIZE and fainter(APART_RATIO):
            out.append(i)
        elif fainter(TOP_RATIO) and together and n["pitch"] - max(together) >= TOP_GAP:
            doubt.append(i)
    return out, doubt


def top_overtones(notes: list[dict], in_chords: list[bool]) -> list[int]:
    """Indices of the notes of `notes` (sorted by onset) that stand on top of their strum and are an overtone,
    heard at under TOP_RATIO, of a note sounding under them: played, or the ring of the chord. fingered()
    leaves one out when it alone moves its chord up the neck (DRAG_FRETS)."""
    out = []
    for i, (n, others) in enumerate(zip(notes, sounding_with(notes))):
        if not in_chords[i]:
            continue
        half = n["onset"] + 0.5 * (n["offset"] - n["onset"])
        under = [low for low in others if n["pitch"] - low["pitch"] in bass_tab.OVERTONES
                 and low["onset"] <= n["onset"] + bass_tab.OVERTONE_LATE and low["offset"] >= half]
        together = [o["pitch"] for o in others if abs(o["onset"] - n["onset"]) <= STRUM_SECONDS]
        if together and n["pitch"] > max(together) and any(n.get("amplitude", 1.0) < TOP_RATIO * low.get("amplitude", 1.0) for low in under):
            out.append(i)
    return out


def completed_chords(notes: list[dict], strings: int, ticks_per_beat: int) -> list[dict]:
    """The notes to add to the written `notes` so that a chord has what the same chord around it has
    (COMPLETE_*): each as a note of the tab, `inferred` and in doubt. A chord is three or more notes on one
    onset; nothing is added to one that already has `strings` notes or to a line."""
    by: dict[int, list[dict]] = {}
    for n in notes:
        by.setdefault(n["start"], []).append(n)
    chords = [(start, ns) for start, ns in sorted(by.items()) if len(ns) >= CHORD_SIZE]
    added = []
    for i, (start, ns) in enumerate(chords):
        mine = {n["pitch"] for n in ns}
        classes = {p % 12 for p in mine}
        around = [{n["pitch"] for n in other} for j, (at, other) in enumerate(chords)
                  if j != i and abs(j - i) <= COMPLETE_REACH and abs(at - start) <= COMPLETE_BEATS * ticks_per_beat
                  and {n["pitch"] % 12 for n in other} == classes]
        if len(around) < COMPLETE_NEED:
            continue
        count = Counter(p for other in around for p in other)
        room = strings - len(mine)
        for pitch in sorted(p for p, c in count.items() if p not in mine and c / len(around) >= COMPLETE_SHARE)[:max(0, room)]:
            added.append({"pitch": pitch, "start": start, "dur": max(n["dur"] for n in ns), "confidence": INFERRED,
                          "onset_s": float(np.median([n["onset_s"] for n in ns])), "offset_s": float(np.median([n["offset_s"] for n in ns])),
                          "inferred": True})
    return added


def octave_shift(pitches: list[int], heard: Heard) -> int:
    """Semitones to move the whole passage by, when it was heard an octave from where the instrument
    plays: 0, or 12 up or down when more than half of the notes are outside its range on one side and
    OCTAVE_FIT of them are inside it an octave the other way."""
    if not pitches:
        return 0
    p = np.array(pitches)
    for shift, outside in ((-12, p > heard.highest), (12, p < heard.lowest)):
        moved = p + shift
        if np.mean(outside) > 0.5 and np.mean((moved >= heard.lowest) & (moved <= heard.highest)) >= OCTAVE_FIT:
            return shift
    return 0


def confidence(note: dict, in_chord: bool, repeated: bool, second: list[dict] | None) -> float:
    """How sure the note is, 0 to 1; below DOUBT the tab marks it "?".

    In a line SwiftF0 follows the same notes, so a faint note it did not hear at that pitch is in doubt.
    Among chords it follows one of several notes and says nothing about the others: there a note is in
    doubt when Basic Pitch heard it faintly, or rather faintly and only once (`repeated`: its pitch is
    heard again within REPEAT seconds)."""
    amplitude = min(1.0, max(0.0, note.get("amplitude", 1.0)))
    sure = round(0.5 + 0.5 * amplitude, 3)
    doubt = round(min(0.39, amplitude * DOUBT / CHORD_DOUBT), 3)
    if in_chord:
        return doubt if amplitude < CHORD_FAINT or (amplitude < CHORD_DOUBT and not repeated) else sure
    if second and not bass_tab._heard(second, note, note["pitch"]) and amplitude < LINE_DOUBT:
        return doubt
    return sure


def repeated(notes: list[dict]) -> list[bool]:
    """For each note of `notes` (sorted by onset): its pitch starts again within REPEAT seconds, before or after."""
    by_pitch: dict[int, list[float]] = {}
    for n in notes:
        by_pitch.setdefault(n["pitch"], []).append(n["onset"])
    out = []
    for n in notes:
        onsets = by_pitch[n["pitch"]]
        i = bisect.bisect_left(onsets, n["onset"] - REPEAT)
        out.append(any(STRUM_SECONDS < abs(t - n["onset"]) <= REPEAT for t in onsets[i:bisect.bisect_right(onsets, n["onset"] + REPEAT)]))
    return out


def played_notes(raw: list[dict], beats: np.ndarray, instrument: str, octave: str = "auto",
                 second: list[dict] | None = None, clean: bool = True, chords: str = "heard") -> dict:
    """The notes of a chordal instrument on the beat grid: every note heard, not one line.

    `clean` False is Basic Pitch straight to the grid, which the benchmark measures the rules against."""
    from brasscribe_music.durations import apply_written
    from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, quantize
    from brasscribe_music.spelling import key_of

    heard = HEARD[instrument]
    beats = np.asarray(beats, dtype=float).reshape(-1, 2) if np.size(beats) else np.zeros((0, 2))
    if len(beats) < 2:
        raise ValueError(f"only {len(beats)} beat(s) tracked: the recording is too short to write down")
    downs = np.where(beats[:, 1].astype(int) == 1)[0]
    if len(downs) < 2:
        raise ValueError("fewer than two downbeats tracked: no bars to write")
    second = second or None
    notes = sorted((dict(n) for n in raw if n["offset"] - n["onset"] >= MIN_SECONDS), key=lambda n: (n["onset"], n["pitch"]))
    dropped = len(raw) - len(notes)  # too short to be a note: counted with the other leftovers
    if clean and notes:
        gone, unsure = leftovers(notes, chordal(notes), heard.chord_high, heard.high_with_its_note, heard.apart_overtones_out)
        for i in unsure:
            notes[i]["top_overtone"] = True
        for i in top_overtones(notes, chordal(notes)) if heard.apart_overtones_out else ():
            notes[i]["on_top"] = True
        kept = [n for i, n in enumerate(notes) if i not in set(gone)] or notes  # never the whole passage
        dropped += len(notes) - len(kept)
        notes = sorted(strums(kept), key=lambda n: (n["onset"], n["pitch"]))
    if not notes:
        raise ValueError(f"no {heard.kind} notes heard in the recording")
    shift = (octave_shift([n["pitch"] for n in notes], heard) if clean else 0) if octave == "auto" else int(octave)
    if clean:
        for n, in_chord, again in zip(notes, chordal(notes), repeated(notes)):
            n["confidence"] = confidence(n, in_chord, again, second)
            if n.pop("top_overtone", False):
                n["confidence"] = min(n["confidence"], bass_tab.UNCONFIRMED)
    else:
        for n in notes:
            n["confidence"] = 1.0
    onsets = np.array([n["onset"] for n in notes])
    beats_per_bar = int(Counter(np.diff(downs)).most_common(1)[0][0])
    first_down = int(downs[0])
    times = choose_level(beats[:, 0], onsets)
    if len(times) != len(beats):
        beats_per_bar *= 2
        first_down *= 2
    beats_per_bar = bass_tab.bar_beats(beats_per_bar, times, onsets)
    bm = BeatMap(times)
    earliest = float(bm.to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT
    quantized = quantize(notes, times, monophonic=False, auto_level=False)
    starts = sorted({int(q.start) for q in quantized})
    following = dict(zip(starts, starts[1:]))
    heard_at = {(n["onset"], n["pitch"]): n["heard_at"] for n in notes if "heard_at" in n}
    on_top = {(n["onset"], n["pitch"]) for n in notes if n.get("on_top")}
    seen, out = set(), []
    for q, w in apply_written(quantized, bm):
        if (q.start, q.pitch) in seen:  # the same pitch twice on one onset is one note
            continue
        seen.add((q.start, q.pitch))
        out.append({"pitch": int(q.pitch) + shift, "start": int(q.start - pickup),
                    "dur": bass_tab.straight_length(int(q.start), int(w.dur), following.get(int(q.start))) if clean else int(w.dur),
                    "confidence": float(q.confidence), "onset_s": float(heard_at.get((q.onset_s, q.pitch), q.onset_s)), "offset_s": float(q.offset_s),
                    **({"on_top": True} if (q.onset_s, q.pitch) in on_top else {})})
    if chords == "completed" and clean:
        out += completed_chords(out, heard.strings, TICKS_PER_BEAT)
    out.sort(key=lambda n: (n["start"], n["pitch"]))
    name, fifths = key_of([n["start"] / TICKS_PER_BEAT for n in out], [n["dur"] / TICKS_PER_BEAT for n in out],
                          [n["pitch"] for n in out])
    return {"ticks_per_beat": TICKS_PER_BEAT, "notes": out, "octave_shift": shift,
            "octave_source": "auto" if octave == "auto" else "chosen", "octave_notes_moved": 0,
            "leftovers_dropped": dropped,
            "meter": {"beats": beats_per_bar, "beat_unit": 4},
            "key": {"name": name, "fifths": int(fifths), "mode": "minor" if name.endswith("m") else "major"},
            "tempo_bpm": round(float(60 / np.median(np.diff(times))), 1),
            "beat_times": [float(t) for t in times], "first_downbeat": first_down}


def notes_stage(ctx: StageContext) -> None:
    instrument = ctx.params["instrument"]
    try:
        doc = played_notes(bass_tab.load_transcription(ctx.inputs["heard"]), np.loadtxt(ctx.inputs["beats"], ndmin=2),
                           instrument, ctx.params.get("octave", "auto"), bass_tab.load_transcription(ctx.inputs["second"]),
                           chords=ctx.params.get("chords", "heard"))
    except ValueError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    doc["reference_pitch"] = bass_tab.reference_pitch(ctx.inputs["audio"], bool(ctx.params.get("whole_recording")))
    doubtful = sum(n["confidence"] < DOUBT for n in doc["notes"])
    ctx.log(f"{len(doc['notes'])} notes, {doc['meter']['beats']}/{doc['meter']['beat_unit']}, {doc['key']['name']}, "
            f"{doc['tempo_bpm']} BPM; {doc['leftovers_dropped']} overtones and faint notes left out, "
            f"{doubtful} notes in doubt")
    if doc["octave_shift"] and doc["octave_source"] == "auto":
        ctx.log(f"the passage was heard an octave from the instrument: written {doc['octave_shift']:+d} semitones")
    (ctx.out / "tab-notes.json").write_text(json.dumps(doc, indent=1))


# ---------------------------------------------------------------- fingering

def least_wanted(involved: list[int], notes: list[dict]) -> int:
    """Of the notes of a violation, the one to leave out: a doubling that was added before a note that was
    heard, then the least sure, and of equally sure ones the lowest."""
    return min(involved, key=lambda i: (not notes[i].get("doubled", False), notes[i]["confidence"], notes[i]["pitch"]))


# A strummed chord in the first frets (DOUBLE_FRETS) that lacks one string, where one of its notes can be
# played on two strings at once: that note is a unison, struck on both.
DOUBLE_FRETS = 4


def doubled_unisons(notes: list[dict], open_strings: list[int]) -> list[dict]:
    """The notes to add so that a chord's unison is written on both of its strings.

    A ukulele's open G chord (0232) sounds G on two strings, and the transcriber hears one G; written from
    what was heard, the chord has a string left out (02x2). For each onset with one note fewer than the
    instrument has strings (and three or more), a note is added again when it can take two strings with
    every note within DOUBLE_FRETS of the nut (or the capo); of several such notes the one whose shape
    stays lowest, and none when two are as low. The added note has `doubled` set; target-fretted then
    gives each its own string."""
    by: dict[int, list[dict]] = {}
    for n in notes:
        by.setdefault(n["start"], []).append(n)
    count = len(open_strings)
    added = []
    for ns in by.values():
        pitches = [n["pitch"] for n in ns]
        if len(ns) != count - 1 or len(ns) < CHORD_SIZE or len(set(pitches)) != len(pitches):
            continue
        reach = {}  # per note that could be doubled: the highest fret of the lowest such shape
        for i, n in enumerate(ns):
            shapes = [max(p - o for p, o in zip(order, open_strings)) for order in itertools.permutations(pitches + [n["pitch"]])
                      if all(0 <= p - o <= DOUBLE_FRETS for p, o in zip(order, open_strings))]
            if shapes:
                reach[i] = min(shapes)
        lowest = [i for i, fret in reach.items() if fret == min(reach.values())]
        if len(lowest) == 1:
            added.append({**ns[lowest[0]], "doubled": True})
    return added


def fingered(doc: dict, opts: dict, solve: Callable[[dict], dict] = bass_tab.solve) -> dict:
    """tab.json (schemas.Tab) for the notes stage's `doc`, with the instrument of `opts` (options()).

    As the bass line's, with one more step. What was heard can hold more notes on one onset than the
    instrument has strings, or a chord no hand spans: target-fretted, which has by then tried every
    other place for each note, reports those as violations. One note of each violation is then left out
    (least_wanted) and the passage fingered again, until there is no violation: every round leaves out
    at least one note, so it ends, and the tab that is written can be played.

    On a ukulele and a mandolin (Heard.low_octaves_out) a note below the lowest string is left out the
    same way when a note an octave or two above it starts with it: Basic Pitch hears a string's lower
    octave as a note of its own, and under a high-G ukulele's chords that is a row of notes the
    instrument does not have. `unplayable_dropped` counts both. The tuning suggestions are then the ones
    made with those notes still there: a low G under a high-G ukulele's chords is also what a low-G
    ukulele sounds like. Any other note below the instrument stays, flagged out of range, on every
    instrument: it says the tuning or the instrument may be another.

    In the open-position style an overtone on top of a chord that alone moves it up the neck is left
    out (DRAG_FRETS), counted in `leftovers_dropped`."""
    low_octaves_out = HEARD[opts["instrument"]].low_octaves_out
    unisons_doubled = HEARD[opts["instrument"]].unisons_doubled

    def playable(notes: list[dict], unisons: bool) -> tuple[list[dict], list[dict], dict, int, list | None]:
        dropped, suggestions = 0, None
        while True:
            answer = solve({"instrument": {"preset": preset(opts), "capo": opts["capo"]},
                            "notes": [{"pitch": n["pitch"], "start": n["start"], "dur": n["dur"]} for n in notes],
                            "options": {"style": opts["style"], "tempo_bpm": doc["tempo_bpm"]}})
            places = answer["fingering"]["notes"]
            if len(places) != len(notes):
                raise RuntimeError(f"target-fretted placed {len(places)} notes of {len(notes)}")
            out: set[int] = set()
            for v in answer["violations"]:
                named = [v["note"]] if "note" in v else v.get("notes", [])
                involved = [i for i in named if isinstance(i, int) and 0 <= i < len(notes) and i not in out]
                if involved:
                    out.add(least_wanted(involved, notes))
            if answer["violations"] and not out:  # a violation that names no note cannot be answered by leaving one out
                raise RuntimeError(f"target-fretted reports a violation without a note: {answer['violations'][0].get('kind')}")
            lowest = min(s_["open_pitch"] for s_ in answer["instrument"]["tuning"]["strings"]) + answer["instrument"]["capo"]
            together: dict[int, set[int]] = {}
            for n in notes:
                together.setdefault(n["start"], set()).add(n["pitch"])
            low = {i for i, (n, place) in enumerate(zip(notes, places)) if place["out_of_range"] and n["pitch"] < lowest
                   and together[n["start"]] & {n["pitch"] + 12, n["pitch"] + 24}} if low_octaves_out else set()
            if low and suggestions is None:
                suggestions = answer["tuning_suggestions"]
            out |= low
            if not out and unisons:  # once, when what was heard is playable: the unisons, and the fingering again with them
                unisons = False
                more = doubled_unisons(notes, [s_["open_pitch"] + answer["instrument"]["capo"] for s_ in answer["instrument"]["tuning"]["strings"]])
                if more:
                    notes = sorted(notes + more, key=lambda n: (n["start"], n["pitch"]))
                    continue
            if not out:
                # A doubling that did not get a string of its own is not written.
                taken = {(n["start"], place["string"]) for n, place in zip(notes, places) if not n.get("doubled")}
                keep = [i for i, (n, place) in enumerate(zip(notes, places)) if not n.get("doubled") or (n["start"], place["string"]) not in taken]
                return [notes[i] for i in keep], [places[i] for i in keep], answer, dropped, suggestions
            dropped += sum(not notes[i].get("doubled") for i in out)
            notes = [n for i, n in enumerate(notes) if i not in out]

    def hands(notes: list[dict], places: list[dict]) -> dict[int, int]:
        """The lowest fretted fret of each onset; 0 where every note is on an open string."""
        out: dict[int, int] = {}
        for n, place in zip(notes, places):
            fret = place.get("fret") or 0
            if fret and (n["start"] not in out or not out[n["start"]] or fret < out[n["start"]]):
                out[n["start"]] = fret
            out.setdefault(n["start"], 0)
        return out

    notes, places, answer, dropped, suggestions = playable(list(doc["notes"]), unisons_doubled)
    dragging = 0
    if DRAG_FRETS and opts["style"] == DRAG_STYLE and any(n.get("on_top") for n in notes):
        # playable() can leave notes of `rest` out: pair the places with the notes it kept, not with `rest`.
        rest, rest_places = playable([n for n in notes if not n.get("on_top")], False)[:2]
        with_top, without = hands(notes, places), hands(rest, rest_places)
        open_strings: dict[int, int] = {}
        for n, place in zip(rest, rest_places):
            open_strings[n["start"]] = open_strings.get(n["start"], 0) + (place.get("fret") == 0)
        drags = {(n["start"], n["pitch"]) for n in notes if n.get("on_top") and n["start"] in without
                 and with_top[n["start"]] - without[n["start"]] >= DRAG_FRETS and open_strings[n["start"]] >= DRAG_OPEN_STRINGS}
        if drags:
            dragging = len(drags)
            notes, places, answer, dropped, _ = playable([n for n in doc["notes"] if (n["start"], n["pitch"]) not in drags], unisons_doubled)
    notes = [{k: v for k, v in n.items() if k != "on_top"} for n in notes]
    return {"preset": preset(opts), "style": opts["style"], "instrument": answer["instrument"],
            "notes": [{**n, **place} for n, place in zip(notes, places)],
            "violations": answer["violations"],
            "tuning_suggestions": answer["tuning_suggestions"] if suggestions is None else suggestions,
            "octave_shift": doc["octave_shift"], "octave_source": doc["octave_source"],
            "octave_notes_moved": sum(n.get("octave_moved", False) for n in notes),
            **({"doubled_notes": sum(n.get("doubled", False) for n in notes)} if unisons_doubled else {}),
            "inferred_notes": sum(n.get("inferred", False) for n in notes),
            "unplayable_dropped": dropped, "leftovers_dropped": doc.get("leftovers_dropped", 0) + dragging,
            "reference_pitch": doc["reference_pitch"],
            "tempo_bpm": doc["tempo_bpm"], "key": doc["key"], "meter": doc["meter"],
            "ticks_per_beat": doc["ticks_per_beat"], "beat_times": doc["beat_times"],
            "first_downbeat": doc["first_downbeat"]}


def composition(tab: dict, title: str, kind: str):
    """The canonical score of the tab: one voice named after the instrument, at the pitches the tab is written at."""
    from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

    notes = [Note(n["pitch"], n["start"], n["dur"], n["confidence"], [kind], n["onset_s"], n["offset_s"]) for n in tab["notes"]]
    return Composition(title, [Voice(kind, VoiceRole.HARMONY, notes)],
                       [Meter(0, tab["meter"]["beats"], tab["meter"]["beat_unit"])],
                       [KeySig(0, tab["key"]["fifths"], tab["key"]["mode"])], tab["beat_times"], tab["first_downbeat"])


def arrange_stage(ctx: StageContext) -> None:
    doc = json.loads(ctx.inputs["notes"].read_text())
    layout, opts = ctx.params["layout"], ctx.params["fingering"]
    try:
        tab = fingered(doc, opts, lambda request: bass_tab.solve(request, ctx.executor.cancel, ctx.log))
        tab["layout"] = layout
        tab["adjusted_notes"] = bass_tab.export_tab(tab, ctx.params["title"], layout, ctx.out,
                                                    lambda request: bass_tab.tablature(request, ctx.executor.cancel, ctx.log))
        bass_tab.export_text(tab, ctx.params["title"], ctx.out,
                             lambda request, fmt, lang: bass_tab.tab_text(request, fmt, lang, ctx.executor.cancel, ctx.log))
    except RuntimeError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    unplayable = sum(n["out_of_range"] for n in tab["notes"])
    ctx.log(f"{len(tab['notes'])} notes on {tab['preset']}, {unplayable} out of range, {tab['unplayable_dropped']} left out as "
            f"unplayable, {len(tab['violations'])} violations")
    (ctx.out / "tab.json").write_text(json.dumps(tab, indent=1))
    composition(tab, ctx.params["title"], HEARD[opts["instrument"]].kind).to_json(ctx.out / "composition.json")


# ---------------------------------------------------------------- the pipeline

def build(title: str, params: dict) -> Pipeline:
    from . import profiles as P

    opts = options(params)
    if opts["instrument"] in bass_tab.INSTRUMENTS:
        # A bass: the bass-tab profile's pipeline, stage for stage, under this profile's name.
        bass = bass_tab.build(title, params)
        return Pipeline(PROFILE, bass.pipeline, bass.stages, bass.outputs, bass.params)
    heard = HEARD[opts["instrument"]]
    whole = opts["recording"] == "instrument"
    st = [P._beats()]
    if whole:
        audio = Input(SOURCE)
    else:
        # pop-rock's and bass-tab's stage, parameter for parameter: a song is separated once for all three.
        st.append(Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_sw, adapter="separator",
                        outputs=tuple(f"{s}.wav" for s in P.SW_STEMS)))
        audio = Input("stems", f"{heard.stem}.wav")
    kind = heard.kind
    st.append(P._transcribe(kind, "basic-pitch", "bp", audio, None, retune=whole))
    st.append(Stage(f"transcribe.{kind}.swift-f0", "transcribe", {"audio": audio}, tuning.transcribe if whole else S.transcribe,
                    adapter="swift-f0", params={"output": f"{kind}-sw.mid"}, outputs=(f"{kind}-sw.mid",),
                    derive=tuning.derive if whole else None))
    listened = {"instrument": opts["instrument"], **({"whole_recording": True} if whole else {}),
                **({"octave": opts["octave"]} if opts["octave"] != "auto" else {}),
                **({"chords": opts["chords"]} if opts["chords"] != "heard" else {})}
    st.append(Stage("notes", "notes", {"beats": Input("beats", "mix.beats"), "audio": Input(SOURCE),
                                       "heard": Input(f"transcribe.{kind}.basic-pitch", f"{kind}-bp.mid"),
                                       "second": Input(f"transcribe.{kind}.swift-f0", f"{kind}-sw.mid")},
                    notes_stage, params=listened,
                    code=(S.MUSIC_SRC, THIS, bass_tab.THIS, tuning.THIS), outputs=("tab-notes.json",)))
    fingering = {"instrument": opts["instrument"], "tuning": opts["tuning"], "capo": opts["capo"], "style": opts["style"]}
    st.append(Stage("arrange", "arrange", {"notes": Input("notes", "tab-notes.json")}, arrange_stage,
                    params={"title": title, "fingering": fingering, "layout": opts["layout"]},
                    code=(THIS, bass_tab.THIS, bass_tab.core_cli_path()),
                    outputs=("composition.json", "tab.json", "tab.musicxml", *bass_tab.TEXT_OUTPUTS)))
    st.append(Stage("export", "export", {"score": Input("arrange")}, bass_tab.export_stage,
                    params={"musescore": bass_tab.musescore_fingerprint()}, code=(bass_tab.THIS,), outputs=("export.json",)))
    outputs = {"composition.json": ("arrange", "composition.json"), "tab.json": ("arrange", "tab.json"),
               "tab.musicxml": ("arrange", "tab.musicxml"), **{name: ("arrange", name) for name in bass_tab.TEXT_OUTPUTS},
               "tab.pdf": ("export", "tab.pdf"), "tab.mid": ("export", "tab.mid")}
    return Pipeline(PROFILE, "tab", st, outputs, opts)
