"""The solo rule on URMP's real horn, trombone and tuba stems (trumpet as the reference).

Same rule and scoring as measure.py (SwiftF0 spine, Basic Pitch confirming and standing in
for MuScriptor; today's 52-88 window vs the instrument's range). URMP notes are
onset / frequency / duration per line; the pitch is rounded to the nearest semitone.
URMP file tags are sometimes wrong, so a stem whose median pitch contradicts its tag is skipped.
"""
from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import pretty_midi

sys.path.insert(0, str(Path(__file__).parent))
from measure import f1, midi_notes, vote  # noqa: E402
from brasscribe_music.instruments import INSTRUMENTS  # noqa: E402

U = Path("/Users/k/private/brasscribe/data/urmp/Dataset")
MID = Path(__file__).parent / "urmp"
MAP = {"tpt": ("Trumpet", "bb-cornet", (55, 90)), "hn": ("French horn", "eb-tenor-horn", (40, 80)),
       "tbn": ("Trombone", "tenor-trombone", (34, 72)), "tba": ("Tuba", "eb-bass", (20, 60))}


def ref_notes(p: Path) -> list[dict]:
    out = []
    for line in p.read_text().split("\n"):
        xs = line.split()
        if len(xs) >= 3:
            on, hz, dur = map(float, xs[:3])
            out.append({"pitch": int(round(69 + 12 * np.log2(hz / 440))), "onset": on, "offset": on + dur})
    return out


rows = defaultdict(lambda: defaultdict(list))
for sw_p in sorted(MID.glob("*.sw.mid")):
    stem = sw_p.name[: -len(".sw.mid")]  # AuSep_<n>_<inst>_<piece>
    _, n, inst, *rest = stem.split("_")
    piece = "_".join(rest)
    d = next(U.glob(f"{piece.split('_')[0]}_*"))
    ref = ref_notes(d / f"Notes_{n}_{inst}_{piece}.txt")
    name, iid, plaus = MAP[inst]
    med = float(np.median([r["pitch"] for r in ref]))
    if not plaus[0] <= med <= plaus[1]:
        print(f"skip {stem}: median pitch {med} does not fit {inst}")
        continue
    sw, bp = midi_notes(sw_p), midi_notes(MID / f"{stem}.bp.mid")
    R = rows[name]
    R["n"].append(len(ref)); R["pitches"].extend(r["pitch"] for r in ref)
    R["below52"].append(sum(r["pitch"] < 52 for r in ref) / len(ref))
    for tag, est in (("sw", sw), ("today", vote(sw, bp, 52, 88)), ("mine", vote(sw, bp, *INSTRUMENTS[iid].pro))):
        p, r, f, o = f1(ref, est)
        R[f"{tag}_f1"].append(f); R[f"{tag}_rec"].append(r); R[f"{tag}_oct"].append(o)

print(f"{'instrument':12} {'stems':>5} {'range':>9} {'<E3':>5} | {'SW F1':>5} | {'today F1':>8} {'rec':>5} | {'own F1':>6} {'rec':>5} {'oct':>5}")
for k in ("Trumpet", "French horn", "Trombone", "Tuba"):
    R = rows.get(k)
    if not R:
        continue
    m = lambda x: float(np.mean(R[x]))
    lo, hi = int(np.percentile(R["pitches"], 2)), int(np.percentile(R["pitches"], 98))
    print(f"{k:12} {len(R['n']):5} {pretty_midi.note_number_to_name(lo):>4}-{pretty_midi.note_number_to_name(hi):<4} {m('below52'):5.0%} | "
          f"{m('sw_f1'):5.2f} | {m('today_f1'):8.2f} {m('today_rec'):5.2f} | {m('mine_f1'):6.2f} {m('mine_rec'):5.2f} {m('mine_oct'):5.1%}")
