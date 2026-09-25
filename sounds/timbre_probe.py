"""Try source/EQ candidates for a target and measure the harmonic centroid against real references.

    uv run --project sounds python sounds/timbre_probe.py

For each candidate (source library/instrument + EQ chain) the mf-ish sustain samples in the
part's pitch window are trimmed and filtered exactly as build.py does, and the median
spectral centroid in harmonics (centroid / f0) over the first 0.6 s is compared with the
held-out ChoraleBricks songs and URMP. The chosen candidates go into mapping.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from build import ANALYSIS, DC_BLOCK, load_segment, trim  # noqa: E402
from descriptors import cb_split, note_descriptor, reference_notes  # noqa: E402
from dsp import SR, apply_eq  # noqa: E402

LP = lambda f, q=0.707: {"type": "lowpass", "f": f, "q": q}  # noqa: E731
SH = lambda f, g, q=0.7: {"type": "highshelf", "f": f, "gain_db": g, "q": q}  # noqa: E731
LS = lambda f, g, q=0.7: {"type": "lowshelf", "f": f, "gain_db": g, "q": q}  # noqa: E731
PK = lambda f, g, q=0.9: {"type": "peak", "f": f, "gain_db": g, "q": q}  # noqa: E731

MAPPING = json.loads((HERE / "mapping.json").read_text())
CANDIDATES = {
    "euphonium": {
        "window": (45, 60), "reference": "baritone",
        "options": {
            "iowa-tbn current": (("iowa-mis", "tenor-trombone"), MAPPING["targets"]["euphonium"]["eq"]),
            "iowa-tbn LP4 900": (("iowa-mis", "tenor-trombone"), [LS(200, 3), LP(900), LP(900)]),
            "vsco-tbn baritone-eq": (("vsco2ce", "tenor-trombone"), MAPPING["targets"]["baritone"]["eq"]),
            "vsco-tbn LP4 1200": (("vsco2ce", "tenor-trombone"), [LS(200, 3), PK(1800, -3), LP(1200), LP(1200)]),
            "vsco-tbn LP4 900": (("vsco2ce", "tenor-trombone"), [LS(200, 3), LP(900), LP(900)]),
            "vsco-tuba LP 1500": (("vsco2ce", "tuba"), [LP(1500)]),
        },
    },
    "bb-bass": {
        "window": (29, 41), "reference": "tuba",
        "options": {
            "iowa-tuba current": (("iowa-mis", "tuba"), MAPPING["targets"]["bb-bass"]["eq"]),
            "iowa-tuba LP4 400": (("iowa-mis", "tuba"), [LS(120, 1.5), LP(400), LP(400)]),
            "vsco-tuba eb-eq": (("vsco2ce", "tuba"), MAPPING["targets"]["eb-bass"]["eq"]),
            "vsco-tuba LS+LP 1200": (("vsco2ce", "tuba"), [LS(120, 1.5), SH(2500, -1.5), LP(1200)]),
            "vsco-tuba LP4 600": (("vsco2ce", "tuba"), [LS(120, 1.5), LP(600), LP(600)]),
        },
    },
}


def harmonics(library: str, instrument: str, eq: list[dict], lo: int, hi: int, notes: list[dict]) -> tuple[float, int]:
    vals = []
    for n in notes:
        if n["library"] != library or n["instrument"] != instrument or n["art"] != "sus" or n.get("midi") is None:
            continue
        if not lo - 2 <= n["midi"] <= hi + 2 or n["dyn"] not in ("mf", "v2", "v1"):
            continue
        y = apply_eq(trim(load_segment(n)), DC_BLOCK + eq)
        d = note_descriptor(y, 0.0, min(len(y) / SR, 0.8), n["midi"])
        if d:
            vals.append(d["harmonics"])
    return (float(np.median(vals)) if vals else float("nan")), len(vals)


def main() -> None:
    notes = json.loads(ANALYSIS.read_text())
    refs = reference_notes()
    _, held_out = cb_split()
    for tid, spec in CANDIDATES.items():
        lo, hi = spec["window"]
        rs = [d for d in refs[spec["reference"]] if lo <= d["midi"] <= hi]
        cb = np.median([d["harmonics"] for d in rs if d["corpus"] == "ChoraleBricks" and d["song"] in held_out])
        urmp = [d["harmonics"] for d in rs if d["corpus"] == "URMP"]
        print(f"{tid}: window {lo}-{hi}, reference {spec['reference']}: ChoraleBricks held-out {cb:.2f}h"
              + (f", URMP {np.median(urmp):.2f}h" if urmp else ""))
        for name, ((lib, inst), eq) in spec["options"].items():
            h, n = harmonics(lib, inst, eq, lo, hi, notes)
            print(f"   {name:24s} {h:5.2f}h  (n={n})")


if __name__ == "__main__":
    main()
