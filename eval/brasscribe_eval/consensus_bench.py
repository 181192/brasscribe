"""Evaluate consensus over an eval set with leave-one-song-out source precision.

Source precision for song k is measured on all other songs, so the weights are
never fitted on the song being scored.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mir_eval
import numpy as np

from .consensus import consensus, load_sources
from .score import LOOSE_TOL, load_notes, score, to_arrays


def precision_of(notes: list[dict], ref: list[dict]) -> tuple[int, int]:
    ri, rp = to_arrays(ref)
    ei, ep = to_arrays(notes)
    if len(notes) == 0:
        return 0, 0
    m = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None)
    return len(m), len(notes)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("sources", nargs="+", help="label=<name>.mid[:split] relative to each song dir")
    ap.add_argument("--thresholds", default="0.3,0.4,0.5,0.6,0.7,0.8")
    args = ap.parse_args()

    specs = []
    for s in args.sources:
        label, rest = s.split("=", 1)
        name, _, flag = rest.partition(":")
        specs.append((label, name, flag == "split"))

    songs = sorted(p for p in args.eval_dir.iterdir() if (p / "reference.json").exists())
    per_song_sources, refs = {}, {}
    for song in songs:
        refs[song] = load_notes(song / "reference.json")
        srcs = {}
        for label, name, split in specs:
            srcs.update(load_sources({label: song / name}, split))
        per_song_sources[song] = srcs

    # counts[song][source] = (matched, n_est)
    counts = {song: {s: precision_of(n, refs[song]) for s, n in per_song_sources[song].items()} for song in songs}

    thresholds = [float(t) for t in args.thresholds.split(",")]
    results = {t: [] for t in thresholds}
    for song in songs:
        prec = {}
        for s in per_song_sources[song]:
            m = sum(counts[o].get(s, (0, 0))[0] for o in songs if o != song)
            n = sum(counts[o].get(s, (0, 0))[1] for o in songs if o != song)
            prec[s] = m / n if n else 0.3
        for t in thresholds:
            notes, _ = consensus(per_song_sources[song], prec, t)
            results[t].append(score(refs[song], notes))

    summary = {}
    for t in thresholds:
        rs = results[t]
        keys = ["onset100_f1", "onset100_p", "onset100_r", "onset_f1"] + sorted(k for k in rs[0] if k.startswith("recall100"))
        summary[t] = {k: round(float(np.mean([r[k] for r in rs if k in r])), 3) for k in keys}
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
