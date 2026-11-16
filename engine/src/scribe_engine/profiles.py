"""Profiles: which pipeline a recording goes through (docs/shared/research/00-summary.md §0).

  solo                    one brass line, no separation. SwiftF0 is the spine,
                          confirmed by MuScriptor or Basic Pitch (pipeline A, solo rule)
  brass-band              brass-only ensemble, no separation: MuScriptor medium +
                          Basic Pitch on the mix, minimal band (pipeline A); with
                          muscriptor=False, Basic Pitch alone (the apps' draft on device)
  pop-rock                full band: BS-RoFormer SW, then per-stem transcription
                          (bass with Basic Pitch), minimal band (pipeline B); a Percussion
                          part plays the pop kit
  orchestra-with-soloist  layered solo-with-band: Mega-53 solo/bass/drums, the
                          orchestra as residual, 18-part brass band (layered)
  tab                     one fretted instrument as tablature (bass, guitar, ukulele, mandolin): its
                          SW stem (or the recording, when it is the instrument alone), Basic Pitch
                          with SwiftF0 as a second opinion, a string and fret per note (tab.py)
  bass-tab                tab with a bass, under the id older apps know (bass_tab.py)
  sheet                   printed music from a picture or a PDF, read into a score (sheet.py); no recording
  sheet-tab               the same page read into tab for one fretted instrument (sheet.py)

In brass-band, Basic Pitch hears the recording retuned to A = 440 when it is out of
tune (tuning.py); not in the draft (muscriptor=False), which follows the device.

Only orchestra-with-soloist is checked end to end against a golden output
(data/golden/mikkel-arranged-band); the other three band profiles are wired from
the same reference modules but have no end-to-end gate yet, and neither has bass-tab.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import stages as S
from . import beat_hints, targets, tuning
from .dag import SOURCE, Input, Pipeline, Stage
from .stages import EVAL_SRC, SYMBOLIC_CODE, THIS


@dataclass(frozen=True)
class Profile:
    name: str
    pipeline: str
    description: str
    validated: bool
    build: callable  # (title, params) -> list[Stage] and outputs
    input: str = "audio"  # what a job of the profile reads: "audio" (a recording) or "pages" (pictures, a PDF)

    @property
    def target(self) -> targets.Target:
        """The target the profile belongs to (targets.py)."""
        return targets.of(self.name)


ARRANGEMENT_DEFAULTS = {"lineup": "full", "difficulty": "faithful", "key": None, "transpose": None,
                        "seat": None, "reads": None, "lead": "lineup"}
LINEUPS = ("full", "minimal", "quartet")
DIFFICULTIES = ("faithful", "standard", "easier")
# Profiles whose recording is arranged without layers (arrange_song): the small band or the quartet only.
# "full" (the apps' default) is made as the small band there, so it is checked as the small band too.
BAND_TAKE_PROFILES = ("brass-band", "pop-rock")


def made_lineup(profile: str, lineup: str | None) -> str:
    """The lineup a job of `profile` asking for `lineup` is actually arranged for."""
    if profile in BAND_TAKE_PROFILES:
        return "quartet" if lineup == "quartet" else "minimal"
    return lineup or ("minimal" if profile == "solo" else "full")


# A solo take has one line and nothing for the other three quartet parts to play.
QUARTET_NEEDS_GROUP = "a quartet needs a recording of the whole group: a solo take has no harmony for the other parts"


class OptionError(ValueError):
    """A job option the engine refuses, with a stable `code` the apps map to their own words (the
    message is English, for logs and Studio). A 422 carries both: {"code": code, "detail": message},
    the code first, so a client that reads only the start of the body still has it."""

    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code


# The codes of OptionError: the refusals a player can meet, and the rest.
QUARTET_NEEDS_GROUP_CODE = "quartet_needs_group"  # a solo take asked for the quartet
PERCUSSION_SOLO_CODE = "percussion_solo"  # a solo take for the percussion seat
SEAT_NO_TUNE_CODE = "seat_no_tune"  # lead=seat where the seat's part cannot carry the tune
READS_NOT_OFFERED_CODE = "reads_not_offered"  # a clef the seat is not offered in
INVALID_OPTIONS_CODE = "invalid_options"  # anything else wrong with the options
CORE_MISSING_CODE = "core_missing"  # a tab profile on an engine without the Rust core's command line
BEAT_INVALID_CODE = "beat_invalid"  # a beat correction the engine cannot read or apply
BEAT_SOURCE_UNAVAILABLE_CODE = "beat_source_unavailable"  # the second beat tracker's beats, on an engine without one
OPTION_ERROR_CODES = (QUARTET_NEEDS_GROUP_CODE, PERCUSSION_SOLO_CODE, SEAT_NO_TUNE_CODE, READS_NOT_OFFERED_CODE,
                      INVALID_OPTIONS_CODE, CORE_MISSING_CODE, BEAT_INVALID_CODE, BEAT_SOURCE_UNAVAILABLE_CODE)


def option_error_code(e: ValueError) -> str:
    return getattr(e, "code", INVALID_OPTIONS_CODE)


def option_error_message(code: str) -> str:
    """The fixed English message a 422 carries for `code`. The exception's own text stays in the engine's
    log: an unexpected ValueError could say more about the engine than a client should see."""
    from scribe_music.instruments import PERCUSSION_SOLO

    return {
        QUARTET_NEEDS_GROUP_CODE: QUARTET_NEEDS_GROUP,
        PERCUSSION_SOLO_CODE: PERCUSSION_SOLO,
        SEAT_NO_TUNE_CODE: "the seat's part can't carry the tune in this lineup: choose another lead",
        READS_NOT_OFFERED_CODE: "the seat's part is not offered in that clef",
        CORE_MISSING_CODE: "this engine cannot write tab: scribe-core is not installed with it (build it with "
                           "`cargo build --release -p scribe-cli` in core/)",
        BEAT_INVALID_CODE: "the beat correction does not fit: level is one of as-tracked, double, half, triple, third "
                           "(phase 0 or 1 with half, 0 to 2 with third), beats_per_bar is 2 to 12, first_downbeat_s "
                           "is a time in the recording, holds are {start_s, end_s, beats} that do not overlap, and "
                           "beats_per_bar and holds come with a level",
        BEAT_SOURCE_UNAVAILABLE_CODE: "this engine has one beat tracker: there are no alternative beats to write on",
    }.get(code, "these job options don't fit together; the engine's log says which one")


# ---------------------------------------------------------------- the beat, as a player corrects it

BEAT_SOURCES = ("tracked", "alternative")
# The adapter of a second beat tracker, whose beats a correction can choose instead (source: alternative).
# None: the engine has one tracker, every job has one beats stage, and the source is refused.
ALTERNATIVE_BEATS: str | None = None
BEAT_FIELDS = ("source", "level", "phase", "beats_per_bar", "first_downbeat_s", "holds")
MAX_HOLDS = 64
MAX_HOLD_BEATS = 16
MIN_BEATS_PER_BAR = 2


def beat_sources() -> tuple[str, ...]:
    """The beats a correction can choose between on this engine."""
    return BEAT_SOURCES if ALTERNATIVE_BEATS else BEAT_SOURCES[:1]


def _number(value, what: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value != value or value in (float("inf"), float("-inf")):
        raise OptionError(f"beat: {what} is a number", BEAT_INVALID_CODE)
    return float(value)


def _whole(value, what: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise OptionError(f"beat: {what} is a whole number", BEAT_INVALID_CODE)
    return value


def within_recording(beat: dict | None, length_s: float | None) -> dict | None:
    """A correction (as beat_correction gives it) held to a recording `length_s` long: a bar that starts, or a
    hold that starts, after the recording ends is refused; a hold that runs past the end is cut at the end.
    Unchanged when the length is not known."""
    if not beat or length_s is None:
        return beat
    if beat.get("first_downbeat_s", 0) >= length_s:
        raise OptionError(f"beat: first_downbeat_s is after the end of the recording ({length_s:.1f} s)", BEAT_INVALID_CODE)
    holds = []
    for h in beat.get("holds", ()):
        if h["start_s"] >= length_s:
            raise OptionError(f"beat: a hold starts at {h['start_s']:g} s, after the end of the recording "
                              f"({length_s:.1f} s)", BEAT_INVALID_CODE)
        holds.append({**h, "end_s": min(h["end_s"], round(length_s, 3))})
    return {**beat, "holds": holds} if holds else beat


def beat_correction(params: dict) -> dict | None:
    """The job's beat correction (`beat` in its parameters) as it is stored and keyed: only what the player
    said, holds in order of time. None for a job without one, and for one that says nothing.

      source            tracked (default) or alternative: which tracker's beats the score is written on
      level             as-tracked, double, half, triple, third; left out, the level is chosen from the notes
      phase             with half or third: which of the first two or three tracked beats is kept (default 0)
      beats_per_bar     2 to 12, on the corrected level
      first_downbeat_s  a time in the recording where a bar starts
      holds             [{start_s, end_s, beats}]: a held note from start_s to end_s is written `beats` beats long

    beats_per_bar and holds count beats, so they come with a level: the one the score is written on (a job's
    beat_hints name it) or another.

    Refuses (OptionError) what does not fit, and the alternative source on an engine with one tracker."""
    from scribe_music.beats import LEVEL_KEEPS, LEVELS, Correction, Hold

    beat = params.get("beat")
    if beat is None:
        return None
    if not isinstance(beat, dict) or set(beat) - set(BEAT_FIELDS):
        raise OptionError(f"beat takes {', '.join(BEAT_FIELDS)} only", BEAT_INVALID_CODE)
    beat = {k: v for k, v in beat.items() if v is not None}
    out: dict = {}
    source = beat.get("source", "tracked")
    if source not in BEAT_SOURCES:
        raise OptionError(f"beat: source must be one of {', '.join(BEAT_SOURCES)}", BEAT_INVALID_CODE)
    if source not in beat_sources():
        raise OptionError(f"beat: this engine has no {source} beats", BEAT_SOURCE_UNAVAILABLE_CODE)
    if source != "tracked":
        out["source"] = source
    if "level" in beat:
        if beat["level"] not in LEVELS:
            raise OptionError(f"beat: level must be one of {', '.join(LEVELS)}", BEAT_INVALID_CODE)
        out["level"] = beat["level"]
    phase = _whole(beat.get("phase", 0), "phase")
    if not 0 <= phase < LEVEL_KEEPS.get(out.get("level"), 1):
        raise OptionError("beat: phase is 0 or 1 with half, 0 to 2 with third, and 0 otherwise", BEAT_INVALID_CODE)
    if phase:
        out["phase"] = phase
    if "beats_per_bar" in beat:
        out["beats_per_bar"] = _whole(beat["beats_per_bar"], "beats_per_bar")
        if not MIN_BEATS_PER_BAR <= out["beats_per_bar"] <= 12:
            raise OptionError(f"beat: beats_per_bar is {MIN_BEATS_PER_BAR} to 12", BEAT_INVALID_CODE)
    if "first_downbeat_s" in beat:
        out["first_downbeat_s"] = _number(beat["first_downbeat_s"], "first_downbeat_s")
        if out["first_downbeat_s"] < 0:
            raise OptionError("beat: first_downbeat_s is a time in the recording, 0 or later", BEAT_INVALID_CODE)
    holds = beat.get("holds", [])
    if not isinstance(holds, (list, tuple)) or len(holds) > MAX_HOLDS:
        raise OptionError(f"beat: holds is a list of at most {MAX_HOLDS}", BEAT_INVALID_CODE)
    rows = []
    for h in holds:
        if not isinstance(h, dict) or set(h) != {"start_s", "end_s", "beats"}:
            raise OptionError("beat: a hold is {start_s, end_s, beats}", BEAT_INVALID_CODE)
        row = {"start_s": _number(h["start_s"], "a hold's start_s"), "end_s": _number(h["end_s"], "a hold's end_s"),
               "beats": _whole(h["beats"], "a hold's beats")}
        if not 0 <= row["start_s"] < row["end_s"] or not 1 <= row["beats"] <= MAX_HOLD_BEATS:
            raise OptionError(f"beat: a hold ends after it starts and is written 1 to {MAX_HOLD_BEATS} beats long",
                              BEAT_INVALID_CODE)
        rows.append(row)
    rows.sort(key=lambda r: (r["start_s"], r["end_s"]))
    if any(a["end_s"] > b["start_s"] for a, b in zip(rows, rows[1:])):
        raise OptionError("beat: holds do not overlap", BEAT_INVALID_CODE)
    if rows:
        out["holds"] = rows
    if ("holds" in out or "beats_per_bar" in out) and "level" not in out:
        # Left to the engine, the level is chosen after the correction, and a count of beats would be read on
        # one level and written on another.
        raise OptionError("beat: holds and beats_per_bar count beats of a level: give level too (the one the "
                          "score is written on is in the job's beat_hints)", BEAT_INVALID_CODE)
    try:  # the reference's own checks, so the two cannot drift apart
        Correction(out.get("level"), out.get("phase", 0), out.get("beats_per_bar"), out.get("first_downbeat_s"),
                   tuple(Hold(**r) for r in rows))
    except ValueError as e:
        raise OptionError(f"beat: {e}", BEAT_INVALID_CODE) from e
    return out or None


def beat_stages(params: dict, model: str | None = None) -> tuple[list[Stage], Input, dict]:
    """The stages that give a job its beats, the file the notes are written on, and what the stage that reads
    it is told.

    Beat This! on the recording; a second tracker beside it when the engine has one (ALTERNATIVE_BEATS); and,
    with a correction, one more stage that applies it to the chosen tracker's beats. The correction is a
    parameter of that stage alone: every model stage keeps its cache entry, so a corrected score is written
    again from the notes that were heard, in seconds.

    The third value is merged into the reading stage's parameters and inputs by `beat_reader`: `given` (what the
    player said, scribe_music.beats.Correction.given) and, with two trackers, both trackers' own beats for
    the hints."""
    from scribe_music.beats import Correction

    st = [_beats(model)]
    beat = beat_correction(params)
    reader: dict = {"params": {}, "inputs": {}}
    if ALTERNATIVE_BEATS:
        st.append(Stage("beats.alternative", "beats", {"audio": Input(SOURCE)}, S.beats_alternative,
                        adapter=ALTERNATIVE_BEATS, outputs=("mix.beats",)))
        reader["inputs"] = {"beats_tracked": Input("beats", "mix.beats"), "beats_alternative": Input("beats.alternative", "mix.beats")}
    if beat is None:
        return st, Input("beats", "mix.beats"), reader
    said = {k: v for k, v in beat.items() if k != "source"}
    st.append(Stage("beats.corrected", "beats", {"beats": Input("beats.alternative" if "source" in beat else "beats", "mix.beats")},
                    S.correct_beats, params={"beat": said}, code=(S.MUSIC_SRC / "beats.py", S.MUSIC_SRC / "quantize.py", THIS),
                    outputs=("mix.beats",)))
    given = Correction(said.get("level"), said.get("phase", 0), said.get("beats_per_bar"), said.get("first_downbeat_s"),
                       tuple(S.hold(h) for h in said.get("holds", ()))).given
    if given:
        reader["params"] = {"beats_given": list(given)}
    return st, Input("beats.corrected", "mix.beats"), reader


def with_beat(opts: dict, params: dict) -> dict:
    """A tab job's options with its beat correction: what its manifest records, and a rerun starts from."""
    beat = beat_correction(params)
    return {**opts, "beat": beat} if beat else opts


def arrangement_options(params: dict) -> dict:
    """The job's arrangement options that differ from the defaults (so a default job keeps its cache keys)."""
    opts = {k: params.get(k) for k in ARRANGEMENT_DEFAULTS if params.get(k) not in (None, ARRANGEMENT_DEFAULTS[k])}
    if opts.get("lineup") not in (None, *LINEUPS):
        raise ValueError(f"lineup must be one of {', '.join(LINEUPS)}")
    if opts.get("difficulty") not in (None, *DIFFICULTIES):
        raise ValueError(f"difficulty must be one of {', '.join(DIFFICULTIES)}")
    if "key" in opts and "transpose" in opts:
        raise ValueError("give key or transpose, not both")
    _check_seat(opts)
    if "transpose" in opts:
        opts["transpose"] = int(opts["transpose"])
        if not -11 <= opts["transpose"] <= 11:
            raise ValueError("transpose is in semitones, -11 to 11")
        if opts["transpose"] == 0:
            del opts["transpose"]
    return opts


def _check_seat(opts: dict) -> None:
    """seat, reads and lead: a known seat, a clef it offers, and a tune it can carry in a band lineup."""
    from scribe_music.instruments import LEADS, SEAT_IDS, check_reads

    seat = opts.get("seat")
    if seat is not None and seat not in SEAT_IDS:
        raise ValueError(f"seat must be one of {', '.join(SEAT_IDS)}")
    try:
        check_reads(seat, opts.get("reads"))
    except ValueError as e:
        raise OptionError(str(e), READS_NOT_OFFERED_CODE if seat is not None and opts.get("reads") in ("treble", "bass")
                          else INVALID_OPTIONS_CODE) from e
    if opts.get("lead") not in (None, *LEADS):
        raise ValueError(f"lead must be one of {', '.join(LEADS)}")
    if opts.get("lead") == "seat" and seat is None:
        raise ValueError("lead=seat needs a seat")


def job_options(profile: str, params: dict) -> dict:
    """arrangement_options, plus what the profile cannot do (the solo profile has no quartet; the tune moves to
    the seat's part in the band lineups only)."""
    from scribe_music.instruments import PERCUSSION_SOLO, lead_lineup, lineup_by_name, seat_by_id

    if sheet.is_sheet(profile):
        opts = sheet.job_options(profile, params)
        if profile == sheet.TAB:
            try:  # before the page is read: the last stage needs the core
                bass_tab.core_cli()
            except bass_tab.CoreCliMissing as e:
                raise OptionError(str(e), CORE_MISSING_CODE) from e
        return opts
    beat_correction(params)
    if tab.is_tab(profile):
        opts = tab.job_options(profile, params)
        try:  # before any model runs: the last stage needs the core
            bass_tab.core_cli()
        except bass_tab.CoreCliMissing as e:
            raise OptionError(str(e), CORE_MISSING_CODE) from e
        return opts
    tab.refuse_options(profile, params)
    opts = arrangement_options(params)
    if profile == "solo" and params.get("lineup") == "quartet":
        raise OptionError(QUARTET_NEEDS_GROUP, QUARTET_NEEDS_GROUP_CODE)
    if profile == "solo" and opts.get("seat") and not seat_by_id(opts["seat"]).reads:
        raise OptionError(PERCUSSION_SOLO, PERCUSSION_SOLO_CODE)
    if profile != "solo" and opts.get("lead") == "seat":
        lineup = made_lineup(profile, params.get("lineup"))
        try:
            lead_lineup(lineup_by_name(lineup), opts["seat"])
        except ValueError as e:
            raise OptionError(str(e), QUARTET_NEEDS_GROUP_CODE if lineup == "quartet" else SEAT_NO_TUNE_CODE) from e
    return opts


def _arrange_params(title: str, params: dict, lineup: str = "full", kit: str = "band", reader: dict | None = None) -> dict:
    """lineup: the profile's lineup when the job does not choose one. kit: the drum kit the Percussion part
    plays (scribe_music.instruments.KITS); set by the profile, not a job option, and passed only when it is
    not the band kit, so the other profiles keep their cache keys. reader: beat_stages' third value."""
    opts = arrangement_options({**params, "lineup": params.get("lineup") or lineup})
    if kit != "band":
        opts["kit"] = kit
    return {"title": title, **({"arrangement": opts} if opts else {}), **((reader or {}).get("params") or {})}


def _beats(model: str | None = None) -> Stage:
    """Beat This! on the recording. `model` is a checkpoint other than the adapter's own (final0): small0 is the
    one the Play apps run on the device. Beats are only reused from the same model: a reuse directory's own
    mix.beats is final0's, and another model's are in beats-<model>/mix.beats."""
    return Stage("beats", "beats", {"audio": Input(SOURCE)}, S.beats, adapter="beat-this",
                 params={"model": model} if model else {},
                 outputs=("mix.beats",), reuse_subdir=f"beats-{model}" if model else ".")


# The transcribers that are retuned to A = 440 first (tuning.py), and only on a whole recording. MuScriptor
# gains on average but loses badly on single pieces (its greedy decoding flips on a few cents); estimates on
# separated stems are unreliable (a stem of an in-tune song can read 30 cents off); and SwiftF0, which
# Basic Pitch confirms in solo and orchestra-with-soloist, is not retuned yet.
RETUNED = ("basic-pitch",)


def _transcribe(layer: str, tool: str, suffix: str, src: Input, reuse_subdir: str | None, retune: bool = False) -> Stage:
    retune = retune and tool in RETUNED
    return Stage(f"transcribe.{layer}.{tool}", "transcribe", {"audio": src}, tuning.transcribe if retune else S.transcribe,
                 adapter=tool, params={"output": f"{layer}-{suffix}.mid"}, outputs=(f"{layer}-{suffix}.mid",),
                 reuse_subdir=reuse_subdir, derive=tuning.derive if retune else None)


def _export(arrange: str, audio: bool) -> Stage:
    """The band score's PDF, MIDI, MP3 and part PDFs. Keyed on the MuseScore that would render them, as the tab's
    export is: a run made without MuseScore is rendered once it is installed, and again after an update."""
    code = S.EXPORT_CODE + ((S.PART_STYLE,) if S.PART_STYLE.exists() else ())
    return Stage("export", "export", {"score": Input(arrange)}, S.export,
                 params={"audio": audio, "musescore": bass_tab.musescore_fingerprint()}, code=code,
                 outputs=("export.json",))


# What every band profile's arrange stage writes.
ARRANGED = ("composition.json", targets.BRASS.musicxml, beat_hints.FILE)


def _outputs(arrange: str) -> dict[str, tuple[str, str]]:
    band = targets.BRASS
    return {
        "composition.json": (arrange, "composition.json"),
        band.musicxml: (arrange, band.musicxml),
        **{name: ("export", name) for name in (*band.rendered, band.file("mp3"))},
        "separation-check.json": (arrange, "separation-check.json"),
        beat_hints.FILE: (arrange, beat_hints.FILE),
        "parts/": (arrange, "parts/"),  # a trailing slash copies every file under that directory
        "parts-pdf/": ("export", "parts/"),  # part PDFs and BRF land next to the part MusicXML
        band.file("brf"): ("export", band.file("brf")),
        "talking-score.json": ("export", "talking-score.json"),
        "talking-score.html": ("export", "talking-score.html"),
        "talking-score.txt": ("export", "talking-score.txt"),
    }


# Layered solo-with-band: the song pipeline (scribe_eval.song_pipeline) as a DAG.
# Stage outputs keep the song pipeline's file names, so an existing output directory
# (mix.beats, stems/, layers/) can seed the cache.
LAYER_TOOLS = {
    "solo": [("muscriptor", "mus"), ("basic-pitch", "bp"), ("swift-f0", "sw")],
    "orchestra": [("muscriptor", "mus")],
    "bass": [("muscriptor", "mus")],
    "drums": [("muscriptor", "mus")],
}


def layered(title: str, params: dict) -> Pipeline:
    beats, written_on, reader = beat_stages(params)
    st = [
        *beats,
        Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_mega53, adapter="mega53",
              outputs=("*.flac", "trumpet.flac", "bass.flac", "drums.flac"), reuse_subdir="stems"),
        Stage("layers", "layers", {"audio": Input(SOURCE), "trumpet": Input("stems", "trumpet.flac"),
                                   "bass": Input("stems", "bass.flac"), "drums": Input("stems", "drums.flac")},
              S.layers, code=(EVAL_SRC / "layers.py", THIS),
              outputs=("solo.wav", "bass.wav", "drums.wav", "orchestra.wav"), reuse_subdir="layers"),
    ]
    arrange_inputs = {"beats": written_on, **reader["inputs"]}
    for layer, tools in LAYER_TOOLS.items():
        for tool, suffix in tools:
            s = _transcribe(layer, tool, suffix, Input("layers", f"{layer}.wav"), "layers")
            st.append(s)
            arrange_inputs[f"{layer}-{suffix}.mid"] = Input(s.name, f"{layer}-{suffix}.mid")
    # Frame-level SwiftF0 contour of the solo stem: where sustained solo notes really end.
    st.append(Stage("contour.solo.swift-f0", "transcribe", {"audio": Input("layers", "solo.wav")}, S.transcribe,
                    adapter="swift-f0-contour", params={"output": "solo-sw.contour.npz"},
                    outputs=("solo-sw.contour.npz",), reuse_subdir="layers"))
    arrange_inputs["solo-sw.contour.npz"] = Input("contour.solo.swift-f0", "solo-sw.contour.npz")
    # Layer audio: energy gate, separation check, dynamics and rehearsal marks read it.
    for layer in LAYER_TOOLS:
        arrange_inputs[f"{layer}.wav"] = Input("layers", f"{layer}.wav")
    st.append(Stage("arrange", "arrange", arrange_inputs, S.arrange_layered, params=_arrange_params(title, params, reader=reader),
                    code=SYMBOLIC_CODE, outputs=ARRANGED))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("orchestra-with-soloist", "layered", st, _outputs("arrange"), params)


def brass_band(title: str, params: dict) -> Pipeline:
    """A whole brass band, no separation: MuScriptor on the mix for the melody, bass and harmony, Basic Pitch
    confirming the melody, arrange_song for the minimal band or the quartet.

    With muscriptor=False it is the draft the Play apps make on the device: Basic Pitch on the mix fills
    every MuScriptor slot, with no melody support (the notes are the same with it; only one model votes), and
    Beat This! small0 gives the beats, as on the device.
    """
    mix = Input(SOURCE)
    full = params.get("muscriptor", True)
    beats, written_on, reader = beat_stages(params, None if full else "small0")
    if full:
        st = [*beats, _transcribe("mix", "muscriptor", "mus", mix, None),
              _transcribe("mix", "basic-pitch", "bp", mix, None, retune=True)]
        notes, support = Input("transcribe.mix.muscriptor", "mix-mus.mid"), {"melody_support": Input("transcribe.mix.basic-pitch", "mix-bp.mid")}
        # A slow beat that a brass ensemble's notes divide in three is a bar counted in one (a 6/4 hymn tune in
        # two): split in three. Not in the draft, which is the reference for the device's.
        reader = {**reader, "params": {**reader["params"], "three": True}}
    else:
        # Not retuned: the draft is the reference for the device's, and the device does not retune.
        st = [*beats, _transcribe("mix", "basic-pitch", "bp", mix, None)]
        notes, support = Input("transcribe.mix.basic-pitch", "mix-bp.mid"), {}
    st.append(Stage("arrange", "arrange", {
        "beats": written_on, **reader["inputs"], "melody": notes, **support, "bass": notes, "harmony0": notes},
        S.arrange_band, params=_arrange_params(title, params, reader=reader), code=SYMBOLIC_CODE, outputs=ARRANGED))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("brass-band", "A", st, _outputs("arrange"), params)


def solo(title: str, params: dict) -> Pipeline:
    """One brass line, no separation, through the layered arranger with only a solo layer.

    The same path the Play apps run on device (Rust arrangeLayersBand): SwiftF0 is the spine,
    confirmed by MuScriptor and Basic Pitch; the SwiftF0 contour gives the note ends; Beat This!
    small0 gives the beats; the minimal band by default. With muscriptor=False (as on device),
    Basic Pitch also fills MuScriptor's confirmation slot. Stage outputs use the layered names, so
    a directory with mix.beats and layers/solo-{sw,bp,mus}.mid, solo-sw.contour.npz can seed the cache.
    The quartet is refused (QUARTET_NEEDS_GROUP).
    """
    if params.get("lineup") == "quartet":
        raise ValueError(QUARTET_NEEDS_GROUP)
    from scribe_music.instruments import PERCUSSION_SOLO, seat_by_id

    if params.get("seat") and not seat_by_id(params["seat"]).reads:
        raise ValueError(PERCUSSION_SOLO)
    mix = Input(SOURCE)
    # small0 on the computer too, not the adapter's own final0, so a solo score made here is the one the device
    # makes. `scribe bench solo-beat-model` measured the two on the 184 single parts of URMP and ChoraleBricks:
    # final0 got the metre right more often (URMP 0.24 -> 0.29, ChoraleBricks 0.43 -> 0.60) and written positions
    # were level, but no difference was significant (sign test p >= 0.12, ChoraleBricks' metre on 15 parts the
    # closest). Measure again on a larger set before letting the computer use final0.
    st, written_on, reader = beat_stages(params, "small0")
    tools = [("swift-f0", "sw"), ("basic-pitch", "bp")] + ([("muscriptor", "mus")] if params.get("muscriptor", True) else [])
    arrange_inputs = {"beats": written_on, **reader["inputs"]}
    for tool, suffix in tools:
        s = _transcribe("solo", tool, suffix, mix, "layers")
        st.append(s)
        arrange_inputs[f"solo-{suffix}.mid"] = Input(s.name, f"solo-{suffix}.mid")
    if "solo-mus.mid" not in arrange_inputs:
        arrange_inputs["solo-mus.mid"] = arrange_inputs["solo-bp.mid"]
    st.append(Stage("contour.solo.swift-f0", "transcribe", {"audio": mix}, S.transcribe, adapter="swift-f0-contour",
                    params={"output": "solo-sw.contour.npz"}, outputs=("solo-sw.contour.npz",), reuse_subdir="layers"))
    arrange_inputs["solo-sw.contour.npz"] = Input("contour.solo.swift-f0", "solo-sw.contour.npz")
    # A solo take with a seat is written on the seat's part: the tune is always the player's.
    if params.get("seat"):
        params = {**params, "lead": "seat"}
    st.append(Stage("arrange", "arrange", arrange_inputs, S.arrange_layered, params=_arrange_params(title, params, "minimal", reader=reader),
                    code=SYMBOLIC_CODE, outputs=ARRANGED))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("solo", "layered-solo", st, _outputs("arrange"), params)


SW_STEMS = ("vocals", "other", "guitar", "piano", "bass", "drums")


def pop_rock(title: str, params: dict) -> Pipeline:
    melody_stem = params.get("melody_stem", "vocals")
    st, written_on, reader = beat_stages(params)
    st.append(Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_sw, adapter="separator",
                    outputs=tuple(f"{s}.wav" for s in SW_STEMS)))
    for stem in ("vocals", "other", "guitar", "piano"):
        st.append(_transcribe(stem, "muscriptor", "mus", Input("stems", f"{stem}.wav"), None))
    st.append(_transcribe(melody_stem, "basic-pitch", "bp", Input("stems", f"{melody_stem}.wav"), None))
    st.append(_transcribe("bass", "basic-pitch", "bp", Input("stems", "bass.wav"), None))
    harmony = {f"harmony{i}": Input(f"transcribe.{s}.muscriptor", f"{s}-mus.mid")
               for i, s in enumerate(x for x in ("vocals", "other", "guitar", "piano") if x != melody_stem)}
    st.append(Stage("arrange", "arrange", {
        "beats": written_on, **reader["inputs"], "melody": Input(f"transcribe.{melody_stem}.muscriptor", f"{melody_stem}-mus.mid"),
        "melody_support": Input(f"transcribe.{melody_stem}.basic-pitch", f"{melody_stem}-bp.mid"),
        "bass": Input("transcribe.bass.basic-pitch", "bass-bp.mid"), **harmony},
        S.arrange_band, params=_arrange_params(title, params, kit="pop", reader=reader), code=SYMBOLIC_CODE,
        outputs=ARRANGED))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("pop-rock", "B", st, _outputs("arrange"), params)


PROFILES: dict[str, Profile] = {p.name: p for p in [
    Profile("solo", "layered-solo", "One brass line, no separation; SwiftF0 spine confirmed by MuScriptor or Basic Pitch, "
            "layered arranger (the on-device path), minimal band", True, solo),
    Profile("brass-band", "A", "Brass-only ensemble; MuScriptor medium + Basic Pitch on the mix, minimal band", False, brass_band),
    Profile("pop-rock", "B", "Full band; BS-RoFormer SW stems, per-stem transcription, minimal band", False, pop_rock),
    Profile("orchestra-with-soloist", "layered",
            "Soloist with orchestra; Mega-53 solo/bass/drums + orchestra residual, 18-part brass band", True, layered),
]}

# Tablature. Registered after the band's profiles; its options are its own (bass_tab.options).
from . import bass_tab  # noqa: E402 - it reads this module's stage helpers when it builds

from . import tab  # noqa: E402 - the same

PROFILES[tab.PROFILE] = Profile(tab.PROFILE, "tab", "One fretted instrument as tablature: bass, guitar, ukulele or mandolin "
                                "(instrument); its BS-RoFormer SW stem (or the recording itself), Basic Pitch with SwiftF0 as "
                                "a second opinion, a string and fret per note", False, tab.build)
PROFILES[bass_tab.PROFILE] = Profile(bass_tab.PROFILE, "tab", "The bass line as tablature; BS-RoFormer SW bass stem (or the "
                                     "recording itself), Basic Pitch, a string and fret per note. Kept for older apps: it is "
                                     "the tab profile with a bass", False, bass_tab.build)


# Printed music read from pictures (sheet.py): one profile for each target.
from . import sheet  # noqa: E402 - it reads this module's stage helpers when it builds

PROFILES[sheet.SCORE] = Profile(sheet.SCORE, "sheet", "Printed music from a screenshot, a photo or a PDF, read into a score "
                                "as it is written: parts, PDF, MIDI, braille and the talking score; not arranged", False,
                                sheet.build_score, input="pages")
PROFILES[sheet.TAB] = Profile(sheet.TAB, "sheet", "Printed music from a screenshot, a photo or a PDF, its first staff "
                              "written as tablature for one fretted instrument (instrument)", False, sheet.build_tab,
                              input="pages")


def check_input(profile: str, path: Path) -> None:
    """A job's input is the kind its profile reads: pages for the sheet profiles, a recording for the others.
    pages.WrongInput when it is not: no refused option, so it has no code among the ones above."""
    from . import pages

    if (PROFILES[profile].input == "pages") != pages.is_pages(path):
        raise pages.WrongInput(pages.WRONG_INPUT_DETAIL)


def default_title(profile: str, audio: Path) -> str:
    return targets.of(profile).titles[profile].format(name=Path(audio).stem.replace("_", " ").replace("-", " ").title())


def build(profile: str, audio: Path, title: str | None = None, params: dict | None = None) -> Pipeline:
    if profile not in PROFILES:
        raise KeyError(f"unknown profile {profile!r}; choose from {', '.join(PROFILES)}")
    if not tab.is_tab(profile):
        tab.refuse_options(profile, params or {})
    return PROFILES[profile].build(title or default_title(profile, audio), dict(params or {}))
