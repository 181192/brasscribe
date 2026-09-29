"""The conformance matrix: every case is one entry point run on one input set.

Kinds (each mirrors a Python entry point and a `brasscribe-core` subcommand):
  layers  arrange_layers_song: layer MIDI + beats -> composition.json + brass-band.musicxml
  song    arrange_song: melody/support/bass/harmony MIDI + beats -> composition.json + brass-band.musicxml
  lead    lead_sheet: melody/support/bass MIDI + beats -> lead.musicxml (concert-pitch parts, pickup)
  bench   arrange_bench: reference.json notated positions -> composition.json + brass-band.musicxml
  quant   quantize reference notes on the tracked beats -> quant.json (unit level)
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
DATA = REPO / "data"
# The Mikkel golden output.
MIKKEL_GOLDEN = DATA / "golden/mikkel-arranged-band"
# The on-device reference clip.
ONDEVICE_REF = DATA / "runs" / "apple" / "entertainer-ref"
MIKKEL_TITLE = "Mikkel — solo cornet & brass band (draft)"
# SwiftF0 contour of the Mikkel solo stem that the golden output was made with (sha256 prefix).
MIKKEL_CONTOUR_SHA = "06d60fa5aae3"


MIKKEL_VARIANTS = [
    ("layers-standard", ["--difficulty", "standard"]),
    ("layers-easier", ["--difficulty", "easier"]),
    ("layers-minimal-easier", ["--lineup", "minimal", "--difficulty", "easier"]),
    ("layers-key-bb", ["--key", "Bb"]),
    ("layers-transpose-down-3", ["--transpose", "-3"]),
    # Up 3: the soloist lead reaches 87, above the cornet's solo range; its phrases keep their contour.
    ("layers-transpose-up-3", ["--transpose", "3"]),
    ("layers-quartet", ["--lineup", "quartet"]),
    ("layers-quartet-easier", ["--lineup", "quartet", "--difficulty", "easier"]),
    # A seat changes no notes of a band take; reading bass clef rewrites only the seat's part.
    ("layers-seat-euphonium-bass-clef", ["--seat", "euphonium", "--reads", "bass"]),
    ("layers-minimal-seat-2nd-baritone", ["--lineup", "minimal", "--seat", "2nd-baritone", "--reads", "bass"]),
    # The tune on the player's part: Euphonium solo with band (the countermelody moves to Solo Horn).
    ("layers-lead-seat-euphonium", ["--lead", "seat", "--seat", "euphonium"]),
    ("layers-lead-seat-euphonium-easier", ["--lead", "seat", "--seat", "euphonium", "--difficulty", "easier"]),
    ("layers-minimal-lead-seat-1st-horn", ["--lineup", "minimal", "--lead", "seat", "--seat", "1st-horn"]),
    ("layers-lead-seat-flugelhorn", ["--lead", "seat", "--seat", "flugelhorn"]),
    # A trumpet player: the lead part is written for trumpet in the bands (same notes), 1st Cornet in the quartet.
    ("layers-seat-trumpet", ["--seat", "trumpet"]),
    ("layers-minimal-seat-trumpet", ["--lineup", "minimal", "--seat", "trumpet"]),
    ("layers-quartet-seat-trumpet", ["--lineup", "quartet", "--seat", "trumpet"]),
    ("layers-lead-seat-trumpet-easier", ["--lead", "seat", "--seat", "trumpet", "--difficulty", "easier"]),
    # The footer on the arranged parts in Norwegian.
    ("layers-lang-nb", ["--lang", "nb"]),
    # The pop kit (a pop or rock take): the Percussion part's midi-instruments select bank 128 program 1.
    ("layers-kit-pop", ["--kit", "pop"]),
]
# Variants with a golden output of their own: the case name -> its directory under data/golden, or, until it is
# promoted there, under data-pending/golden next to data/.
VARIANT_GOLDENS = {"layers-kit-pop": "mikkel-arranged-band-kit-pop"}
PENDING_GOLDEN = DATA.resolve().parent / "data-pending" / "golden"


def variant_golden(stage: str) -> Path | None:
    name = VARIANT_GOLDENS.get(stage)
    if name is None:
        return None
    return next((d for d in (DATA / "golden" / name, PENDING_GOLDEN / name) if d.exists()), None)


# Song lineup options on the chorales: the tune on the player's part (non-layered arranger).
SONG_SEAT = ["--seat", "euphonium", "--lead", "seat", "--reads", "bass"]
# ChoraleBricks instrument -> the seat its solo take is written for.
SOLO_SEATS = [("bar", "1st-baritone"), ("tb", "1st-trombone"), ("tba", "eb-bass"), ("fho", "solo-horn"), ("tp", "trumpet")]
# Eval sets whose songs are also arranged for the quartet (song and bench cases): the chorales,
# which a brass quartet plays.
QUARTET_SETS = ("choralebricks-brass4",)
QUARTET = ["--lineup", "quartet"]


def mikkel_contour() -> Path | None:
    """The contour next to the repro layers, else the engine cache's copy with the golden's hash."""
    import hashlib

    here = DATA / "mikkel/repro/layers/solo-sw.contour.npz"
    if here.exists():
        return here
    for p in sorted((DATA / "cache/objects").glob("*/*/files/solo-sw.contour.npz")):
        if hashlib.sha256(p.read_bytes()).hexdigest().startswith(MIKKEL_CONTOUR_SHA):
            return p
    return None


@dataclass
class Case:
    id: str
    kind: str
    args: dict = field(default_factory=dict)
    golden: Path | None = None


def _has_quarter(ref: Path) -> bool:
    d = json.loads(ref.read_text())
    notes = d["notes"] if isinstance(d, dict) else d
    return any("quarter" in n for n in notes)


def synth_layers(song: Path, out: Path) -> Path:
    """Layer directory for an eval song: its full-mix transcriptions stand in for every layer."""
    out.mkdir(parents=True, exist_ok=True)
    sw = song / "pipeB-sw-muscriptor.mid"
    src = {
        "solo-sw.mid": sw if sw.exists() else song / "basic-pitch.mid",
        "solo-mus.mid": song / "muscriptor-medium.mid",
        "solo-bp.mid": song / "basic-pitch.mid",
        "bass-mus.mid": song / "muscriptor-medium.mid",
        "orchestra-mus.mid": song / "basic-pitch.mid",
        "drums-mus.mid": song / "muscriptor-medium.mid",
        # the mix stands in for every layer's audio (energy gate, separation check, dynamics, sections)
        "solo.wav": song / "mix.wav",
        "bass.wav": song / "mix.wav",
        "drums.wav": song / "mix.wav",
        "orchestra.wav": song / "mix.wav",
    }
    for name, p in src.items():
        link = out / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(p)
    return out


def all_cases(work: Path, only: str | None = None) -> list[Case]:
    mikkel = {"layers": DATA / "mikkel/repro/layers", "beats": DATA / "mikkel/repro/mix.beats", "title": MIKKEL_TITLE,
              **({"contour": c} if (c := mikkel_contour()) else {})}
    cases = [Case("mikkel/layers", "layers", mikkel, golden=MIKKEL_GOLDEN)]
    # Arrangement options (lineup, difficulty, key) against the Python reference.
    for stage, options in MIKKEL_VARIANTS:
        cases.append(Case(f"mikkel/{stage}", "layers", {**mikkel, "options": options}, golden=variant_golden(stage)))
    for eval_set in sorted(p for p in (DATA / "eval").iterdir() if p.is_dir()):
        for song in sorted(p for p in eval_set.iterdir() if (p / "reference.json").exists()):
            base = f"{eval_set.name}/{song.name}"
            beats = song / "beat-this.beats"
            mus, bp = song / "muscriptor-medium.mid", song / "basic-pitch.mid"
            cases.append(Case(f"{base}/song", "song", {"beats": beats, "melody": mus, "support": bp, "bass": mus,
                                                       "harmony": [mus, bp], "title": song.name}))
            cases.append(Case(f"{base}/lead", "lead", {"beats": beats, "melody": mus, "support": bp, "bass": mus,
                                                       "title": song.name}))
            cases.append(Case(f"{base}/layers", "layers", {"layers": work / "_layers" / base, "song": song,
                                                           "beats": beats, "title": song.name}))
            if eval_set.name in QUARTET_SETS:
                cases.append(Case(f"{base}/song-quartet", "song", {**cases[-3].args, "options": QUARTET}))
                cases.append(Case(f"{base}/song-lead-seat", "song", {**cases[-4].args, "options": SONG_SEAT}))
            if _has_quarter(song / "reference.json"):
                cases.append(Case(f"{base}/bench", "bench", {"reference": song / "reference.json", "title": song.name}))
                if eval_set.name in QUARTET_SETS:
                    cases.append(Case(f"{base}/bench-quartet", "bench", {**cases[-1].args, "options": QUARTET}))
                cases.append(Case(f"{base}/quant", "quant", {"reference": song / "reference.json", "beats": beats}))
    # Solo takes written for a seat (the frozen ChoraleBricks stems of eval/fixtures/choralebricks-solo): one stem
    # per low or middle brass instrument, with no seat, with its seat and, where the seat offers it, in bass clef.
    solo_fx = REPO / "eval" / "fixtures" / "choralebricks-solo"
    for abbr, seat in SOLO_SEATS:
        stems = sorted(solo_fx.glob(f"*/*_{abbr}.sw.mid"))
        if not stems:
            continue
        sw = stems[0]
        stem, song = sw.name[: -len(".sw.mid")], sw.parent
        layers = work / "_solo-layers" / f"{song.name}-{stem}"
        layers.mkdir(parents=True, exist_ok=True)
        for name, src in (("solo-sw.mid", f"{stem}.sw.mid"), ("solo-bp.mid", f"{stem}.bp.mid"), ("solo-mus.mid", f"{stem}.bp.mid")):
            link = layers / name
            if link.is_symlink() or link.exists():
                link.unlink()
            link.symlink_to(song / src)
        base = {"layers": layers, "beats": song / f"{stem}.beats", "title": stem, "contour": song / f"{stem}.contour.npz"}
        variants = [("no-seat", ["--lineup", "minimal"]), (seat, ["--lineup", "minimal", "--seat", seat])]
        from brasscribe_music.instruments import seat_by_id

        if "bass" in seat_by_id(seat).reads and seat_by_id(seat).own_part.instrument.clef != "bass":
            variants.append((f"{seat}-bass-clef", ["--lineup", "minimal", "--seat", seat, "--reads", "bass"]))
        for tag, options in variants:
            cases.append(Case(f"solo-seat/{song.name}/{stem}/{tag}", "layers", {**base, "options": options}))
    # On-device clip: small0 beats on one instrument (every beat labelled a downbeat), minimal lineup; its
    # layered output from the Python reference is kept next to it.
    ent = ONDEVICE_REF
    if (ent / "layers").exists():
        cases.append(Case("entertainer/layers", "layers",
                          {"layers": ent / "layers", "beats": ent / "beats-small0.beats", "title": "Reference",
                           "contour": ent / "layers" / "solo-sw.contour.npz", "options": ["--lineup", "minimal"]},
                          golden=ent / "layered"))
    # Meter and bar phase on single-instrument beat tracks (every URMP and ChoraleBricks part, Beat This!
    # small0 on the part's own recording): meter_of alone, and the layered song with that part's beats.
    solo = DATA / "runs" / "music-core" / "solo-beats"
    eval_songs = {s.name: s for es in (DATA / "eval").iterdir() if es.is_dir() for s in es.iterdir()
                  if (s / "reference.json").exists()}
    for song in sorted(solo.glob("*/*")) if solo.exists() else []:
        if not (song / "reference.json").exists():
            continue
        ref = None
        for bf in sorted(song.glob("*.beats")):
            base = f"solo-beats/{song.parent.name}/{song.name}/{bf.stem}"
            notes = work / "_solo-notes" / f"{song.parent.name}-{song.name}-{bf.stem}.json"
            if not notes.exists():
                ref = ref or json.loads((song / "reference.json").read_text())
                notes.parent.mkdir(parents=True, exist_ok=True)
                notes.write_text(json.dumps(sorted(({"onset": n["onset"], "offset": n["offset"]} for n in ref["notes"]
                                                    if n["part"] == bf.stem), key=lambda n: n["onset"])))
            cases.append(Case(f"{base}/meter", "meter", {"beats": bf, "notes": notes}))
            if song.name in eval_songs:
                es = eval_songs[song.name]
                cases.append(Case(f"{base}/layers", "layers", {"layers": work / "_layers" / es.parent.name / es.name,
                                                               "song": es, "beats": bf, "title": es.name}))
    if only:
        cases = [c for c in cases if only in c.id]
    return cases
