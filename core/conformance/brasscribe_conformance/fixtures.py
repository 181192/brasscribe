"""Unit-level fixtures from the Python reference on seeded synthetic inputs.

    uv run python -m brasscribe_conformance.fixtures

Writes core/brasscribe-core/tests/fixtures/*.json; `cargo test` compares the
Rust functions with them (exact equality). No recorded data is involved.
"""

from __future__ import annotations

import json
import warnings
from pathlib import Path

import numpy as np
from music21 import duration as m21duration

from brasscribe_music.quantize import choose_level, fill_gaps, quantize
from brasscribe_music.spelling import key_of, spell

from .cases import REPO

OUT = REPO / "core" / "brasscribe-core" / "tests" / "fixtures"
warnings.filterwarnings("ignore")


def spelling_cases(rng) -> list[dict]:
    cases = []
    for k in range(120):
        n = int(rng.integers(1, 400))
        # tonal-ish material: a random scale plus chromatic passing notes
        tonic = int(rng.integers(0, 12))
        scale = [(tonic + s) % 12 for s in (0, 2, 4, 5, 7, 9, 11)]
        pcs = [scale[i] if rng.random() > 0.2 else int(rng.integers(0, 12)) for i in rng.integers(0, 7, size=n)]
        pitches = [int(12 * rng.integers(3, 7) + pc) for pc in pcs]
        ticks = np.sort(rng.integers(0, 24 * 64, size=n)) // int(rng.choice([1, 6, 8, 12]))
        onsets = [float(t) / 24 for t in ticks]
        durs = [float(rng.integers(1, 97)) / 24 for _ in range(n)]
        sp = spell(onsets, durs, pitches)
        name, fifths = key_of(onsets, durs, pitches)
        cases.append({"onsets": onsets, "durations": durs, "pitches": pitches,
                      "spelled": [[s, a, o] for s, a, o in sp], "key": name, "fifths": fifths})
    return cases


def quantize_cases(rng) -> list[dict]:
    cases = []
    for k in range(80):
        nb = int(rng.integers(4, 200))
        ibi = rng.uniform(0.35, 1.3) * rng.uniform(0.9, 1.1, size=nb)
        beats = np.cumsum(ibi) + rng.uniform(0, 2)
        n = int(rng.integers(1, 300))
        on = np.sort(rng.uniform(beats[0] - 1, beats[-1] + 1, size=n))
        off = on + rng.uniform(0.03, 2.0, size=n)
        notes = [{"pitch": int(p), "onset": float(a), "offset": float(b)} for p, a, b in
                 zip(rng.integers(30, 90, size=n), on, off)]
        mono, auto = bool(k % 2), bool(k % 3)
        q = quantize(notes, beats, monophonic=mono, auto_level=auto)
        g = fill_gaps([type(x)(**vars(x)) for x in q], 12, 0.0)
        cases.append({"beats": beats.tolist(), "notes": notes, "monophonic": mono, "auto_level": auto,
                      "level": choose_level(beats, on).tolist(),
                      "quantized": [[x.pitch, x.start, x.end] for x in q],
                      "filled": [[x.pitch, x.start, x.end] for x in g]})
    return cases


def argsort_cases(rng) -> list[dict]:
    out = []
    for k in range(200):
        a = rng.integers(20, 100, size=int(rng.integers(1, 600))).astype(np.int32)
        out.append({"values": a.tolist(), "argsort": np.argsort(a).tolist()})
    return out


def duration_cases() -> list[dict]:
    out = []
    for den in (24, 48, 60, 72):
        for num in range(1, 8 * den + 1):
            ql = num / den
            qc = m21duration.quarterConversion(ql)
            t = qc.tuplet
            out.append({"num": num, "den": den,
                        "components": [[c.type, c.dots] for c in qc.components],
                        "tuplet": None if t is None else [t.numberNotesActual, t.numberNotesNormal,
                                                          t.durationNormal.type, t.durationNormal.dots]})
    return out


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(20260925)
    for name, data in (("spelling", spelling_cases(rng)), ("quantize", quantize_cases(rng)),
                       ("argsort", argsort_cases(rng)), ("duration", duration_cases())):
        (OUT / f"{name}.json").write_text(json.dumps(data))
        print(name, len(data))


if __name__ == "__main__":
    main()
