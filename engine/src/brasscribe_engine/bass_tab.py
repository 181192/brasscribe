"""The bass-tab profile: a bass line written as tablature.

    beats                        Beat This! on the recording
    stems                        BS-RoFormer SW, as in pop-rock (a song separated for either profile is
                                 separated once); left out when the recording is the bass alone
    transcribe.bass.basic-pitch  Basic Pitch on the bass stem, or on the recording when it is the bass alone
                                 (then retuned to A = 440 first, as any whole recording: tuning.py)
    transcribe.bass.swift-f0     SwiftF0 on the same audio: a second opinion, for each note's confidence
    notes                        the bottom line, without the overtones heard as notes, on the beat grid with
                                 written durations (the shared quantization and durations); the octave
                                 check, for the line and for single notes; each note's confidence; meter,
                                 key, tempo, and the recording's offset from A = 440
    arrange                      a string and a fret for every note, and the tab as MusicXML, as plain text
                                 and as playing instructions in words, all from the Rust crate target-fretted
                                 (core/target-fretted)
    export                       PDF and MIDI of that MusicXML through MuseScore, as the band profiles'

The instrument (instrument, tuning, capo, style) is a parameter of the last stage only, so choosing
another tuning for a song fingers it again without transcribing it again. The octave is a parameter of
the notes stage: `auto` runs the octave check, a number of semitones replaces it.

The engine reaches target-fretted through the core's command line (`brasscribe-core fret` for the
fingering, `brasscribe-core tab` for the MusicXML), which passes the crate's JSON requests and responses
through unchanged.

The result is tab.json (schemas.Tab), a composition.json with the one bass voice, tab.musicxml
(export_tab), the same tab as text for a monospace font (tab.txt) and in words for a screen reader or a
braille display (tab-instructions.en.txt and .nb.txt; export_text), and tab.pdf and tab.mid when MuseScore
is installed.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from collections import Counter
from pathlib import Path
from typing import Callable

import numpy as np

from . import stages as S
from . import tuning
from .adapters import kill_tree
from .config import REPO_ROOT, child_env
from .dag import SOURCE, Input, Pipeline, Stage, StageContext, StageFailed

PROFILE = "bass-tab"
THIS = Path(__file__).resolve()

# The instruments and their tunings: target-fretted's presets are "<instrument>-<tuning>", standard first.
# A test checks this table against the crate.
INSTRUMENTS: dict[str, tuple[str, ...]] = {
    "bass-4": ("standard", "eb-standard", "d-standard", "drop-d", "bead"),
    "bass-5": ("standard", "drop-a"),
    "bass-6": ("standard",),
}
STYLES = ("as-played", "open-position", "lead")  # target-fretted's Style
# What was recorded: a song the bass is separated from, or the bass alone (no separation).
RECORDINGS = ("song", "instrument")
MAX_CAPO = 12
# Which octave the line is written in: auto lets the octave check decide; the others are the player's
# choice, in semitones from what was heard.
OCTAVES = ("auto", "0", "-12", "+12")
# What the page shows (target-fretted's Layout). A bass part is tab alone unless the player asks for notation.
LAYOUTS = ("tab", "tab-and-notation", "notation")
DEFAULTS = {"instrument": "bass-4", "tuning": "standard", "capo": 0, "style": "as-played", "recording": "song",
            "octave": "auto", "layout": "tab"}

# The octave check. Transcribers hear a bass an octave high when its fundamental is weak (a phone's
# microphone barely carries a low E). The whole line is written an octave lower when its median pitch
# is above OCTAVE_MEDIAN and at least OCTAVE_FIT of its notes stay at or above BASS_LOWEST an octave
# lower. It is decided from what was heard, against one bass for every job: the player's tuning and
# capo do not change which octave the recording is in.
BASS_LOWEST = 28  # E1, the low string of a four-string bass
# A#2. The bass lines of the Slakh excerpts have their median at B1 to G2 (38 to 43), so the same lines
# heard an octave high have it at 50 to 55; this is the middle of the gap.
OCTAVE_MEDIAN = 46
OCTAVE_FIT = 0.9
OCTAVE_MAX_SHIFTS = 2
# Single notes heard an octave high, after the whole line is placed (octave_outliers).
OUTLIER_WINDOW = 4  # neighbours on each side
OUTLIER_ABOVE = 6  # semitones over their median
# Overtones heard as notes (without_overtones): the 2nd to 6th partial above a note that started no later
# than OVERTONE_LATE seconds after it and sounds through OVERTONE_COVER of its length.
OVERTONES = (12, 19, 24, 28, 31)
OVERTONE_LATE = 0.02
OVERTONE_COVER = 0.5
OVERTONE_PLAYED = 0.1  # seconds after the lower note's onset: later than this, and heard by the second transcriber, it was played
STRAY_SECONDS = 0.2  # a stray note is shorter than this (stray_notes)
# Confidence (note_confidence). DOUBT is target-fretted's default threshold for the "?" mark.
DOUBT = 0.4
UNCONFIRMED = 0.3  # the second transcriber did not hear the note at that pitch
AMPLITUDE_DOUBT = 0.4  # Basic Pitch's amplitude below which a note is in doubt when nothing else can say
SECOND_LOWEST = 30  # F#1 (46 Hz): the lowest pitch SwiftF0 hears

CORE_CLI_ENV = "BRASSCRIBE_CORE_CLI"
# How long one fingering may take before it is stopped. A song takes a fraction of a second; the limit
# is for a core that hangs.
FRET_TIMEOUT_S = 600.0
FRET_POLL_S = 0.1  # seconds between checks for a cancelled job or the time limit


# ---------------------------------------------------------------- options

def given(**values) -> dict:
    """The fretted options a job sets, without the ones it leaves out: a job that names none has the
    parameters it had before these options existed."""
    return {k: v for k, v in values.items() if k in DEFAULTS and v is not None}


def refuse_options(profile: str, params: dict) -> None:
    """A profile that writes no tab takes none of the fretted options."""
    named = [k for k in DEFAULTS if params.get(k) is not None]
    if named:
        raise ValueError(f"{', '.join(named)}: only the {PROFILE} profile takes this, not {profile}")


def options(params: dict) -> dict:
    """The job's fretted options with the defaults filled in. Refuses unknown values, a tuning the
    instrument has no preset for, and the brass-band options."""
    from .profiles import ARRANGEMENT_DEFAULTS

    band = [k for k, default in ARRANGEMENT_DEFAULTS.items() if params.get(k) not in (None, default)]
    if params.get("muscriptor") is False:
        band.append("muscriptor")
    if band:
        raise ValueError(f"{', '.join(band)}: the {PROFILE} profile writes tab for one instrument and takes "
                         f"{', '.join(DEFAULTS)} only")
    opts = {k: params[k] if params.get(k) is not None else default for k, default in DEFAULTS.items()}
    if opts["instrument"] not in INSTRUMENTS:
        raise ValueError(f"instrument must be one of {', '.join(INSTRUMENTS)}")
    if opts["tuning"] not in INSTRUMENTS[opts["instrument"]]:
        raise ValueError(f"tuning of {opts['instrument']} must be one of {', '.join(INSTRUMENTS[opts['instrument']])}")
    if isinstance(opts["capo"], bool) or not isinstance(opts["capo"], int) or not 0 <= opts["capo"] <= MAX_CAPO:
        raise ValueError(f"capo is a fret, 0 (none) to {MAX_CAPO}")
    if opts["style"] not in STYLES:
        raise ValueError(f"style must be one of {', '.join(STYLES)}")
    if opts["recording"] not in RECORDINGS:
        raise ValueError(f"recording must be one of {', '.join(RECORDINGS)}")
    if opts["octave"] not in OCTAVES:
        raise ValueError(f"octave must be one of {', '.join(OCTAVES)}")
    if opts["layout"] not in LAYOUTS:
        raise ValueError(f"layout must be one of {', '.join(LAYOUTS)}")
    return opts


def preset(opts: dict) -> str:
    """target-fretted's preset id for the job's instrument and tuning."""
    return f"{opts['instrument']}-{opts['tuning']}"


# ---------------------------------------------------------------- the Rust core

class CoreCliMissing(RuntimeError):
    pass


def _core_cli() -> tuple[Path, str]:
    """Where the core's command line is, or would be, and where that comes from: `env`
    (BRASSCRIBE_CORE_CLI), `checkout` (its release build) or `path`."""
    named = os.environ.get(CORE_CLI_ENV)
    if named:
        return Path(named).expanduser(), "env"
    built = REPO_ROOT / "core" / "target" / "release" / ("brasscribe-core.exe" if os.name == "nt" else "brasscribe-core")
    on_path = None if built.is_file() else shutil.which("brasscribe-core")
    return (Path(on_path), "path") if on_path else (built, "checkout")


def core_cli_path() -> Path:
    return _core_cli()[0]


def core_cli() -> Path:
    """The core's command line; CoreCliMissing says how to get it."""
    cli = core_cli_path()
    if not cli.is_file() or not os.access(cli, os.X_OK):
        # No path in the message: a refused or failed job's error is shown to paired devices too.
        raise CoreCliMissing(f"brasscribe-core not found ({CORE_CLI_ENV}, core/target/release, PATH): build it with "
                             f"`cargo build --release -p brasscribe-cli` in core/")
    return cli


def solve(request: dict, cancel: threading.Event | None = None, log: Callable[[str], None] | None = None) -> dict:
    """target-fretted's answer to its fingering request (core/target-fretted/README.md, JSON)."""
    return core_call("fret", request, cancel, log)


def tablature(request: dict, cancel: threading.Event | None = None, log: Callable[[str], None] | None = None) -> dict:
    """target-fretted's answer to its tablature request: {"musicxml": ..., "adjusted_notes": ...}."""
    return core_call("tab", request, cancel, log)


def tab_text(request: dict, fmt: str, lang: str | None = None, cancel: threading.Event | None = None,
             log: Callable[[str], None] | None = None) -> str:
    """target-fretted's tablature request answered as plain text: `fmt` "text" is the tab for a monospace
    font, "instructions" the tab in words, in `lang` (TEXT_LANGS)."""
    text = core_call("tab", request, cancel, log, ("--format", fmt, *(("--lang", lang) if lang else ())), parse=False)
    if _answered_in_json(text):
        raise RuntimeError("brasscribe-core is too old to write the tab as text: build it again with "
                           "`cargo build --release -p brasscribe-cli` in core/")
    return text


def _answered_in_json(text: str) -> bool:
    """Whether `text` is the tab command's JSON answer: a core from before the text formats ignores the format
    asked for and answers with {"musicxml": ...}. A title may start with a brace; only that answer is refused."""
    if not text.startswith('{"musicxml"'):
        return False
    try:
        return isinstance(json.loads(text), dict)
    except ValueError:
        return False


def core_call(command: str, request: dict, cancel: threading.Event | None = None,
              log: Callable[[str], None] | None = None, args: tuple[str, ...] = (), parse: bool = True):
    """One call of the core's command line: the JSON `request` in, its JSON answer out (or, with `parse` off,
    the text it wrote). `args` follow `--request` and `--out`.

    Setting `cancel` stops the core, and so does FRET_TIMEOUT_S. No error names a path on this computer."""
    cli = core_cli()
    if _core_cli()[1] == "path":
        # Which binary answered matters when it is not the checkout's own. The job's log says where it came
        # from; the path itself goes to the engine's log only (paired devices read the job's).
        if log:
            log("brasscribe-core taken from the PATH")
        print(f"brasscribe-core taken from the PATH: {cli}", file=sys.stderr, flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        req, out = Path(tmp) / "request.json", Path(tmp) / "answer.json"
        req.write_text(json.dumps(request))
        try:
            proc = subprocess.Popen([str(cli), command, "--request", str(req), "--out", str(out), *args], stdin=subprocess.DEVNULL,
                                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, env=child_env())
        except OSError as e:  # not a program this computer can run; the message would name its path
            raise RuntimeError(f"brasscribe-core could not be started ({type(e).__name__}): build it with "
                               f"`cargo build --release -p brasscribe-cli` in core/") from None
        end = time.monotonic() + FRET_TIMEOUT_S
        while True:
            try:
                _, stderr = proc.communicate(timeout=FRET_POLL_S)
                break
            except subprocess.TimeoutExpired:
                if cancel is not None and cancel.is_set():
                    kill_tree(proc)
                    raise RuntimeError(f"brasscribe-core {command} stopped: the job was cancelled") from None
                if time.monotonic() > end:
                    kill_tree(proc)
                    raise RuntimeError(f"brasscribe-core {command} stopped after {FRET_TIMEOUT_S:.0f} s, its time limit") from None
            except BaseException:  # e.g. Ctrl-C in `brasscribe run`: leave no process running
                kill_tree(proc)
                raise
        if proc.returncode != 0:
            raise RuntimeError(f"brasscribe-core {command} failed: {stderr.strip()[-2000:].replace(tmp, '.')}")
        text = out.read_text(encoding="utf-8")
        return json.loads(text) if parse else text


# ---------------------------------------------------------------- notes

def load_transcription(path: Path) -> list[dict]:
    """A transcriber's notes: pitch, onset and offset in seconds, and `amplitude` (0 to 1), the MIDI
    velocity, which Basic Pitch writes from how strongly it heard the note."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(path))
    return [{"pitch": int(n.pitch), "onset": float(n.start), "offset": float(n.end), "amplitude": n.velocity / 127}
            for inst in pm.instruments if not inst.is_drum for n in inst.notes]


def without_overtones(raw: list[dict], second: list[dict] | None = None) -> list[dict]:
    """`raw` without the notes that are an overtone of a lower note sounding through them.

    A transcriber hears a plucked string's partials as notes of their own, starting a little after the
    string does. In a bass line they would cut the real note short and send the hand up the neck.

    A player also plays those intervals over a note that still rings: a popped octave over a slapped
    root, root and octave in eighths, a line moving over a held root. Such a note starts well after the
    lower one (more than OVERTONE_PLAYED after its onset), and the second transcriber, which follows
    one line, hears it at its own pitch: with both signs it is kept. Without a second transcriber
    there is nothing to tell the two apart, and the interval over a sounding note is left out."""
    by_onset = sorted(raw, key=lambda n: n["onset"])
    kept = []
    for n in by_onset:
        half = n["onset"] + OVERTONE_COVER * (n["offset"] - n["onset"])
        under = [low for low in by_onset if low is not n and n["pitch"] - low["pitch"] in OVERTONES
                 and low["onset"] <= n["onset"] + OVERTONE_LATE and low["offset"] >= half]
        played = bool(second) and _heard(second, n, n["pitch"]) and all(n["onset"] - low["onset"] > OVERTONE_PLAYED for low in under)
        if not under or played:
            kept.append(n)
    return kept


def _heard(second: list[dict], note: dict, pitch: int) -> bool:
    """The second transcriber has a note of `pitch` while `note` sounds."""
    return any(s["pitch"] == pitch and s["onset"] < note["offset"] and s["offset"] > note["onset"] for s in second)


def octave_outliers(line: list[dict], second: list[dict] | None) -> list[int]:
    """Indices of the notes of `line` that were heard an octave high, one at a time.

    Two things must agree: the note stands more than OUTLIER_ABOVE over the median of its OUTLIER_WINDOW
    neighbours on each side, and the second transcriber heard the octave below while it sounds and not
    the note's own pitch. Neither is enough alone: a bass line jumps an octave on purpose, and the second
    transcriber has octave errors of its own. Without a second transcriber no note is moved, and a
    passage both transcribers heard high stays where it is."""
    if not second:
        return []
    return [j for j, n in enumerate(line) if _stands_above(line, j) and n["pitch"] - 12 >= BASS_LOWEST
            and _heard(second, n, n["pitch"] - 12) and not _heard(second, n, n["pitch"])]


def stray_notes(line: list[dict], second: list[dict] | None) -> list[int]:
    """Indices of the notes of `line` that are left out as not the bass. All of this must hold: the note
    stands above its neighbours as an octave outlier does, the second transcriber heard neither it nor its
    lower octave, and Basic Pitch heard it faintly (under AMPLITUDE_DOUBT) and briefly (under STRAY_SECONDS).

    A high note that is only unconfirmed stays in the line with a confidence under DOUBT: it may be a
    fill the second transcriber missed, and a wrong note with a "?" is better than a missing fill."""
    if not second:
        return []
    return [j for j, n in enumerate(line) if _stands_above(line, j)
            and not _heard(second, n, n["pitch"]) and not _heard(second, n, n["pitch"] - 12)
            and n.get("amplitude", 1.0) < AMPLITUDE_DOUBT and n["offset"] - n["onset"] < STRAY_SECONDS]


def _stands_above(line: list[dict], j: int) -> bool:
    """Note `j` is more than OUTLIER_ABOVE over the median of its OUTLIER_WINDOW neighbours on each side."""
    lo, hi = max(0, j - OUTLIER_WINDOW), min(len(line), j + OUTLIER_WINDOW + 1)
    around = [line[i]["pitch"] for i in range(lo, hi) if i != j]
    return len(around) >= 2 and line[j]["pitch"] - float(np.median(around)) > OUTLIER_ABOVE


STRAIGHT_LENGTHS = (6, 12, 18, 24, 36, 48, 72, 96)  # ticks: a 16th to a whole note, with the dotted values


def straight_length(start: int, dur: int, next_start: int | None) -> int:
    """`dur`, or the nearest straight value when a note on the 16th grid, followed by one on it, was given a
    triplet's length. The shared durations choose among triplet and straight values alike; under a tab a
    lone triplet value draws a bracket over a line that has no triplets."""
    if dur % 6 == 0 or start % 6 != 0 or (next_start is not None and next_start % 6 != 0):
        return dur
    room = None if next_start is None else next_start - start
    fits = [c for c in STRAIGHT_LENGTHS if room is None or c <= room] or [6]
    return min(fits, key=lambda c: (abs(np.log(c / dur)), c))


def note_confidence(note: dict, second: list[dict] | None) -> float:
    """How sure the note is, 0 to 1; below DOUBT it is one to check (the tab marks it "?").

    With a second transcriber's notes (`second`: SwiftF0 on the same audio), a note it also heard at that
    pitch is sure, the more so the stronger Basic Pitch heard it, and a note it did not hear there is in
    doubt. SwiftF0 hears nothing below SECOND_LOWEST, so the lowest notes of a bass, and every note when
    there is no second transcriber, are judged on Basic Pitch's amplitude alone."""
    amplitude = min(1.0, max(0.0, note.get("amplitude", 1.0)))
    sure = round(0.5 + 0.5 * amplitude, 3)
    if second is None or note["pitch"] < SECOND_LOWEST:
        return sure if amplitude >= AMPLITUDE_DOUBT else round(amplitude * DOUBT / AMPLITUDE_DOUBT, 3)
    return sure if _heard(second, note, note["pitch"]) else UNCONFIRMED


# A bar of two tracked beats whose onsets divide the beat in three is a real two (6/8 counted in two): of
# the onsets off the beat, COMPOUND_SHARE or more lie within COMPOUND_NEAR of a third of the beat, not of a
# half or a quarter, and there are at least COMPOUND_ONSETS of them. The share is above every two-beat-bar
# take of GuitarSet's players 00 to 02 (their highest is 0.75). Swing and shuffles divide the beat in three
# too, but play its second third only (long-short): of the onsets near a third, COMPOUND_BOTH or more lie on
# each of the two. GuitarSet's jazz takes with a share of 0.7 or more put at most 0.10 of them on the first
# third as the tab profile reads their notes (five takes of players 00 to 05: three of the players the rules
# are set on, two held out; shares up to 0.84 when tracked in four), and at most 0.16 as the bass line reads
# them (eight takes: six and two). At lower shares, which COMPOUND_SHARE already turns down, they put up to 0.5
# there.
# A rendered 12/8 shuffle puts 0.02 there, three eighths to the beat 0.5, and a jig's
# long-short-then-three-eighths a third. A 6/8 tune played mostly long-short is read as a shuffle (two simple
# beats, written two bars to the bar of four): the two cannot be told apart by where the onsets fall.
COMPOUND_SHARE = 0.8
COMPOUND_NEAR = 0.07
COMPOUND_ONSETS = 12
COMPOUND_BOTH = 0.25


def compound(beat_times: np.ndarray, onsets: np.ndarray) -> bool:
    """The onsets divide the beats of `beat_times` in three (COMPOUND_*)."""
    from brasscribe_music.quantize import BeatMap

    at = BeatMap(beat_times).to_beats(np.unique(np.round(np.sort(onsets), 2))) % 1.0
    first, second = int(np.sum(np.abs(at - 1 / 3) <= COMPOUND_NEAR)), int(np.sum(np.abs(at - 2 / 3) <= COMPOUND_NEAR))
    thirds = first + second
    twos = int(np.sum((np.abs(at - 0.5) <= COMPOUND_NEAR) | (np.abs(at - 0.25) <= COMPOUND_NEAR) | (np.abs(at - 0.75) <= COMPOUND_NEAR)))
    return (thirds + twos >= COMPOUND_ONSETS and thirds / (thirds + twos) >= COMPOUND_SHARE
            and min(first, second) >= COMPOUND_BOTH * thirds)


def bar_beats(tracked: int, beat_times: np.ndarray | None = None, onsets: np.ndarray | None = None) -> int:
    """Beats in a bar, given the commonest distance between the tracked downbeats (after the level is chosen).

    On one instrument alone the beat tracker often calls every beat, or every other one, a downbeat: on
    GuitarSet's single lines (all in 4/4) it gave bars of one beat in 48% of the takes and of two in 34%,
    and the tab was written in 1/4 or 2/4. A bar of one or two beats is taken as half or a quarter of a
    bar of four, and a bar of eight as two. A bar of two whose beats the onsets divide in three (compound)
    stays two: that is 6/8 counted in two. Any other real 2/4 is written two bars to the bar; three,
    five, six and seven stay as tracked."""
    if tracked == 2 and beat_times is not None and onsets is not None and compound(beat_times, onsets):
        return 2
    return 4 if tracked in (1, 2, 8) else tracked


def transcribed_line(raw: list[dict], beats: np.ndarray, octave: str = "auto", second: list[dict] | None = None) -> dict:
    """The bass line of transcribed notes ({pitch, onset, offset} in seconds) on the beat grid.

    As the bass voice of the song arrangers: the bottom line, quantized as one voice on the level
    the onsets choose, tick 0 on the downbeat at or before the first note, durations as written.
    There is no pitch window, so a line that was heard too high is all there for the octave check.
    `octave` (OCTAVES): auto runs the check, a number is the player's choice. `octave_shift` is what
    every pitch was moved by, and `octave_source` says who decided: auto or chosen."""
    from brasscribe_eval.lead_sheet import line
    from brasscribe_music.durations import apply_written
    from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, choose_level, quantize
    from brasscribe_music.spelling import key_of

    beats = np.asarray(beats, dtype=float).reshape(-1, 2) if np.size(beats) else np.zeros((0, 2))
    if len(beats) < 2:
        raise ValueError(f"only {len(beats)} beat(s) tracked: the recording is too short to write down")
    pos = beats[:, 1].astype(int)
    downs = np.where(pos == 1)[0]
    if len(downs) < 2:
        raise ValueError("fewer than two downbeats tracked: no bars to write")
    second = second or None  # a second transcriber that heard nothing has no opinion
    heard = without_overtones(raw, second)
    bottom = line(heard, 0, 127, top=False)
    if not bottom:
        raise ValueError("no bass notes heard in the recording")
    strays = set(stray_notes(bottom, second))
    bottom = [n for j, n in enumerate(bottom) if j not in strays] or bottom  # never the whole line
    moved = set(octave_outliers(bottom, second)) if octave == "auto" else set()
    bottom = [{**n, "pitch": n["pitch"] - 12} if j in moved else n for j, n in enumerate(bottom)]
    bottom = [{**n, "confidence": note_confidence(n, second)} for n in bottom]
    moved_at = {(n["onset"], n["pitch"]) for j, n in enumerate(bottom) if j in moved}
    beats_per_bar = int(Counter(np.diff(downs)).most_common(1)[0][0])
    first_down = int(downs[0])
    onsets = np.array([n["onset"] for n in bottom])
    times = choose_level(beats[:, 0], onsets)
    if len(times) != len(beats):
        beats_per_bar *= 2
        first_down *= 2
    beats_per_bar = bar_beats(beats_per_bar, times, onsets)
    earliest = float(BeatMap(times).to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT

    written = apply_written(quantize(bottom, times, monophonic=True, auto_level=False), BeatMap(times))
    shift = octave_shift([q.pitch for q, _ in written]) if octave == "auto" else int(octave)
    starts = [int(q.start) for q, _ in written]
    notes = [{"pitch": int(q.pitch) + shift, "start": int(q.start - pickup),
              "dur": straight_length(int(q.start), int(w.dur), starts[i + 1] if i + 1 < len(starts) else None),
              "confidence": float(q.confidence), "onset_s": float(q.onset_s), "offset_s": float(q.offset_s),
              **({"octave_moved": True} if (q.onset_s, q.pitch) in moved_at else {})}
             for i, (q, w) in enumerate(written)]
    name, fifths = key_of([n["start"] / TICKS_PER_BEAT for n in notes], [n["dur"] / TICKS_PER_BEAT for n in notes],
                          [n["pitch"] for n in notes])
    return {"ticks_per_beat": TICKS_PER_BEAT, "notes": notes, "octave_shift": shift,
            "octave_source": "auto" if octave == "auto" else "chosen",
            "octave_notes_moved": sum(n.get("octave_moved", False) for n in notes),
            "overtones_dropped": len(raw) - len(heard), "strays_dropped": len(strays),
            "meter": {"beats": beats_per_bar, "beat_unit": 4},
            "key": {"name": name, "fifths": int(fifths), "mode": "minor" if name.endswith("m") else "major"},
            "tempo_bpm": round(float(60 / np.median(np.diff(times))), 1),
            "beat_times": [float(t) for t in times], "first_downbeat": first_down}


def reference_pitch(audio: Path, whole_recording: bool) -> dict | None:
    """The recording's offset from A = 440 (tuning.estimate); None when it cannot be measured.

    `retuned`: the notes were transcribed from the recording retuned to A = 440, which happens only
    when the recording itself is transcribed (a separated stem is not retuned: tuning.py)."""
    try:
        cents, concentration = tuning.estimate_file(audio)
    except Exception:  # noqa: BLE001 - a file it cannot read has no measurable tuning
        return None
    if concentration < tuning.MIN_CONCENTRATION:
        return None
    return {"cents": round(cents, 1), "concentration": round(concentration, 2),
            "retuned": whole_recording and tuning.decide(cents, concentration) != 0}


def octave_shift(pitches: list[int]) -> int:
    """Semitones to move the whole line by: 0, or whole octaves down when it was heard an octave (or
    two) above where a bass plays (OCTAVE_MEDIAN, OCTAVE_FIT)."""
    shift = 0
    for _ in range(OCTAVE_MAX_SHIFTS if pitches else 0):
        moved = np.array(pitches) + shift
        if np.median(moved) <= OCTAVE_MEDIAN or np.mean(moved - 12 >= BASS_LOWEST) < OCTAVE_FIT:
            break
        shift -= 12
    return shift


def notes_stage(ctx: StageContext) -> None:
    try:
        doc = transcribed_line(load_transcription(ctx.inputs["bass"]), np.loadtxt(ctx.inputs["beats"], ndmin=2),
                               ctx.params.get("octave", "auto"), load_transcription(ctx.inputs["second"]))
    except ValueError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    doc["reference_pitch"] = reference_pitch(ctx.inputs["audio"], bool(ctx.params.get("whole_recording")))
    ctx.log(f"{len(doc['notes'])} notes, {doc['meter']['beats']}/{doc['meter']['beat_unit']}, "
            f"{doc['key']['name']}, {doc['tempo_bpm']} BPM")
    doubtful = sum(n["confidence"] < DOUBT for n in doc["notes"])
    ctx.log(f"{doc['overtones_dropped']} overtones and {doc['strays_dropped']} stray notes left out, {doc['octave_notes_moved']} single notes written an octave "
            f"lower, {doubtful} notes in doubt")
    if doc["octave_shift"] and doc["octave_source"] == "auto":
        ctx.log(f"the line was heard above a bass: written {-doc['octave_shift'] // 12} octave(s) lower")
    (ctx.out / "bass-notes.json").write_text(json.dumps(doc, indent=1))


# ---------------------------------------------------------------- fingering

def fingered(doc: dict, opts: dict, solve: Callable[[dict], dict] = solve) -> dict:
    """tab.json (schemas.Tab) for the notes stage's `doc`, with the instrument of `opts` (options()).

    The notes are target-fretted's, in its order: each note's time and what was heard, then its
    place on the neck. The crate never changes a pitch: a note the instrument cannot play is flagged
    out of range."""
    answer = solve({"instrument": {"preset": preset(opts), "capo": opts["capo"]},
                    "notes": [{"pitch": n["pitch"], "start": n["start"], "dur": n["dur"]} for n in doc["notes"]],
                    "options": {"style": opts["style"], "tempo_bpm": doc["tempo_bpm"]}})
    places = answer["fingering"]["notes"]
    if len(places) != len(doc["notes"]):
        raise RuntimeError(f"target-fretted placed {len(places)} notes of {len(doc['notes'])}")
    return {"preset": preset(opts), "style": opts["style"], "instrument": answer["instrument"],
            "notes": [{**n, **place} for n, place in zip(doc["notes"], places)],
            "violations": answer["violations"], "tuning_suggestions": answer["tuning_suggestions"],
            "octave_shift": doc["octave_shift"], "octave_source": doc["octave_source"],
            "octave_notes_moved": doc.get("octave_notes_moved", 0),
            "reference_pitch": doc["reference_pitch"],
            "tempo_bpm": doc["tempo_bpm"], "key": doc["key"], "meter": doc["meter"],
            "ticks_per_beat": doc["ticks_per_beat"], "beat_times": doc["beat_times"],
            "first_downbeat": doc["first_downbeat"]}


def composition(tab: dict, title: str):
    """The canonical score of the tab: one bass voice, at the pitches the tab is written at."""
    from brasscribe_music.score_model import Composition, KeySig, Meter, Note, Voice, VoiceRole

    notes = [Note(n["pitch"], n["start"], n["dur"], n["confidence"], ["bass"], n["onset_s"], n["offset_s"])
             for n in tab["notes"]]
    return Composition(title, [Voice("bass", VoiceRole.BASS, notes)],
                       [Meter(0, tab["meter"]["beats"], tab["meter"]["beat_unit"])],
                       [KeySig(0, tab["key"]["fifths"], tab["key"]["mode"])], tab["beat_times"], tab["first_downbeat"])


PAGE_TITLE_MAX = 48  # characters: a longer title runs off the page in the tab's header


def page_title(title: str) -> str:
    """The title as the page's header shows it: one line that fits, cut at a word where there is one.
    The job keeps its whole name."""
    title = " ".join("".join(c for c in title if c.isprintable() or c.isspace()).split())
    if len(title) <= PAGE_TITLE_MAX:
        return title
    cut = title[:PAGE_TITLE_MAX - 1]
    word = cut.rfind(" ")
    return (cut[:word] if word >= PAGE_TITLE_MAX // 2 else cut).rstrip() + "…"


def tab_request(tab: dict, title: str, layout: str) -> dict:
    """target-fretted's tablature request for `tab`: the notes where tab.json has them, not fingered again."""
    places = ("pitch", "string", "fret", "alternatives", "out_of_range", "pinned")
    return {
        "title": page_title(title),
        "instrument": {"preset": tab["preset"], "capo": tab["instrument"]["capo"]},
        "notes": [{"pitch": n["pitch"], "start": n["start"], "dur": n["dur"], "confidence": n["confidence"]} for n in tab["notes"]],
        "fingering": {"notes": [{k: n[k] for k in places} for n in tab["notes"]]},
        "tempo_bpm": round(tab["tempo_bpm"]),  # the page says a whole number of beats per minute
        "meter": tab["meter"],
        "key": {"fifths": tab["key"]["fifths"], "mode": tab["key"]["mode"]},
        "tab": {"layout": layout}}


def export_tab(tab: dict, title: str, layout: str, out: Path, tablature: Callable[[dict], dict] = tablature) -> int:
    """Write `tab` as MusicXML to `out`/tab.musicxml, laid out as `layout` (LAYOUTS), in one call of the core.

    The notes are written where tab.json has them, not fingered again. Returns how many notes the
    writer had to move to a start or length it can spell."""
    answer = tablature(tab_request(tab, title, layout))
    (out / "tab.musicxml").write_text(answer["musicxml"])
    return int(answer["adjusted_notes"])


TEXT_TAB = "tab.txt"
TEXT_LANGS = ("en", "nb")  # the languages the playing instructions are written in
TEXT_OUTPUTS = (TEXT_TAB, *(f"tab-instructions.{lang}.txt" for lang in TEXT_LANGS))


def export_text(tab: dict, title: str, out: Path, text: Callable[[dict, str, str | None], str] = tab_text) -> None:
    """Write `tab` as plain text to `out` (TEXT_OUTPUTS): tab.txt, the tab for a monospace font, and the playing
    instructions in each of TEXT_LANGS, the tab in words for a screen reader or a braille display.

    The same request as the MusicXML's, so the same notes in the same places; the layout does not show in text."""
    request = tab_request(tab, title, DEFAULTS["layout"])
    (out / TEXT_TAB).write_text(text(request, "text", None), encoding="utf-8")
    for lang in TEXT_LANGS:
        (out / f"tab-instructions.{lang}.txt").write_text(text(request, "instructions", lang), encoding="utf-8")


def retitled_text(text: str, old: str, new: str, gap: str = "") -> str:
    """A text export with the title `old` in its first line, retitled `new`; `gap` is what follows the title's
    line (the instructions have an empty line there). A text without a title gets one, and loses it for no title."""
    old, new = page_title(old), page_title(new)
    head = f"{old}\n{gap}" if old else ""
    if not text.startswith(head):  # not as it was written: left alone
        return text
    return (f"{new}\n{gap}" if new else "") + text[len(head):]


def arrange_stage(ctx: StageContext) -> None:
    doc = json.loads(ctx.inputs["notes"].read_text())
    layout = ctx.params.get("layout", DEFAULTS["layout"])
    try:
        tab = fingered(doc, ctx.params["fingering"], lambda request: solve(request, ctx.executor.cancel, ctx.log))
        tab["layout"] = layout
        tab["adjusted_notes"] = export_tab(tab, ctx.params["title"], layout, ctx.out,
                                           lambda request: tablature(request, ctx.executor.cancel, ctx.log))
        export_text(tab, ctx.params["title"], ctx.out,
                    lambda request, fmt, lang: tab_text(request, fmt, lang, ctx.executor.cancel, ctx.log))
    except RuntimeError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    unplayable = sum(n["out_of_range"] for n in tab["notes"])
    ctx.log(f"{len(tab['notes'])} notes on {tab['preset']}, {unplayable} out of range, {len(tab['violations'])} violations")
    if tab["adjusted_notes"]:
        ctx.log(f"{tab['adjusted_notes']} notes moved to a start or length that can be written")
    (ctx.out / "tab.json").write_text(json.dumps(tab, indent=1))
    composition(tab, ctx.params["title"]).to_json(ctx.out / "composition.json")


EXPORT_FORMATS = ("pdf", "mid")


def musescore_fingerprint() -> str | None:
    """Which MuseScore would render the tab, for the export stage's cache key: None without one, else a
    digest of where its program is, its size and when it was written. So a run made without MuseScore is
    rendered once it is installed, and again after an update."""
    from brasscribe_music import musescore

    exe = musescore.binary()
    found = shutil.which(exe) if exe else None
    if not found:
        return None
    try:
        st = Path(found).resolve().stat()
    except OSError:
        return None
    return hashlib.sha256(f"{Path(found).resolve()}:{st.st_size}:{st.st_mtime_ns}".encode()).hexdigest()[:16]


def export_stage(ctx: StageContext) -> None:
    """PDF and MIDI of the tab's MusicXML through MuseScore, as the band profiles' export stage.

    MuseScore 4 aborts during shutdown after writing its output, so success is judged by the output
    files, never the exit code. Without MuseScore nothing is rendered, and export.json and the log say so."""
    from brasscribe_music import musescore

    mscore = musescore.binary() if ctx.params.get("musescore") else None  # as the stage was keyed
    written = []
    if mscore:
        dsts = [ctx.out / f"tab.{ext}" for ext in EXPORT_FORMATS]
        missing = musescore.convert_many([(ctx.inputs["score"] / "tab.musicxml", dsts)])
        if missing:
            raise StageFailed(ctx.stage.name, f"MuseScore did not write {missing[0].name}")
        written = [d.name for d in dsts]
    else:
        ctx.log("mscore not found: PDF and MIDI skipped")
    (ctx.out / "export.json").write_text(json.dumps({"musescore": mscore, "written": written,
                                                     "skipped": [] if mscore else [f"tab.{ext}" for ext in EXPORT_FORMATS]},
                                                    indent=1))


# ---------------------------------------------------------------- the pipeline

def build(title: str, params: dict) -> Pipeline:
    from . import profiles as P

    opts = options(params)
    whole = opts["recording"] == "instrument"
    # The adapter's own beat model (final0), as pop-rock: it runs on the computer, on a whole song, and the two
    # profiles share its cache entry. small0 is for what the apps also make on the device.
    st = [P._beats()]
    if whole:
        bass = Input(SOURCE)
    else:
        # pop-rock's stage, parameter for parameter: the two profiles share its cache entry.
        st.append(Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_sw, adapter="separator",
                        outputs=tuple(f"{s}.wav" for s in P.SW_STEMS)))
        bass = Input("stems", "bass.wav")
    st.append(P._transcribe("bass", "basic-pitch", "bp", bass, None, retune=whole))
    # A second opinion on the same audio, for each note's confidence (note_confidence). It is this profile's own
    # stage: beats, stems and Basic Pitch are still the ones pop-rock runs.
    # On a whole recording it hears the same retuned audio as Basic Pitch: two transcribers a few cents apart
    # would round an out-of-tune note to different pitches, and the disagreement would read as doubt.
    st.append(Stage("transcribe.bass.swift-f0", "transcribe", {"audio": bass}, tuning.transcribe if whole else S.transcribe,
                    adapter="swift-f0", params={"output": "bass-sw.mid"}, outputs=("bass-sw.mid",),
                    derive=tuning.derive if whole else None))
    # Only what differs from the defaults, so a job that chooses neither keeps its cache entry.
    heard = {**({"whole_recording": True} if whole else {}), **({"octave": opts["octave"]} if opts["octave"] != "auto" else {})}
    st.append(Stage("notes", "notes", {"beats": Input("beats", "mix.beats"), "audio": Input(SOURCE),
                                       "bass": Input("transcribe.bass.basic-pitch", "bass-bp.mid"),
                                       "second": Input("transcribe.bass.swift-f0", "bass-sw.mid")},
                    notes_stage, params=heard,
                    code=(S.MUSIC_SRC, S.EVAL_SRC, THIS, tuning.THIS), outputs=("bass-notes.json",)))
    fingering = {"instrument": opts["instrument"], "tuning": opts["tuning"], "capo": opts["capo"], "style": opts["style"]}
    st.append(Stage("arrange", "arrange", {"notes": Input("notes", "bass-notes.json")}, arrange_stage,
                    params={"title": title, "fingering": fingering, "layout": opts["layout"]},
                    # The core binary is part of the cache key: a new target-fretted fingers again.
                    code=(THIS, core_cli_path()), outputs=("composition.json", "tab.json", "tab.musicxml", *TEXT_OUTPUTS)))
    st.append(Stage("export", "export", {"score": Input("arrange")}, export_stage,
                    params={"musescore": musescore_fingerprint()}, code=(THIS,), outputs=("export.json",)))
    outputs = {"composition.json": ("arrange", "composition.json"), "tab.json": ("arrange", "tab.json"),
               "tab.musicxml": ("arrange", "tab.musicxml"), **{name: ("arrange", name) for name in TEXT_OUTPUTS},
               "tab.pdf": ("export", "tab.pdf"), "tab.mid": ("export", "tab.mid")}
    return Pipeline(PROFILE, "tab", st, outputs, opts)
