"""Bar-line robustness: quant_bench metrics with the tracked beats raw vs cleaned (brasscribe_music.beats).

Missed and inserted beats shift every later note by a beat, which the
position metric (one integer beat shift per piece) counts as wrong. Cleaning
should raise position accuracy without costing subdivision or duration.

Because one global shift makes position accuracy swing on a single beat
error, the bench also counts drift events: along the piece, the beat offset
between our position and the score's (median over 9 notes) changes.

    uv run python -W ignore -m brasscribe_eval.barline_bench ../data/eval/urmp-brass ../data/eval/choralebricks-brass4
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from brasscribe_music.beats import clean_beats
from brasscribe_music.freetime import unstable_runs

from brasscribe_music.quantize import TICKS_PER_BEAT, quantize

from .quant_bench import evaluate
from .score import load_notes

KEYS = ("position_acc", "subdivision_acc", "duration_acc", "beats_per_quarter")


def drift_events(ref: list[dict], beats: np.ndarray) -> int:
    q = quantize(ref, beats)
    by = {(round(x.onset_s, 6), x.pitch): x for x in q}
    items = sorted(ref, key=lambda r: r["onset"])
    offs = []
    for r in items:
        x = by[(round(r["onset"], 6), r["pitch"])]
        d = int(round(r["quarter"] * TICKS_PER_BEAT)) - x.start
        if d % TICKS_PER_BEAT == 0:
            offs.append(d // TICKS_PER_BEAT)
    if len(offs) < 9:
        return 0
    sm = [int(np.median(offs[i:i + 9])) for i in range(len(offs) - 8)]
    return int(sum(a != b for a, b in zip(sm, sm[1:])))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dirs", type=Path, nargs="+")
    args = ap.parse_args()
    rows = []
    for d in args.eval_dirs:
        for song in sorted(p for p in d.iterdir() if (p / "reference.json").exists()):
            b = np.loadtxt(song / "beat-this.beats")
            ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
            c = clean_beats(b[:, 0], b[:, 1] == 1, skip=unstable_runs(b[:, 0]), onsets=np.array([r["onset"] for r in ref]))
            raw = evaluate(song, None)
            fixed = evaluate(song, None, beats_override=c.times)
            raw["drift_events"] = drift_events(ref, b[:, 0])
            fixed["drift_events"] = drift_events(ref, c.times)
            rows.append((raw, fixed))
            print(f"{song.name:40s} +{c.inserted}/-{c.removed} beats  "
                  + " ".join(f"{k[:3]} {raw[k]:.3f}->{fixed[k]:.3f}" for k in KEYS)
                  + f" drift {raw['drift_events']}->{fixed['drift_events']}")
    out = {v: {k: round(float(np.mean([r[i][k] for r in rows])), 3) for k in KEYS} for i, v in enumerate(("raw", "cleaned"))}
    for i, v in enumerate(("raw", "cleaned")):
        out[v]["drift_events_total"] = int(sum(r[i]["drift_events"] for r in rows))
    print(json.dumps(out))


if __name__ == "__main__":
    main()
