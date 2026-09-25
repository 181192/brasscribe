"""Free-time detection on rubato and fermata material: does it fire, and does it cost the strict passages?

For every piece with Beat This! beats and score-aligned reference notes
(URMP brass, ChoraleBricks), the reference notes are quantized twice:
  grid   the beat grid as tracked (choose_level, as quant_bench does)
  free   the same beats with free-time runs replaced (brasscribe_music.freetime)
Reported per piece: the detected regions, and for both variants
  - strict passages (notes outside any region): position / subdivision /
    duration accuracy as in quant_bench, the integer beat shift fitted per
    stretch between regions, so both variants are scored the same way
  - inside regions: rhythm shape, the share of successive inter-onset
    intervals per part whose ratio to the score's matches within 25% after
    one tempo factor per region (proportional notation cannot match score
    positions, but should keep long vs short)

    uv run python -W ignore -m brasscribe_eval.freetime_bench ../data/eval/urmp-brass ../data/eval/choralebricks-brass4
"""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from brasscribe_music.freetime import plan_free_time
from brasscribe_music.quantize import TICKS_PER_BEAT, choose_level, quantize

from .score import load_notes


def _strict_scores(pairs, segments) -> dict:
    """pairs: (ref note, qnote) outside regions; segments: seconds boundaries splitting them into stretches."""
    n = max(1, len(pairs))
    pos = sub = dur = 0
    for lo, hi in segments:
        seg = [(r, x) for r, x in pairs if lo <= r["onset"] < hi]
        ref_ticks = [int(round(r["quarter"] * TICKS_PER_BEAT)) for r, _ in seg]
        shift = Counter(rt - x.start for rt, (_, x) in zip(ref_ticks, seg) if (rt - x.start) % TICKS_PER_BEAT == 0).most_common(1)
        shift = shift[0][0] if shift else 0
        pos += sum(x.start + shift == rt for rt, (_, x) in zip(ref_ticks, seg))
        sub += sum(x.start % TICKS_PER_BEAT == rt % TICKS_PER_BEAT for rt, (_, x) in zip(ref_ticks, seg))
        dur += sum((x.end - x.start) == int(round(r["dur_quarter"] * TICKS_PER_BEAT)) for r, x in seg)
    return {"position": pos / n, "subdivision": sub / n, "duration": dur / n}


def _shape(pairs) -> tuple[int, int]:
    """(matching, total) successive-IOI ratios per part vs the score, one tempo factor."""
    by_part = defaultdict(list)
    for r, x in pairs:
        by_part[r["part"]].append((r["quarter"], x.start))
    ours, score = [], []
    for items in by_part.values():
        items = sorted(set(items))
        for (q0, t0), (q1, t1) in zip(items, items[1:]):
            if q1 > q0 and t1 > t0:
                ours.append(t1 - t0)
                score.append((q1 - q0) * TICKS_PER_BEAT)
    if not ours:
        return 0, 0
    ratio = np.array(ours) / np.array(score)
    k = np.median(ratio)
    return int(np.sum(np.abs(ratio / k - 1) <= 0.25)), len(ratio)


def evaluate(song: Path) -> dict:
    ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
    b = np.loadtxt(song / "beat-this.beats")
    onsets = np.array([r["onset"] for r in ref])
    grid = choose_level(b[:, 0], onsets)
    doubled = len(grid) != len(b)
    pos = b[:, 1].astype(int)
    bpb = Counter(np.diff(np.where(pos == 1)[0])).most_common(1)
    bpb = int(bpb[0][0]) * (2 if doubled else 1) if bpb else 4
    first_down = int(np.argmax(pos == 1)) * (2 if doubled else 1)
    by_part = defaultdict(list)
    for r in ref:
        by_part[r["part"]].append(r)
    melody = max(by_part.values(), key=lambda v: np.mean([r["pitch"] for r in v]))  # top part
    plan = plan_free_time(grid, onsets, bpb, first_down, None if doubled else pos == 1,
                          tempo_onsets=np.array([r["onset"] for r in melody]))
    spans_s = [(s0, s1) for _, _, s0, s1, _ in plan.spans]

    def run(beats, coarse):
        q = quantize(ref, beats, auto_level=False, coarse=coarse)
        by_key = {(round(x.onset_s, 6), x.pitch): x for x in q}
        return [(r, by_key[(round(r["onset"], 6), r["pitch"])]) for r in ref]

    variants = {"grid": run(grid, None), "free": run(plan.beat_times, plan.beat_ranges or None)}
    inside = lambda r: any(s0 <= r["onset"] < s1 for s0, s1 in spans_s)  # noqa: E731
    edges = sorted({-np.inf, np.inf} | {x for s in spans_s for x in s})
    segments = list(zip(edges, edges[1:]))
    out = {"piece": song.name, "n": len(ref), "regions": [(round(s0, 2), round(s1, 2)) for s0, s1 in spans_s],
           "n_inside": sum(inside(r) for r in ref)}
    for name, pairs in variants.items():
        strict = [(r, x) for r, x in pairs if not inside(r)]
        out[name] = _strict_scores(strict, segments)
        m, t = _shape([(r, x) for r, x in pairs if inside(r)])
        out[name]["inside_shape"] = m / t if t else None
        out[name]["inside_pairs"] = t
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dirs", type=Path, nargs="+")
    args = ap.parse_args()
    rows = []
    for d in args.eval_dirs:
        for song in sorted(p for p in d.iterdir() if (p / "reference.json").exists()):
            r = evaluate(song)
            rows.append(r)
            g, f = r["grid"], r["free"]
            print(f"{r['piece']:40s} regions={r['regions']} inside={r['n_inside']:4d} "
                  f"strict pos {g['position']:.3f}->{f['position']:.3f} sub {g['subdivision']:.3f}->{f['subdivision']:.3f} "
                  f"dur {g['duration']:.3f}->{f['duration']:.3f}"
                  + (f" | inside shape {g['inside_shape']:.3f}->{f['inside_shape']:.3f} ({f['inside_pairs']} IOIs)"
                     if f["inside_shape"] is not None else ""))
    summary = {}
    for v in ("grid", "free"):
        summary[v] = {k: round(float(np.mean([r[v][k] for r in rows])), 3) for k in ("position", "subdivision", "duration")}
    summary["pieces_with_regions"] = sum(bool(r["regions"]) for r in rows)
    summary["pieces"] = len(rows)
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
