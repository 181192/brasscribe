"""Profiles: which pipeline a recording goes through (docs/research/00-summary.md §0).

  solo                    one brass line, no separation. SwiftF0 is the spine,
                          confirmed by MuScriptor or Basic Pitch (pipeline A, solo rule)
  brass-band              brass-only ensemble, no separation: MuScriptor medium +
                          Basic Pitch on the mix, minimal band (pipeline A)
  pop-rock                full band: BS-RoFormer SW, then per-stem transcription
                          (bass with Basic Pitch), minimal band (pipeline B)
  orchestra-with-soloist  layered solo-with-band: Mega-53 solo/bass/drums, the
                          orchestra as residual, 18-part brass band (layered)

Only orchestra-with-soloist is checked end to end against a golden output
(data/golden/mikkel-arranged-band); the other three are wired from the same
reference modules but have no end-to-end gate yet.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from . import stages as S
from .dag import SOURCE, Input, Pipeline, Stage
from .stages import EVAL_SRC, SYMBOLIC_CODE, THIS


@dataclass(frozen=True)
class Profile:
    name: str
    pipeline: str
    description: str
    validated: bool
    build: callable  # (title, params) -> list[Stage] and outputs


ARRANGEMENT_DEFAULTS = {"lineup": "full", "difficulty": "faithful", "key": None, "transpose": None,
                        "seat": None, "reads": None, "lead": "lineup"}
LINEUPS = ("full", "minimal", "quartet")
DIFFICULTIES = ("faithful", "standard", "easier")
# A solo take has one line and nothing for the other three quartet parts to play.
QUARTET_NEEDS_GROUP = "a quartet needs a recording of the whole group: a solo take has no harmony for the other parts"


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
    from brasscribe_music.instruments import LEADS, SEAT_IDS, check_reads

    seat = opts.get("seat")
    if seat is not None and seat not in SEAT_IDS:
        raise ValueError(f"seat must be one of {', '.join(SEAT_IDS)}")
    check_reads(seat, opts.get("reads"))
    if opts.get("lead") not in (None, *LEADS):
        raise ValueError(f"lead must be one of {', '.join(LEADS)}")
    if opts.get("lead") == "seat" and seat is None:
        raise ValueError("lead=seat needs a seat")


def job_options(profile: str, params: dict) -> dict:
    """arrangement_options, plus what the profile cannot do (the solo profile has no quartet; the tune moves to
    the seat's part in the band lineups only)."""
    from brasscribe_music.instruments import lead_lineup, lineup_by_name

    from brasscribe_music.instruments import PERCUSSION_SOLO, seat_by_id

    opts = arrangement_options(params)
    if profile == "solo" and params.get("lineup") == "quartet":
        raise ValueError(QUARTET_NEEDS_GROUP)
    if profile == "solo" and opts.get("seat") and not seat_by_id(opts["seat"]).reads:
        raise ValueError(PERCUSSION_SOLO)
    if profile != "solo" and opts.get("lead") == "seat":
        lineup = params.get("lineup") or ("minimal" if profile in ("brass-band", "pop-rock") else "full")
        lead_lineup(lineup_by_name(lineup), opts["seat"])
    return opts


def _arrange_params(title: str, params: dict, lineup: str = "full") -> dict:
    """lineup: the profile's lineup when the job does not choose one."""
    opts = arrangement_options({**params, "lineup": params.get("lineup") or lineup})
    return {"title": title, "arrangement": opts} if opts else {"title": title}


def _beats() -> Stage:
    return Stage("beats", "beats", {"audio": Input(SOURCE)}, S.beats, adapter="beat-this",
                 outputs=("mix.beats",), reuse_subdir=".")


def _transcribe(layer: str, tool: str, suffix: str, src: Input, reuse_subdir: str | None) -> Stage:
    return Stage(f"transcribe.{layer}.{tool}", "transcribe", {"audio": src}, S.transcribe, adapter=tool,
                 params={"output": f"{layer}-{suffix}.mid"}, outputs=(f"{layer}-{suffix}.mid",), reuse_subdir=reuse_subdir)


def _export(arrange: str, audio: bool) -> Stage:
    code = S.EXPORT_CODE + ((S.PART_STYLE,) if S.PART_STYLE.exists() else ())
    return Stage("export", "export", {"score": Input(arrange)}, S.export, params={"audio": audio}, code=code,
                 outputs=("export.json",))


def _outputs(arrange: str) -> dict[str, tuple[str, str]]:
    return {
        "composition.json": (arrange, "composition.json"),
        "brass-band.musicxml": (arrange, "brass-band.musicxml"),
        "brass-band.pdf": ("export", "brass-band.pdf"),
        "brass-band.mid": ("export", "brass-band.mid"),
        "brass-band.mp3": ("export", "brass-band.mp3"),
        "separation-check.json": (arrange, "separation-check.json"),
        "parts/": (arrange, "parts/"),  # a trailing slash copies every file under that directory
        "parts-pdf/": ("export", "parts/"),  # part PDFs and BRF land next to the part MusicXML
        "brass-band.brf": ("export", "brass-band.brf"),
        "talking-score.json": ("export", "talking-score.json"),
        "talking-score.html": ("export", "talking-score.html"),
        "talking-score.txt": ("export", "talking-score.txt"),
    }


# Layered solo-with-band: the song pipeline (brasscribe_eval.song_pipeline) as a DAG.
# Stage outputs keep the song pipeline's file names, so an existing output directory
# (mix.beats, stems/, layers/) can seed the cache.
LAYER_TOOLS = {
    "solo": [("muscriptor", "mus"), ("basic-pitch", "bp"), ("swift-f0", "sw")],
    "orchestra": [("muscriptor", "mus")],
    "bass": [("muscriptor", "mus")],
    "drums": [("muscriptor", "mus")],
}


def layered(title: str, params: dict) -> Pipeline:
    st = [
        _beats(),
        Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_mega53, adapter="mega53",
              outputs=("*.flac", "trumpet.flac", "bass.flac", "drums.flac"), reuse_subdir="stems"),
        Stage("layers", "layers", {"audio": Input(SOURCE), "trumpet": Input("stems", "trumpet.flac"),
                                   "bass": Input("stems", "bass.flac"), "drums": Input("stems", "drums.flac")},
              S.layers, code=(EVAL_SRC / "layers.py", THIS),
              outputs=("solo.wav", "bass.wav", "drums.wav", "orchestra.wav"), reuse_subdir="layers"),
    ]
    arrange_inputs = {"beats": Input("beats", "mix.beats")}
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
    st.append(Stage("arrange", "arrange", arrange_inputs, S.arrange_layered, params=_arrange_params(title, params),
                    code=SYMBOLIC_CODE, outputs=("composition.json", "brass-band.musicxml")))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("orchestra-with-soloist", "layered", st, _outputs("arrange"), params)


def brass_band(title: str, params: dict) -> Pipeline:
    mix = Input(SOURCE)
    st = [_beats(), _transcribe("mix", "muscriptor", "mus", mix, None), _transcribe("mix", "basic-pitch", "bp", mix, None)]
    st.append(Stage("arrange", "arrange", {
        "beats": Input("beats", "mix.beats"), "melody": Input("transcribe.mix.muscriptor", "mix-mus.mid"),
        "melody_support": Input("transcribe.mix.basic-pitch", "mix-bp.mid"),
        "bass": Input("transcribe.mix.muscriptor", "mix-mus.mid"),
        "harmony0": Input("transcribe.mix.muscriptor", "mix-mus.mid")},
        S.arrange_band, params=_arrange_params(title, params), code=SYMBOLIC_CODE, outputs=("composition.json", "brass-band.musicxml")))
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
    from brasscribe_music.instruments import PERCUSSION_SOLO, seat_by_id

    if params.get("seat") and not seat_by_id(params["seat"]).reads:
        raise ValueError(PERCUSSION_SOLO)
    mix = Input(SOURCE)
    st = [Stage("beats", "beats", {"audio": mix}, S.beats, adapter="beat-this", params={"env": {"BEAT_THIS_MODEL": "small0"}},
                outputs=("mix.beats",), reuse_subdir=".")]
    tools = [("swift-f0", "sw"), ("basic-pitch", "bp")] + ([("muscriptor", "mus")] if params.get("muscriptor", True) else [])
    arrange_inputs = {"beats": Input("beats", "mix.beats")}
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
    st.append(Stage("arrange", "arrange", arrange_inputs, S.arrange_layered, params=_arrange_params(title, params, "minimal"),
                    code=SYMBOLIC_CODE, outputs=("composition.json", "brass-band.musicxml")))
    st.append(_export("arrange", params.get("audio", True)))
    return Pipeline("solo", "layered-solo", st, _outputs("arrange"), params)


SW_STEMS = ("vocals", "other", "guitar", "piano", "bass", "drums")


def pop_rock(title: str, params: dict) -> Pipeline:
    melody_stem = params.get("melody_stem", "vocals")
    st = [_beats(), Stage("stems", "stems", {"audio": Input(SOURCE)}, S.stems_sw, adapter="separator",
                          outputs=tuple(f"{s}.wav" for s in SW_STEMS))]
    for stem in ("vocals", "other", "guitar", "piano"):
        st.append(_transcribe(stem, "muscriptor", "mus", Input("stems", f"{stem}.wav"), None))
    st.append(_transcribe(melody_stem, "basic-pitch", "bp", Input("stems", f"{melody_stem}.wav"), None))
    st.append(_transcribe("bass", "basic-pitch", "bp", Input("stems", "bass.wav"), None))
    harmony = {f"harmony{i}": Input(f"transcribe.{s}.muscriptor", f"{s}-mus.mid")
               for i, s in enumerate(x for x in ("vocals", "other", "guitar", "piano") if x != melody_stem)}
    st.append(Stage("arrange", "arrange", {
        "beats": Input("beats", "mix.beats"), "melody": Input(f"transcribe.{melody_stem}.muscriptor", f"{melody_stem}-mus.mid"),
        "melody_support": Input(f"transcribe.{melody_stem}.basic-pitch", f"{melody_stem}-bp.mid"),
        "bass": Input("transcribe.bass.basic-pitch", "bass-bp.mid"), **harmony},
        S.arrange_band, params=_arrange_params(title, params), code=SYMBOLIC_CODE, outputs=("composition.json", "brass-band.musicxml")))
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

DEFAULT_TITLES = {
    "orchestra-with-soloist": "{name} — solo cornet & brass band (draft)",
    "solo": "{name} — solo (draft)",
    "brass-band": "{name} — brass band (draft)",
    "pop-rock": "{name} — brass band (draft)",
}


def default_title(profile: str, audio: Path) -> str:
    return DEFAULT_TITLES[profile].format(name=Path(audio).stem.replace("_", " ").replace("-", " ").title())


def build(profile: str, audio: Path, title: str | None = None, params: dict | None = None) -> Pipeline:
    if profile not in PROFILES:
        raise KeyError(f"unknown profile {profile!r}; choose from {', '.join(PROFILES)}")
    return PROFILES[profile].build(title or default_title(profile, audio), dict(params or {}))
