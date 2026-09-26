"""Meter and bar phase on the solo path: every URMP and ChoraleBricks single part, Beat This! small0 beats.

Per part (beats and references from solo_beats.py), the bar grid is built the
way arrange_layers_song builds it, once with the tracker's downbeat labels
taken as they are (before) and once through beats.meter_of (after: labels
when plausible, else the meter inferred from the note accents). The part's
reference notes are quantized on the beats and scored:

  bar_position_acc  notes whose position in the bar (in quarters) equals the score's
  meter_match       the bar length in quarters equals the score's (the tracked beat's length
                    in quarters is estimated from the notated positions, so a tracker running at
                    half or double speed is not penalised twice)

    uv run python -W ignore -m brasscribe_eval.solo_meter_bench ../data/runs/music-core/solo-beats
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from fractions import Fraction
from pathlib import Path

import numpy as np
from brasscribe_music.beats import clean_beats_gated, meter_of
from brasscribe_music.freetime import unstable_runs
from brasscribe_music.quantize import TICKS_PER_BEAT, choose_level, quantize

BEAT_QUARTERS = (0.5, 1.0, 1.5, 2.0, 3.0)
USE_POSITIONS = True


def _bar_grid(b: np.ndarray, onsets: np.ndarray, durations: np.ndarray, infer: bool):
    pos = b[:, 1].astype(int)
    down = pos == 1
    gaps = np.diff(np.where(down)[0])
    bpb = int(Counter(gaps).most_common(1)[0][0]) if len(gaps) else 1
    times = b[:, 0]
    if infer:
        m = meter_of(times, down, onsets, durations, positions=pos if USE_POSITIONS else None)
        bpb, first = m.beats_per_bar, m.first_downbeat
        inferred = not m.from_labels
        if m.times is not None:
            times = m.times
    else:
        first, inferred = int(np.argmax(down)), False
    if not inferred:  # an inferred meter has already fitted the grid to its bar phase
        cb = clean_beats_gated(times, down, bpb, skip=unstable_runs(times), onsets=onsets)
        if cb.applied:
            times, first = cb.times, cb.phase(bpb)
    lvl = choose_level(times, onsets)
    if len(lvl) != len(times):
        bpb, first = bpb * 2, first * 2
    return lvl, bpb, first, inferred


def score_part(notes: list[dict], b: np.ndarray, time_sig: str, infer: bool) -> dict:
    notes = sorted((n for n in notes if "quarter" in n), key=lambda n: n["onset"])
    on = np.array([n["onset"] for n in notes])
    du = np.array([n["offset"] - n["onset"] for n in notes])
    times, bpb, first, inferred = _bar_grid(b, on, du, infer)
    q = quantize(notes, times, auto_level=False)
    by = {(round(x.onset_s, 6), x.pitch): x for x in q}
    beats = [by[(round(n["onset"], 6), n["pitch"])].start / TICKS_PER_BEAT - first for n in notes]
    # Tracked beat length in quarters, from consecutive notated positions.
    ratios = [(b2["quarter"] - b1["quarter"]) / (x2 - x1) for b1, b2, x1, x2 in zip(notes, notes[1:], beats, beats[1:])
              if x2 - x1 > 0 and b2["quarter"] > b1["quarter"]]
    raw = float(np.median(ratios)) if ratios else 1.0
    beat_q = min(BEAT_QUARTERS, key=lambda v: abs(np.log(v / raw)))
    num, den = (int(x) for x in time_sig.split("/"))
    bar_q = Fraction(num * 4, den)
    ours_bar_q = Fraction(bpb) * Fraction(beat_q).limit_denominator(4)
    ok = 0
    for n, x in zip(notes, beats):
        ref = (Fraction(n["measure"]).limit_denominator(48) % 1) * bar_q if "measure" in n \
            else Fraction(n["quarter"]).limit_denominator(48) % bar_q
        ours = (Fraction(x).limit_denominator(48) % bpb) * Fraction(beat_q).limit_denominator(4)
        ok += abs(float(ours % bar_q - ref)) < 1e-3
    return {"notes": len(notes), "bar_position_acc": ok / max(1, len(notes)), "meter_match": ours_bar_q == bar_q,
            "beats_per_bar": bpb, "beat_quarters": beat_q, "inferred": inferred,
            "downbeat_rate": round(float(np.mean(b[:, 1] == 1)), 2)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("root", type=Path, help="solo_beats.py output (urmp/, choralebricks/)")
    ap.add_argument("--list", action="store_true", help="print every part")
    args = ap.parse_args()
    summary = {}
    for set_dir in sorted(p for p in args.root.iterdir() if p.is_dir()):
        rows = []
        for song in sorted(p for p in set_dir.iterdir() if (p / "reference.json").exists()):
            ref = json.loads((song / "reference.json").read_text())
            ts = ref.get("time_sig", "4/4")
            for bf in sorted(song.glob("*.beats")):
                part = bf.stem
                notes = [n for n in ref["notes"] if n["part"] == part]
                b = np.loadtxt(bf, ndmin=2)
                if len([n for n in notes if "quarter" in n]) < 8 or len(b) < 8:
                    continue
                before, after = score_part(notes, b, ts, False), score_part(notes, b, ts, True)
                rows.append((song.name, part, ts, before, after))
                if args.list:
                    print(f"{set_dir.name}/{song.name[:28]:28s} {part:8s} {ts:5s} rate {before['downbeat_rate']:.2f} "
                          f"bpb {before['beats_per_bar']}->{after['beats_per_bar']} "
                          f"acc {before['bar_position_acc']:.2f}->{after['bar_position_acc']:.2f} "
                          f"meter {before['meter_match']}->{after['meter_match']}")
        n = sum(r[3]["notes"] for r in rows)
        summary[set_dir.name] = {
            "parts": len(rows),
            "implausible_labels": sum(r[4]["inferred"] for r in rows),
            "bar_position_acc": {k: round(sum(r[i]["bar_position_acc"] * r[i]["notes"] for r in rows) / n, 3)
                                 for i, k in ((3, "before"), (4, "after"))},
            "bar_position_acc_implausible": {
                k: round(float(np.mean([r[i]["bar_position_acc"] for r in rows if r[4]["inferred"]] or [0])), 3)
                for i, k in ((3, "before"), (4, "after"))},
            "meter_match": {k: round(float(np.mean([r[i]["meter_match"] for r in rows])), 3)
                            for i, k in ((3, "before"), (4, "after"))},
            "parts_worse": sum(r[4]["bar_position_acc"] < r[3]["bar_position_acc"] - 0.01 for r in rows),
        }
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
