"""The bass-tab profile: a bass line written as tablature.

    beats                        Beat This! on the recording
    stems                        BS-RoFormer SW, as in pop-rock (a song separated for either profile is
                                 separated once); left out when the recording is the bass alone
    transcribe.bass.basic-pitch  Basic Pitch on the bass stem, or on the recording when it is the bass alone
                                 (then retuned to A = 440 first, as any whole recording: tuning.py)
    notes                        the bottom line on the beat grid with written durations (the shared
                                 quantization and durations), the octave check, meter, key, tempo, and the
                                 recording's offset from A = 440
    arrange                      a string and a fret for every note, and the tab as MusicXML, both from
                                 the Rust crate target-fretted (core/target-fretted)
    export                       PDF and MIDI of that MusicXML through MuseScore, as the band profiles'

The instrument (instrument, tuning, capo, style) is a parameter of the last stage only, so choosing
another tuning for a song fingers it again without transcribing it again. The octave is a parameter of
the notes stage: `auto` runs the octave check, a number of semitones replaces it.

The engine reaches target-fretted through the core's command line (`brasscribe-core fret` for the
fingering, `brasscribe-core tab` for the MusicXML), which passes the crate's JSON requests and responses
through unchanged.

The result is tab.json (schemas.Tab), a composition.json with the one bass voice, tab.musicxml
(export_tab), and tab.pdf and tab.mid when MuseScore is installed.
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


def core_call(command: str, request: dict, cancel: threading.Event | None = None,
              log: Callable[[str], None] | None = None) -> dict:
    """One call of the core's command line: the JSON `request` in, its JSON answer out.

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
            proc = subprocess.Popen([str(cli), command, "--request", str(req), "--out", str(out)], stdin=subprocess.DEVNULL,
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
        return json.loads(out.read_text())


# ---------------------------------------------------------------- notes

def transcribed_line(raw: list[dict], beats: np.ndarray, octave: str = "auto") -> dict:
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
    bottom = line(raw, 0, 127, top=False)
    if not bottom:
        raise ValueError("no bass notes heard in the recording")
    beats_per_bar = int(Counter(np.diff(downs)).most_common(1)[0][0])
    first_down = int(downs[0])
    onsets = np.array([n["onset"] for n in bottom])
    times = choose_level(beats[:, 0], onsets)
    if len(times) != len(beats):
        beats_per_bar *= 2
        first_down *= 2
    earliest = float(BeatMap(times).to_beats(np.array([onsets.min()]))[0])
    while first_down > earliest + 1e-6:
        first_down -= beats_per_bar
    pickup = first_down * TICKS_PER_BEAT

    written = apply_written(quantize(bottom, times, monophonic=True, auto_level=False), BeatMap(times))
    shift = octave_shift([q.pitch for q, _ in written]) if octave == "auto" else int(octave)
    notes = [{"pitch": int(q.pitch) + shift, "start": int(q.start - pickup), "dur": int(w.dur), "confidence": float(q.confidence),
              "onset_s": float(q.onset_s), "offset_s": float(q.offset_s)} for q, w in written]
    name, fifths = key_of([n["start"] / TICKS_PER_BEAT for n in notes], [n["dur"] / TICKS_PER_BEAT for n in notes],
                          [n["pitch"] for n in notes])
    return {"ticks_per_beat": TICKS_PER_BEAT, "notes": notes, "octave_shift": shift,
            "octave_source": "auto" if octave == "auto" else "chosen",
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
    from brasscribe_eval.score import load_notes

    try:
        doc = transcribed_line(load_notes(ctx.inputs["bass"]), np.loadtxt(ctx.inputs["beats"], ndmin=2),
                               ctx.params.get("octave", "auto"))
    except ValueError as e:
        raise StageFailed(ctx.stage.name, str(e)) from e
    doc["reference_pitch"] = reference_pitch(ctx.inputs["audio"], bool(ctx.params.get("whole_recording")))
    ctx.log(f"{len(doc['notes'])} notes, {doc['meter']['beats']}/{doc['meter']['beat_unit']}, "
            f"{doc['key']['name']}, {doc['tempo_bpm']} BPM")
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


def export_tab(tab: dict, title: str, layout: str, out: Path, tablature: Callable[[dict], dict] = tablature) -> int:
    """Write `tab` as MusicXML to `out`/tab.musicxml, laid out as `layout` (LAYOUTS), in one call of the core.

    The notes are written where tab.json has them, not fingered again. Returns how many notes the
    writer had to move to a start or length it can spell."""
    places = ("pitch", "string", "fret", "alternatives", "out_of_range", "pinned")
    answer = tablature({
        "title": page_title(title),
        "instrument": {"preset": tab["preset"], "capo": tab["instrument"]["capo"]},
        "notes": [{"pitch": n["pitch"], "start": n["start"], "dur": n["dur"], "confidence": n["confidence"]} for n in tab["notes"]],
        "fingering": {"notes": [{k: n[k] for k in places} for n in tab["notes"]]},
        "tempo_bpm": round(tab["tempo_bpm"]),  # the page says a whole number of beats per minute
        "meter": tab["meter"],
        "key": {"fifths": tab["key"]["fifths"], "mode": tab["key"]["mode"]},
        "tab": {"layout": layout}})
    (out / "tab.musicxml").write_text(answer["musicxml"])
    return int(answer["adjusted_notes"])


def arrange_stage(ctx: StageContext) -> None:
    doc = json.loads(ctx.inputs["notes"].read_text())
    layout = ctx.params.get("layout", DEFAULTS["layout"])
    try:
        tab = fingered(doc, ctx.params["fingering"], lambda request: solve(request, ctx.executor.cancel, ctx.log))
        tab["layout"] = layout
        tab["adjusted_notes"] = export_tab(tab, ctx.params["title"], layout, ctx.out,
                                           lambda request: tablature(request, ctx.executor.cancel, ctx.log))
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
    st = [P._beats()]
    if whole:
        bass = Input(SOURCE)
    else:
        # pop-rock's stage, parameter for parameter: the two profiles share its cache entry.
        st.append(Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_sw, adapter="separator",
                        outputs=tuple(f"{s}.wav" for s in P.SW_STEMS)))
        bass = Input("stems", "bass.wav")
    st.append(P._transcribe("bass", "basic-pitch", "bp", bass, None, retune=whole))
    # Only what differs from the defaults, so a job that chooses neither keeps its cache entry.
    heard = {**({"whole_recording": True} if whole else {}), **({"octave": opts["octave"]} if opts["octave"] != "auto" else {})}
    st.append(Stage("notes", "notes", {"beats": Input("beats", "mix.beats"), "audio": Input(SOURCE),
                                       "bass": Input("transcribe.bass.basic-pitch", "bass-bp.mid")},
                    notes_stage, params=heard,
                    code=(S.MUSIC_SRC, S.EVAL_SRC, THIS, tuning.THIS), outputs=("bass-notes.json",)))
    fingering = {"instrument": opts["instrument"], "tuning": opts["tuning"], "capo": opts["capo"], "style": opts["style"]}
    st.append(Stage("arrange", "arrange", {"notes": Input("notes", "bass-notes.json")}, arrange_stage,
                    params={"title": title, "fingering": fingering, "layout": opts["layout"]},
                    # The core binary is part of the cache key: a new target-fretted fingers again.
                    code=(THIS, core_cli_path()), outputs=("composition.json", "tab.json", "tab.musicxml")))
    st.append(Stage("export", "export", {"score": Input("arrange")}, export_stage,
                    params={"musescore": musescore_fingerprint()}, code=(THIS,), outputs=("export.json",)))
    outputs = {"composition.json": ("arrange", "composition.json"), "tab.json": ("arrange", "tab.json"),
               "tab.musicxml": ("arrange", "tab.musicxml"), "tab.pdf": ("export", "tab.pdf"), "tab.mid": ("export", "tab.mid")}
    return Pipeline(PROFILE, "tab", st, outputs, opts)
