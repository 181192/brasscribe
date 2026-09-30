"""Evaluate beat tracking + quantization against notated positions.

Needs a reference with notated positions per note ("quarter", "dur_quarter"),
as built by choralebricks.py from the ChoraleBricks alignments. Slakh MIDI is
largely unquantized (live-played), so it cannot serve as notation ground truth.

Input notes are either the reference notes themselves (isolates beat tracking
and quantization) or estimated notes matched to the reference. Reported:
  - position_acc: quantized onset equals the notated position (after aligning
    the detected beat index to the score with the best integer offset)
  - subdivision_acc: same position within the beat
  - duration_acc: quantized length equals the notated length
  - beats_per_quarter: detected beats per notated quarter (1.0 = right metrical level)
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import mir_eval
import numpy as np
from brasscribe_music.quantize import TICKS_PER_BEAT, quantize

from .score import LOOSE_TOL, load_notes, to_arrays


def evaluate(song: Path, source: str | None, beats_file: str = "beat-this.beats", beats_override: np.ndarray | None = None) -> dict:
    ref = load_notes(song / "reference.json")
    beats = beats_override if beats_override is not None else np.loadtxt(song / beats_file)[:, 0]

    if source is None:
        pairs = [(r, r) for r in ref]
    else:
        est = load_notes(song / source)
        ri, rp = to_arrays(ref)
        ei, ep = to_arrays(est)
        m = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None)
        pairs = [(ref[i], est[j]) for i, j in m]

    pairs = [(r, e) for r, e in pairs if "quarter" in r]  # a few performed notes have no score counterpart
    q = quantize([e for _, e in pairs], beats)
    # (onset, pitch, offset): parts in unison on one onset keep their own lengths
    by_onset = {(round(x.onset_s, 6), x.pitch, round(x.offset_s, 6)): x for x in q}
    est_q = [by_onset[(round(e["onset"], 6), e["pitch"], round(e["offset"], 6))] for _, e in pairs]
    ref_ticks = [int(round(r["quarter"] * TICKS_PER_BEAT)) for r, _ in pairs]

    shift = Counter(rt - x.start for rt, x in zip(ref_ticks, est_q) if (rt - x.start) % TICKS_PER_BEAT == 0).most_common(1)
    shift = shift[0][0] if shift else 0

    n = max(1, len(pairs))
    pos = sum(x.start + shift == rt for rt, x in zip(ref_ticks, est_q)) / n
    sub = sum(x.start % TICKS_PER_BEAT == rt % TICKS_PER_BEAT for rt, x in zip(ref_ticks, est_q)) / n
    dur = sum((x.end - x.start) == int(round(r["dur_quarter"] * TICKS_PER_BEAT)) for (r, _), x in zip(pairs, est_q)) / n
    ref = [r for r in ref if "quarter" in r]
    span_q = max(r["quarter"] for r in ref) - min(r["quarter"] for r in ref)
    t0, t1 = min(r["onset"] for r in ref), max(r["onset"] for r in ref)
    nb = np.sum((beats >= t0) & (beats <= t1))
    return {"n": len(pairs), "of_ref": len(ref), "position_acc": pos, "subdivision_acc": sub,
            "duration_acc": dur, "beats_per_quarter": nb / max(1.0, span_q)}


def reference_beats(song: Path) -> np.ndarray:
    """Beat times interpolated from the notated positions (upper bound for beat tracking)."""
    ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
    qs = np.array([r["quarter"] for r in ref])
    ts = np.array([r["onset"] for r in ref])
    order = np.argsort(qs)
    qs, ts = qs[order], ts[order]
    uq, idx = np.unique(qs, return_index=True)
    ut = np.array([np.median(ts[qs == q]) for q in uq])
    grid = np.arange(np.ceil(uq[0]), np.floor(uq[-1]) + 1)
    return np.interp(grid, uq, ut)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path)
    ap.add_argument("--source", help="estimated notes file; default uses reference notes")
    ap.add_argument("--beats", default="beat-this.beats", help="beats file, or 'reference'")
    args = ap.parse_args()
    rows = []
    for song in sorted(p for p in args.eval_dir.iterdir() if (p / "reference.json").exists()):
        override = reference_beats(song) if args.beats == "reference" else None
        r = evaluate(song, args.source, args.beats, override)
        rows.append(r)
        print(f"{song.name:42s} " + " ".join(f"{k}={v:.2f}" if isinstance(v, float) else f"{k}={v}" for k, v in r.items()))
    keys = ["position_acc", "subdivision_acc", "duration_acc", "beats_per_quarter"]
    print(json.dumps({k: round(float(np.mean([r[k] for r in rows])), 3) for k in keys}))


if __name__ == "__main__":
    main()
