"""Sanity checks on built instruments and renders.

    uv run --project sounds python sounds/checks.py loops                  # loop seams of every built sample
    uv run --project sounds python sounds/checks.py balance RUN [RUN ...]  # integrated LUFS per dry stem

loops: for each looped sample, the step at the jump |y[end-1] -> y[start]| relative to the
99th percentile of the sample-to-sample steps in the 40 ms before the jump (> 1 means the jump
is a bigger discontinuity than the waveform itself ever makes, i.e. a potential click), and the correlation of 10 ms before the loop end with 10 ms before the loop start
(what the crossfade makes the jump sound like). Outliers are listed.
balance: per-part loudness relative to the loudest part, side by side for each run, to catch
sections that end up far quieter or louder than in the baseline.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dsp import SR  # noqa: E402

BUILT = HERE.parent / "data" / "sounds" / "built"


def loops() -> None:
    rows = []
    for regions in sorted(BUILT.glob("*/regions.json")):
        t = json.loads(regions.read_text())
        for s in t["articulations"]["sus"]["samples"]:
            if not s["loop"]:
                continue
            a, b = s["loop"]
            y, _ = sf.read(str(regions.parent / "samples" / s["file"]), dtype="float64")
            w = int(0.01 * SR)
            natural = np.abs(np.diff(y[b - 4 * w : b]))
            step = abs(y[a] - y[b - 1]) / (np.percentile(natural, 99) + 1e-12)
            # the audio heard across the jump is y[b-w:b] followed by y[a:a+w]; compare with the
            # natural continuation y[a-w:a] -> y[a:a+w]
            pre_end, pre_start = y[b - w : b], y[a - w : a]
            corr = float(np.dot(pre_end, pre_start) / (np.linalg.norm(pre_end) * np.linalg.norm(pre_start) + 1e-12))
            rows.append((t["target"], s["file"], step, corr))
    steps = np.array([r[2] for r in rows])
    corrs = np.array([r[3] for r in rows])
    print(f"{len(rows)} loops: step/p99-natural median {np.median(steps):.3f}, p99 {np.percentile(steps, 99):.3f}, max {steps.max():.3f}; "
          f"seam correlation median {np.median(corrs):.3f}, p1 {np.percentile(corrs, 1):.3f}, min {corrs.min():.3f}")
    bad = [r for r in rows if r[2] > 1.0 or r[3] < 0.9]
    for r in bad:
        print(f"  check {r[0]:15s} {r[1]:40s} step {r[2]:.2f} corr {r[3]:.3f}")
    print(f"{len(bad)} outliers (jump step above the largest natural step, or correlation < 0.9)")


def balance(runs: list[str]) -> None:
    meter = pyloudnorm.Meter(SR)
    table: dict[str, dict[str, float]] = {}
    for run in runs:
        for stem in sorted((Path(run) / "stems").glob("*.wav")):
            x, _ = sf.read(str(stem), dtype="float64")
            table.setdefault(stem.stem, {})[Path(run).name] = meter.integrated_loudness(x)
    names = [Path(r).name for r in runs]
    top = {n: max(v[n] for v in table.values() if n in v) for n in names}
    print(f"{'part':16s} " + " ".join(f"{n[:12]:>12s}" for n in names) + "   (LU relative to the loudest part)")
    for part, v in table.items():
        print(f"{part:16s} " + " ".join(f"{v.get(n, float('nan')) - top[n]:+12.1f}" for n in names))


if __name__ == "__main__":
    if sys.argv[1] == "loops":
        loops()
    else:
        balance(sys.argv[2:])
