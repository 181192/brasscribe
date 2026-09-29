"""Adversarial checks of the collision-aware ("dense") quantizer: kept notes and readability.

Runs brasscribe_music.quantize(..., monophonic=True, dense=True) from the music/ tree given on PYTHONPATH
(the fast-notes code under review) on exact and jittered figures, steady and rubato, and reports per case:

  kept      notes written / notes played
  shifted   notes moved off their snapped slot (confidence halved)
  switches  grid changes between consecutive beats inside the figure
  grids     histogram of the chosen subdivision per beat
  exact     notes written on the slot of their true (performed) subdivision position

    PYTHONPATH=<tree>/music/src python docs/research/fastnotes/dense_probe.py
"""

from __future__ import annotations

from collections import Counter

import numpy as np
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap, quantize

try:
    from brasscribe_music.quantize import choose_grids_dense
except ImportError:  # the base tree
    choose_grids_dense = None

LEAD = 1.0


def figure(bpm, div, n, jitter=0.0, rubato=0.0, seed=0):
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    # rubato: the performed beat length drifts sinusoidally by +-rubato (fraction), the grid stays the tracker's
    t, out = LEAD, []
    for i in range(n):
        k = i / div
        local = beat * (1 + rubato * np.sin(2 * np.pi * k / 4))
        out.append(t + rng.normal(0, jitter))
        t += local / div
    notes = [{"pitch": 60 + (i % 2) * 2, "onset": float(o), "offset": float(o + beat / div * 0.9), "confidence": 1.0}
             for i, o in enumerate(out)]
    true_ticks = [round(i * TICKS_PER_BEAT / div) for i in range(n)]
    return notes, np.arange(LEAD - 4 * beat, LEAD + 64 * beat, beat), true_ticks


def run(label, bpm, div, n=32, jitter=0.0, rubato=0.0, trials=20):
    kept = shifted = switches = exact = 0
    hist = Counter()
    for s in range(trials):
        notes, bt, true_ticks = figure(bpm, div, n, jitter, rubato, s)
        q = quantize([dict(x) for x in notes], bt, monophonic=True, auto_level=False, dense=True)
        kept += len(q)
        shifted += sum(x.confidence < 1.0 for x in q)
        bm = BeatMap(bt)
        on = bm.to_beats(np.array([x["onset"] for x in notes]))
        g = choose_grids_dense(on, None, np.r_[np.diff(bt), bt[-1] - bt[-2]]) if choose_grids_dense else {}
        ks = sorted(g)
        seq = [g[k] for k in ks]
        switches += sum(a != b for a, b in zip(seq, seq[1:]))
        hist.update(seq)
        base = 4 * TICKS_PER_BEAT  # LEAD is beat 4 of the grid
        written = {x.start - base for x in q}
        exact += sum(t in written for t in true_ticks)
    T = trials * n
    print(f"{label:34} kept {kept / T:.2f}  exact {exact / T:.2f}  shifted {shifted / T:.2f}  "
          f"switches/beat {switches / (trials * n / div):.2f}  grids {dict(sorted(hist.items()))}")


def main():
    run("16ths @100 exact", 100, 4)
    run("16ths @140 jitter 10 ms", 140, 4, jitter=0.010)
    run("16ths @140 jitter 20 ms", 140, 4, jitter=0.020)
    run("16ths @100 rubato 10%", 100, 4, rubato=0.10)
    run("16ths @100 rubato 10% + 15 ms", 100, 4, jitter=0.015, rubato=0.10)
    run("triplet 8ths @100 exact", 100, 3)
    run("triplet 8ths @100 jitter 15 ms", 100, 3, jitter=0.015)
    run("sextuplets @100 exact", 100, 6)
    run("sextuplets @100 jitter 10 ms", 100, 6, jitter=0.010)
    run("32nds @80 exact", 80, 8)
    run("32nds @80 jitter 8 ms", 80, 8, jitter=0.008)
    run("trill 12/s @120 (div 6)", 120, 6)
    run("trill 14/s @120 (not a grid)", 120, 7)
    run("8ths @120 jitter 30 ms (slow)", 120, 2, jitter=0.030)
    run("quarters @90 jitter 40 ms (slow)", 90, 1, jitter=0.040)


if __name__ == "__main__":
    main()
