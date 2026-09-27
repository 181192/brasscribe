"""Section recording: can the player's own voice be picked out of a four-part brass mix by range?

ChoraleBricks brass4 mixes (S trumpet, A flugelhorn, T baritone, B tuba), cached MuScriptor medium
and Basic Pitch MIDI. Per voice: a monophonic line inside that seat's range (top line for S,
bottom for B; A and T from what is left after S and B are taken), scored against the voice.
"""
from __future__ import annotations

import json
from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

from brasscribe_eval.lead_sheet import line

EV = Path("/Users/k/private/brasscribe/data/eval/choralebricks-brass4")
TOL = 0.10
RANGE = {"S": (52, 82), "A": (52, 82), "T": (40, 70), "B": (24, 72)}


def midi(p):
    pm = pretty_midi.PrettyMIDI(str(p))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if not i.is_drum for n in i.notes]


def arr(ns):
    if not ns:
        return np.zeros((0, 2)), np.zeros(0)
    return (np.array([[n["onset"], max(n["offset"], n["onset"] + 0.01)] for n in ns]),
            mir_eval.util.midi_to_hz(np.array([n["pitch"] for n in ns], float)))


def f1(ref, est):
    if not est:
        return 0.0, 0.0
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(*arr(ref), *arr(est), onset_tolerance=TOL, offset_ratio=None)
    return f, r


def key(n):
    return (round(n["onset"], 3), n["pitch"])


res = {m: {v: [] for v in "SATB"} for m in ("muscriptor-medium", "basic-pitch")}
for d in sorted(EV.iterdir()):
    if not (d / "reference.json").exists():
        continue
    ref = json.loads((d / "reference.json").read_text())
    ref = ref["notes"] if isinstance(ref, dict) else ref
    for m in res:
        est = midi(d / f"{m}.mid")
        s = line(est, *RANGE["S"], top=True)
        b = line(est, *RANGE["B"], top=False)
        taken = {key(n) for n in s + b}
        rest = [n for n in est if key(n) not in taken]
        a = line(rest, *RANGE["A"], top=True)
        taken |= {key(n) for n in a}
        t = line([n for n in rest if key(n) not in taken], *RANGE["T"], top=False)
        for v, e in zip("SATB", (s, a, t, b)):
            res[m][v].append(f1([n for n in ref if n["part"] == v], e))

for m, vs in res.items():
    print(m, "  ".join(f"{v}: F1 {np.mean([x[0] for x in xs]):.2f} R {np.mean([x[1] for x in xs]):.2f}" for v, xs in vs.items()))
