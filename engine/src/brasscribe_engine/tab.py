"""The tab profile: what one fretted instrument plays, written as tablature.

`instrument` chooses the instrument, and with it which sound is listened to and how its notes are read:

    bass-4, bass-5, bass-6      one line. The stages, parameters and results are the bass-tab profile's
                                (bass_tab.py), stage for stage, so the two share their cache entries.
    guitar-6, guitar-7, guitar-8
    ukulele, ukulele-baritone   chords and lines. The stages below.
    mandolin

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
    stem: str | None  # the separator's stem that carries it in a song; None: not known yet
    lowest: int  # the lowest pitch any tuning of the instrument reaches (MIDI)
    highest: int  # the highest fret of its top string in standard tuning
    strings: int
    # Among chords an overtone above this pitch is left out (leftovers). It was measured on guitars only, where it
    # is the 12th fret of the top string in standard tuning; an instrument without a measurement has none.
    chord_high: int | None = None


GUITAR_CHORD_HIGH = 76  # E5: the 12th fret of a guitar's top string in standard tuning (six, seven and eight strings alike)

# Guitar ranges: the lowest tuning offered (drop B on six strings, B standard and F# on seven and eight) to
# the 22nd or 24th fret of the top string.
HEARD = {
    "guitar-6": Heard("guitar", "guitar", 35, 86, 6, GUITAR_CHORD_HIGH),
    "guitar-7": Heard("guitar", "guitar", 34, 88, 7, GUITAR_CHORD_HIGH),
    "guitar-8": Heard("guitar", "guitar", 30, 88, 8, GUITAR_CHORD_HIGH),
    "ukulele": Heard("ukulele", None, 55, 87, 4),
    "ukulele-baritone": Heard("ukulele", None, 50, 83, 4),
    "mandolin": Heard("mandolin", None, 55, 96, 4),
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
# Among chords an overtone is told from a played note only at the top of a strum. On a guitar the top note is
# left out when it is an overtone of a note under it and above the 12th fret of the top string (Heard.chord_high;
# 99% wrong). It is in doubt, on any instrument, when it is an overtone heard at under TOP_RATIO of the note
# under it and stands TOP_GAP semitones or more over the rest of the strum (84% wrong): one such note
# would otherwise move the whole chord up the neck.
#
# Every other number here is about the transcriber (how strongly and how long Basic Pitch hears a played
# note) or about intervals, not about a guitar; the instrument's own limits are in Heard.
TOP_RATIO = 0.8
TOP_GAP = 9
# The whole passage an octave from where the instrument plays: more than half of its notes outside the
# instrument's range on one side, and OCTAVE_FIT of them inside it an octave the other way.
OCTAVE_FIT = 0.9


# ---------------------------------------------------------------- options

def options(params: dict) -> dict:
    """The job's options with the defaults filled in: a six-string guitar in standard tuning, heard in a song.
    A ukulele or mandolin is heard alone by default."""
    from .profiles import ARRANGEMENT_DEFAULTS

    band = [k for k, default in ARRANGEMENT_DEFAULTS.items() if params.get(k) not in (None, default)]
    if params.get("muscriptor") is False:
        band.append("muscriptor")
    if band:
        raise ValueError(f"{', '.join(band)}: the {PROFILE} profile writes tab for one instrument and takes "
                         f"{', '.join(bass_tab.DEFAULTS)} only")
    instrument = params.get("instrument") or DEFAULT_INSTRUMENT
    if instrument not in TUNINGS:
        raise ValueError(f"instrument must be one of {', '.join(TUNINGS)}")
    # An instrument whose stem in a song is not known yet is taken alone unless the job says otherwise.
    alone_only = instrument in HEARD and HEARD[instrument].stem is None
    defaults = {**bass_tab.DEFAULTS, "instrument": instrument, "tuning": TUNINGS[instrument][0], "layout": DEFAULT_LAYOUT,
                **({"recording": "instrument"} if alone_only else {})}
    opts = {k: params[k] if params.get(k) is not None else default for k, default in defaults.items()}
    if opts["tuning"] not in TUNINGS[instrument]:
        raise ValueError(f"tuning of {instrument} must be one of {', '.join(TUNINGS[instrument])}")
    if isinstance(opts["capo"], bool) or not isinstance(opts["capo"], int) or not 0 <= opts["capo"] <= MAX_CAPO:
        raise ValueError(f"capo is a fret, 0 (none) to {MAX_CAPO}")
    for name, allowed in (("style", STYLES), ("recording", RECORDINGS), ("octave", OCTAVES), ("layout", LAYOUTS)):
        if opts[name] not in allowed:
            raise ValueError(f"{name} must be one of {', '.join(allowed)}")
    if alone_only and opts["recording"] == "song":
        raise ValueError(f"recording of {instrument} must be instrument: which of the separator's stems carries it in a "
                         f"song is not measured yet")
    return opts


def refuse_options(profile: str, params: dict) -> None:
    """A profile that writes no tab takes none of the tab options."""
    named = [k for k in bass_tab.DEFAULTS if params.get(k) is not None]
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
    return bass_tab.options(params) if profile == bass_tab.PROFILE else options(params)


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


def leftovers(notes: list[dict], in_chords: list[bool], chord_high: int | None = None) -> tuple[list[int], list[int]]:
    """Indices of the notes of `notes` (sorted by onset) that were not played, and of those that may not have been.

    Left out: in a line, the faint overtones of a note sounding under them and the notes heard too faintly
    to be played ones; among chords, an overtone above `chord_high` (Heard.chord_high) when the instrument
    has one. In doubt: among chords, a faint overtone standing over the top of its strum (TOP_RATIO, TOP_GAP)."""
    out, doubt = [], []
    for i, (n, others) in enumerate(zip(notes, sounding_with(notes))):
        amplitude = n.get("amplitude", 1.0)
        half = n["onset"] + 0.5 * (n["offset"] - n["onset"])
        under = [low for low in others if n["pitch"] - low["pitch"] in bass_tab.OVERTONES
                 and low["onset"] <= n["onset"] + bass_tab.OVERTONE_LATE and low["offset"] >= half]
        if not in_chords[i]:
            if any(amplitude < OVERTONE_RATIO * low.get("amplitude", 1.0) for low in under) or amplitude < LINE_FAINT:
                out.append(i)
        elif under and chord_high is not None and n["pitch"] > chord_high:
            out.append(i)
        elif any(amplitude < TOP_RATIO * low.get("amplitude", 1.0) for low in under):
            together = [o["pitch"] for o in others if abs(o["onset"] - n["onset"]) <= STRUM_SECONDS]
            if together and n["pitch"] - max(together) >= TOP_GAP:
                doubt.append(i)
    return out, doubt


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
                 second: list[dict] | None = None, clean: bool = True) -> dict:
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
    dropped = 0
    if clean and notes:
        gone, unsure = leftovers(notes, chordal(notes), heard.chord_high)
        for i in unsure:
            notes[i]["top_overtone"] = True
        kept = [n for i, n in enumerate(notes) if i not in set(gone)] or notes  # never the whole passage
        dropped = len(notes) - len(kept)
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
    bm = BeatMap(times)
    earliest = float(bm.to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT
    quantized = quantize(notes, times, monophonic=False, auto_level=False)
    starts = sorted({int(q.start) for q in quantized})
    following = dict(zip(starts, starts[1:]))
    heard_at = {(n["onset"], n["pitch"]): n["heard_at"] for n in notes if "heard_at" in n}
    seen, out = set(), []
    for q, w in apply_written(quantized, bm):
        if (q.start, q.pitch) in seen:  # the same pitch twice on one onset is one note
            continue
        seen.add((q.start, q.pitch))
        out.append({"pitch": int(q.pitch) + shift, "start": int(q.start - pickup),
                    "dur": bass_tab.straight_length(int(q.start), int(w.dur), following.get(int(q.start))) if clean else int(w.dur),
                    "confidence": float(q.confidence), "onset_s": float(heard_at.get((q.onset_s, q.pitch), q.onset_s)), "offset_s": float(q.offset_s)})
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


def _second_opinion(ctx: StageContext, transcribe: Callable[[StageContext], None]) -> None:
    """SwiftF0 on the instrument's audio. It refuses to write a file when it hears no note at all (a stem
    of chords and noise can do that): that is no opinion, not a failed job, and an empty file says so."""
    import pretty_midi

    from .adapters import AdapterError

    try:
        transcribe(ctx)
    except AdapterError as e:
        if ctx.executor.cancel.is_set() or "empty notes list" not in str(e):
            raise
        ctx.log("SwiftF0 heard no single line: the notes have no second opinion")
        pretty_midi.PrettyMIDI().write(str(ctx.out / ctx.params["output"]))


def second_opinion(ctx: StageContext) -> None:
    _second_opinion(ctx, S.transcribe)


def second_opinion_retuned(ctx: StageContext) -> None:
    _second_opinion(ctx, tuning.transcribe)


def notes_stage(ctx: StageContext) -> None:
    instrument = ctx.params["instrument"]
    try:
        doc = played_notes(bass_tab.load_transcription(ctx.inputs["heard"]), np.loadtxt(ctx.inputs["beats"], ndmin=2),
                           instrument, ctx.params.get("octave", "auto"), bass_tab.load_transcription(ctx.inputs["second"]))
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
    """Of the notes of a violation, the one to leave out: the least sure, and of equally sure ones the lowest."""
    return min(involved, key=lambda i: (notes[i]["confidence"], notes[i]["pitch"]))


def fingered(doc: dict, opts: dict, solve: Callable[[dict], dict] = bass_tab.solve) -> dict:
    """tab.json (schemas.Tab) for the notes stage's `doc`, with the instrument of `opts` (options()).

    As the bass line's, with one more step. What was heard can hold more notes on one onset than the
    instrument has strings, or a chord no hand spans: target-fretted, which has by then tried every
    other place for each note, reports those as violations. One note of each violation is then left out
    (least_wanted) and the passage fingered again, until there is no violation: every round leaves out
    at least one note, so it ends, and the tab that is written can be played. `unplayable_dropped`
    counts every note left out this way."""
    notes = list(doc["notes"])
    dropped = 0
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
        if not out:
            break
        dropped += len(out)
        notes = [n for i, n in enumerate(notes) if i not in out]
    return {"preset": preset(opts), "style": opts["style"], "instrument": answer["instrument"],
            "notes": [{**n, **place} for n, place in zip(notes, places)],
            "violations": answer["violations"], "tuning_suggestions": answer["tuning_suggestions"],
            "octave_shift": doc["octave_shift"], "octave_source": doc["octave_source"],
            "octave_notes_moved": sum(n.get("octave_moved", False) for n in notes),
            "unplayable_dropped": dropped, "leftovers_dropped": doc.get("leftovers_dropped", 0),
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
    st.append(Stage(f"transcribe.{kind}.swift-f0", "transcribe", {"audio": audio}, second_opinion_retuned if whole else second_opinion,
                    adapter="swift-f0", params={"output": f"{kind}-sw.mid"}, outputs=(f"{kind}-sw.mid",),
                    derive=tuning.derive if whole else None))
    listened = {"instrument": opts["instrument"], **({"whole_recording": True} if whole else {}),
                **({"octave": opts["octave"]} if opts["octave"] != "auto" else {})}
    st.append(Stage("notes", "notes", {"beats": Input("beats", "mix.beats"), "audio": Input(SOURCE),
                                       "heard": Input(f"transcribe.{kind}.basic-pitch", f"{kind}-bp.mid"),
                                       "second": Input(f"transcribe.{kind}.swift-f0", f"{kind}-sw.mid")},
                    notes_stage, params=listened,
                    code=(S.MUSIC_SRC, THIS, bass_tab.THIS, tuning.THIS), outputs=("tab-notes.json",)))
    fingering = {"instrument": opts["instrument"], "tuning": opts["tuning"], "capo": opts["capo"], "style": opts["style"]}
    st.append(Stage("arrange", "arrange", {"notes": Input("notes", "tab-notes.json")}, arrange_stage,
                    params={"title": title, "fingering": fingering, "layout": opts["layout"]},
                    code=(THIS, bass_tab.THIS, bass_tab.core_cli_path()), outputs=("composition.json", "tab.json", "tab.musicxml")))
    st.append(Stage("export", "export", {"score": Input("arrange")}, bass_tab.export_stage,
                    params={"musescore": bass_tab.musescore_fingerprint()}, code=(bass_tab.THIS,), outputs=("export.json",)))
    outputs = {"composition.json": ("arrange", "composition.json"), "tab.json": ("arrange", "tab.json"),
               "tab.musicxml": ("arrange", "tab.musicxml"), "tab.pdf": ("export", "tab.pdf"), "tab.mid": ("export", "tab.mid")}
    return Pipeline(PROFILE, "tab", st, outputs, opts)
