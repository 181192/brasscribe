"""Separation-failure detection on the solo-vote cases (Mega-53 trumpet stems with a known solo part).

A case counts as failed when SwiftF0 on the stem scores onset F1 < 0.5 against
the reference solo; brasscribe_music.separation.check_stem should flag exactly
those, without the reference.

    uv run python -W ignore -m brasscribe_eval.separation_bench
"""

from __future__ import annotations

import json

import numpy as np
import soundfile as sf
from brasscribe_music.separation import check_stem

from .lead_sheet import line
from .score import load_notes, score
from .solo_vote_bench import EVAL, cases


def _mix_of(name: str):
    kind, song = name.split(":")
    if kind == "chorale":
        return next(p for p in (EVAL / "choralebricks-brass4").iterdir() if p.name.startswith(song)) / "mix.wav"
    return EVAL / "slakh-trumpet" / song / "mix.wav"


def main() -> None:
    tp = fp = fn = tn = 0
    for name, d, ref in cases():
        if not (d / "trumpet.flac").exists():
            continue
        f1 = score(ref, line(load_notes(d / "trumpet-sw.mid"), 52, 88, top=True))["onset100_f1"]
        stem, sr = sf.read(d / "trumpet.flac", dtype="float32")
        mix, sr2 = sf.read(_mix_of(name), dtype="float32")
        if sr2 != sr:  # levels only: linear resampling is enough
            mix = mix.mean(axis=1) if mix.ndim > 1 else mix
            mix = np.interp(np.arange(int(len(mix) * sr / sr2)) * sr2 / sr, np.arange(len(mix)), mix).astype(np.float32)
        c = check_stem(stem, mix, sr)
        bad = f1 < 0.5
        tp += bad and c.failed
        fp += (not bad) and c.failed
        fn += bad and not c.failed
        tn += (not bad) and not c.failed
        print(f"{name:26s} F1(sw)={f1:.2f} stem-mix {c.stem_minus_mix_db:6.1f} dB flagged={c.failed}")
    print(json.dumps({"true_pos": tp, "false_pos": fp, "false_neg": fn, "true_neg": tn}))


if __name__ == "__main__":
    main()
