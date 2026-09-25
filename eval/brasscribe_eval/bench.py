"""Run one adapter over an eval set and write a per-song + mean metrics table."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from pathlib import Path

import pandas as pd

from .score import load_notes, score


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("adapter", type=Path, help="path to adapter run.sh")
    ap.add_argument("--name", required=True, help="label; output file is <song>/<name>.mid")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    rows = []
    for song in sorted(p for p in args.eval_dir.iterdir() if (p / "mix.wav").exists()):
        out = song / f"{args.name}.mid"
        secs = None
        if args.force or not out.exists():
            t0 = time.time()
            subprocess.run([str(args.adapter.resolve()), str(song / "mix.wav"), str(out)], check=True, env=os.environ)
            secs = time.time() - t0
        m = score(load_notes(song / "reference.json"), load_notes(out))
        rows.append({"song": song.name, "runtime_s": secs, **m})
        print(f"{song.name}: onset_f1={m['onset_f1']:.3f} onoff_f1={m['onoff_f1']:.3f}", flush=True)

    df = pd.DataFrame(rows)
    means = df.drop(columns="song").mean(numeric_only=True)
    df.loc[len(df)] = {"song": "MEAN", **means.to_dict()}
    df.to_csv(args.eval_dir / f"results-{args.name}.csv", index=False)
    cols = ["onset_f1", "onoff_f1", "octave_err_rate", "recall_S", "recall_A", "recall_T", "recall_B", "runtime_s"]
    print(json.dumps({c: round(float(means[c]), 3) for c in cols if c in means}, indent=1))


if __name__ == "__main__":
    main()
