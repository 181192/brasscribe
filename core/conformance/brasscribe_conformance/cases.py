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
MIKKEL_TITLE = "Mikkel — solo cornet & brass band (draft)"
# SwiftF0 contour of the Mikkel solo stem that the golden output was made with (sha256 prefix).
MIKKEL_CONTOUR_SHA = "06d60fa5aae3"


MIKKEL_VARIANTS = [
    ("layers-standard", ["--difficulty", "standard"]),
    ("layers-easier", ["--difficulty", "easier"]),
    ("layers-minimal-easier", ["--lineup", "minimal", "--difficulty", "easier"]),
    ("layers-key-bb", ["--key", "Bb"]),
    ("layers-transpose-down-3", ["--transpose", "-3"]),
]


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
    cases = [Case("mikkel/layers", "layers", mikkel, golden=DATA / "golden/mikkel-arranged-band")]
    # Arrangement options (lineup, difficulty, key) against the Python reference.
    for stage, options in MIKKEL_VARIANTS:
        cases.append(Case(f"mikkel/{stage}", "layers", {**mikkel, "options": options}))
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
            if _has_quarter(song / "reference.json"):
                cases.append(Case(f"{base}/bench", "bench", {"reference": song / "reference.json", "title": song.name}))
                cases.append(Case(f"{base}/quant", "quant", {"reference": song / "reference.json", "beats": beats}))
    # On-device clip: small0 beats on one instrument (every beat labelled a downbeat), minimal lineup; its
    # layered output from the Python reference is kept next to it.
    ent = DATA / "runs" / "apple" / "entertainer-ref"
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
