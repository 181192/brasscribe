"""Quantization of fast notes with exact onsets: Python against the Rust CLI, free time, slow tempo.

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/quant_probe.py [path/to/brasscribe-core]

The Rust half needs `cargo build --release -p brasscribe-cli` in core/ (skipped without it).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "music" / "src"))
from brasscribe_music.quantize import quantize  # noqa: E402

CLI = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "core" / "target" / "release" / "brasscribe-core"
LEAD = 1.0


def run(bpm, div, n=24):
    ns = 60 / bpm / div
    return [{"pitch": 60 + i % 12, "onset": LEAD + i * ns, "offset": LEAD + (i + 1) * ns, "confidence": 1.0, "quarter": 0}
            for i in range(n)]


def grid(bpm, beats=64):
    b = 60 / bpm
    return np.arange(LEAD - 4 * b, LEAD - 4 * b + beats * b, b)


def distinct(q):
    return len({x.start if hasattr(x, "start") else x["start"] for x in q})


def rust(notes, bt):
    if not CLI.exists():
        return None
    with tempfile.TemporaryDirectory() as d:
        ref, beats, out = Path(d) / "ref.json", Path(d) / "b.beats", Path(d) / "q.json"
        ref.write_text(json.dumps({"notes": notes}))
        beats.write_text("".join(f"{t:.6f}\t{1 if i % 4 == 0 else i % 4 + 1}\n" for i, t in enumerate(bt)))
        subprocess.run([str(CLI), "quantize", "--reference", str(ref), "--beats", str(beats), "--out", str(out)], check=True)
        return json.loads(out.read_text())


def main():
    print("material | notes | py mono kept | py poly distinct starts | rust poly distinct starts")
    for bpm, div, label in [(120, 4, "16ths@120"), (120, 3, "triplet 8ths@120"), (120, 6, "sextuplets@120"),
                            (100, 8, "32nds@100"), (120, 5, "trill 10/s @120"), (120, 7, "trill 14/s @120")]:
        notes, bt = run(bpm, div), grid(bpm)
        mono = quantize(notes, bt, monophonic=True, auto_level=False)
        poly = quantize(notes, bt, monophonic=False, auto_level=True)
        r = rust(notes, bt)
        print(f"{label} | {len(notes)} | {len(mono)} | {distinct(poly)} | {distinct(r) if r is not None else 'n/a'}")

    print("\nfree time (coarse range over the run: grids 1 and 2 only)")
    for bpm, div, label in [(120, 4, "16ths@120"), (120, 3, "triplets@120"), (120, 6, "sextuplets@120")]:
        notes, bt = run(bpm, div), grid(bpm)
        coarse = [(0.0, 64.0)]
        q = quantize(notes, bt, monophonic=True, auto_level=False, coarse=coarse)
        print(f"{label} | {len(notes)} | kept {len(q)}")

    print("\nslow tempo: choose_level doubles the grid below 90 bpm when notes are dense")
    for bpm, div, label in [(72, 4, "16ths@72"), (72, 6, "sextuplets@72"), (80, 8, "32nds@80")]:
        notes, bt = run(bpm, div), grid(bpm)
        q = quantize(notes, bt, monophonic=True, auto_level=True)
        print(f"{label} | {len(notes)} | kept {len(q)}")


if __name__ == "__main__":
    main()
