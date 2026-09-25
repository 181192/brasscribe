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
    }
    for name, p in src.items():
        link = out / name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(p)
    return out


def all_cases(work: Path, only: str | None = None) -> list[Case]:
    cases = [Case("mikkel/layers", "layers",
                  {"layers": DATA / "mikkel/repro/layers", "beats": DATA / "mikkel/repro/mix.beats", "title": MIKKEL_TITLE,
                   "contour": DATA / "runs/music-core/mikkel/solo-sw.contour.npz"},
                  golden=DATA / "golden/mikkel-arranged-band")]
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
    if only:
        cases = [c for c in cases if only in c.id]
    return cases
