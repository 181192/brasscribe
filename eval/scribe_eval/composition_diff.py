"""Note-level diff of two composition.json files, split at a time (e.g. the end of an intro).

Notes are matched per voice by pitch and performed onset (within 50 ms), so a
changed tick map does not count as a change of notes. For matched notes it
reports how often the written length changed and by how much in seconds
(written ticks mapped through each file's own beat_times). For the solo
voice it also reports, per side of the split, the written note values as
seconds and beats, and how much of the time the solo line sounds on paper.

    uv run python -W ignore -m brasscribe_eval.composition_diff OLD.json NEW.json --split 29.76
"""

from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import numpy as np
from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap
from brasscribe_music.score_model import Composition


def _seconds(comp: Composition):
    bm = BeatMap(np.array(comp.beat_times))

    def f(tick: float) -> float:
        return float(bm.to_seconds(np.array([tick / TICKS_PER_BEAT + comp.first_downbeat]))[0])
    return f


def _match(a, b):
    used = set()
    pairs, only_a = [], []
    for n in a:
        best = None
        for j, m in enumerate(b):
            if j in used or m.pitch != n.pitch or n.onset_s is None or m.onset_s is None:
                continue
            d = abs(m.onset_s - n.onset_s)
            if d <= 0.05 and (best is None or d < best[0]):
                best = (d, j)
        if best is None:
            only_a.append(n)
        else:
            used.add(best[1])
            pairs.append((n, b[best[1]]))
    return pairs, only_a, [m for j, m in enumerate(b) if j not in used]


def diff(old: Composition, new: Composition, split: float) -> dict:
    so, sn = _seconds(old), _seconds(new)
    out = {}
    for vo in old.voices:
        vn = next(v for v in new.voices if v.id == vo.id)
        if all(n.onset_s is None for n in vo.notes + vn.notes):
            out[vo.id] = {"all": {"old": len(vo.notes), "new": len(vn.notes), "note": "no performed onsets stored; counts only"}}
            continue
        row = {}
        for side, sel in (("before", lambda n: (n.onset_s or 0) < split), ("after", lambda n: (n.onset_s or 0) >= split)):
            a, b = [n for n in vo.notes if sel(n)], [n for n in vn.notes if sel(n)]
            pairs, only_old, only_new = _match(a, b)
            dur_changed = [(so(n.end) - so(n.start), sn(m.end) - sn(m.start)) for n, m in pairs
                           if abs((so(n.end) - so(n.start)) - (sn(m.end) - sn(m.start))) > 0.03]
            longer = sum(y > x for x, y in dur_changed)
            row[side] = {"old": len(a), "new": len(b), "matched": len(pairs), "only_old": len(only_old),
                         "only_new": len(only_new), "written_len_changed": len(dur_changed), "longer": longer,
                         "shorter": len(dur_changed) - longer,
                         "median_len_s_old": round(float(np.median([so(n.end) - so(n.start) for n in a])), 3) if a else None,
                         "median_len_s_new": round(float(np.median([sn(m.end) - sn(m.start) for m in b])), 3) if b else None,
                         "articulations_new": dict(Counter(x.value for m in b for x in m.articulations))}
        out[vo.id] = row
    return out


def solo_values(comp: Composition, t0: float, t1: float) -> dict:
    s = _seconds(comp)
    solo = sorted((n for v in comp.voices if v.id == "solo" for n in v.notes if t0 <= (n.onset_s or 0) < t1),
                  key=lambda n: n.start)
    if not solo:
        return {}
    lens = [n.dur / TICKS_PER_BEAT for n in solo]
    secs = [s(n.end) - s(n.start) for n in solo]
    span = s(solo[-1].end) - s(solo[0].start)
    return {"notes": len(solo), "written_beats": dict(sorted(Counter(round(x, 3) for x in lens).items())),
            "median_written_s": round(float(np.median(secs)), 3), "sounding_share": round(sum(secs) / span, 3),
            "shorter_than_8th": sum(x < 0.5 for x in lens)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("old", type=Path)
    ap.add_argument("new", type=Path)
    ap.add_argument("--split", type=float, required=True, help="seconds: report before/after separately")
    args = ap.parse_args()
    old, new = Composition.from_json(args.old), Composition.from_json(args.new)
    print("free regions:", json.dumps([vars(r) | {"notation": r.notation.value} for r in new.free_regions]))
    for voice, row in diff(old, new, args.split).items():
        for side, d in row.items():
            print(f"{voice:8s} {side:6s} " + " ".join(f"{k}={v}" for k, v in d.items()))
    print("solo intro, old:", json.dumps(solo_values(old, 0, args.split)))
    print("solo intro, new:", json.dumps(solo_values(new, 0, args.split)))


if __name__ == "__main__":
    main()
