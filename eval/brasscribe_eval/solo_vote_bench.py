"""Three-way vote on a separated solo line: MuScriptor, Basic Pitch, SwiftF0.

Cases are solo stems separated with Mega-53 from mixes with a known solo part
(ChoraleBricks soprano = trumpet; Slakh trumpet melody). Each source is first
reduced to one line (top note per onset in the solo range); notes are then
clustered across sources and counted by how many models agree. Reports each
source alone, precision by vote count (to calibrate confidence), and the
line built from >= 2 votes.
"""

from __future__ import annotations

import json
import subprocess
from collections import defaultdict
from pathlib import Path

import mir_eval
import numpy as np

from .consensus import cluster
from .lead_sheet import line
from .paths import ADAPTERS, DATA, EVAL_SETS
from .score import LOOSE_TOL, load_notes, score, to_arrays

STEMS = DATA / "mega53-out-bench"
EVAL = EVAL_SETS
TOOLS = {"mus": "muscriptor", "bp": "basic-pitch", "sw": "swift-f0"}


def cases() -> list[tuple[str, Path, list[dict]]]:
    out = []
    for d in sorted((EVAL / "choralebricks-brass4").iterdir()):
        if (d / "reference.json").exists():
            ref = [n for n in load_notes(d / "reference.json") if n["part"] == "S"]
            out.append((f"chorale:{d.name[:14]}", STEMS / f"cb_{d.name}", ref))
    for t, part in (("Track00006", "S02-Trumpet"), ("Track00014", "S00-Trumpet")):
        ref = [n for n in load_notes(EVAL / "slakh-trumpet" / t / "reference.json") if n["part"] == part]
        out.append((f"slakh:{t}", STEMS / f"slakh_{t}", ref))
    return out


def transcribe(stem_dir: Path) -> dict[str, list[dict]]:
    wav = stem_dir / "trumpet.flac"
    res = {}
    for key, tool in TOOLS.items():
        mid = stem_dir / f"trumpet-{key}.mid"
        if not mid.exists():
            subprocess.run([str(ADAPTERS / tool / "run.sh"), str(wav), str(mid)], check=True)
        res[key] = line(load_notes(mid), 52, 88, top=True)
    return res


def matched(ref: list[dict], est: list[dict]) -> set[int]:
    ri, rp = to_arrays(ref)
    ei, ep = to_arrays(est)
    if not len(est):
        return set()
    return {j for _, j in mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None)}


def main() -> None:
    alone = defaultdict(list)
    by_votes = defaultdict(lambda: [0, 0])  # votes -> [correct, total]
    by_combo = defaultdict(lambda: [0, 0])
    vote2 = []
    for name, stem_dir, ref in cases():
        if not (stem_dir / "trumpet.flac").exists():
            continue
        src = transcribe(stem_dir)
        for k, notes in src.items():
            alone[k].append(score(ref, notes)["onset100_f1"])
        cands = cluster(src)
        notes = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)),
                  "votes": len(c.sources), "combo": "+".join(sorted(c.sources))} for c in cands]
        ok = matched(ref, notes)
        for j, n in enumerate(notes):
            by_votes[n["votes"]][0] += j in ok
            by_votes[n["votes"]][1] += 1
            by_combo[n["combo"]][0] += j in ok
            by_combo[n["combo"]][1] += 1
        v2 = line([n for n in notes if n["votes"] >= 2], 52, 88, top=True)
        vote2.append(score(ref, v2))
        print(f"{name:24s} " + " ".join(f"{k}={alone[k][-1]:.2f}" for k in TOOLS) + f"  vote>=2 F={vote2[-1]['onset100_f1']:.2f}")
    print("mean F1 alone:", {k: round(float(np.mean(v)), 3) for k, v in alone.items()})
    print("vote>=2: F1 %.3f  P %.3f  R %.3f" % tuple(np.mean([r[k] for r in vote2]) for k in ("onset100_f1", "onset100_p", "onset100_r")))
    print("precision by vote count:", {v: f"{c / t:.2f} (n={t})" for v, (c, t) in sorted(by_votes.items())})
    print("precision by combination:", json.dumps({k: f"{c / t:.2f} (n={t})" for k, (c, t) in sorted(by_combo.items())}, indent=1))


if __name__ == "__main__":
    main()
