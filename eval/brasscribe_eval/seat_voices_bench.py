"""Can a player's own voice be picked out of a four-part brass recording by their seat's range?

ChoraleBricks brass4 mixes (S trumpet, A flugelhorn, T baritone, B tuba) with the cached MuScriptor
medium and Basic Pitch MIDI, and their consensus (notes both found). Per voice, one monophonic line
inside the seat's professional range: the top line for S, the bottom line for B, then A as the top
and T as the bottom line of what is left. One pass, no tuning. Scored with onset F1 at 100 ms against
the voice. This measures how far "follow my line" in a section recording is from shippable; inner
parts stay arranged until a seat's voice reaches F1 0.85 here.

    python -m brasscribe_eval.seat_voices_bench [--data DIR]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np

from .consensus import cluster
from .lead_sheet import line
from .paths import DATA
from .solo_instruments_bench import score

# Voice -> the seat whose range picks it out.
VOICE_SEATS = {"S": "solo-cornet", "A": "flugelhorn", "T": "1st-baritone", "B": "eb-bass"}
SOURCES = ("muscriptor-medium", "basic-pitch", "consensus")


def _key(n: dict) -> tuple[float, int]:
    return (round(n["onset"], 3), n["pitch"])


def voices(est: list[dict]) -> dict[str, list[dict]]:
    """S, A, T, B lines from one transcription of the mix, by seat range."""
    from brasscribe_music.instruments import seat_by_id

    rng = {v: seat_by_id(s).band_part.instrument.pro for v, s in VOICE_SEATS.items()}
    s = line(est, *rng["S"], top=True)
    b = line(est, *rng["B"], top=False)
    taken = {_key(n) for n in s + b}
    rest = [n for n in est if _key(n) not in taken]
    a = line(rest, *rng["A"], top=True)
    taken |= {_key(n) for n in a}
    t = line([n for n in rest if _key(n) not in taken], *rng["T"], top=False)
    return {"S": s, "A": a, "T": t, "B": b}


def evaluate(eval_dir: Path) -> dict[str, float]:
    from .arrange_layers_song import pitched

    rows: dict[str, list[float]] = {}
    for song in sorted(p for p in eval_dir.iterdir() if (p / "reference.json").exists()):
        ref = json.loads((song / "reference.json").read_text())
        ref = ref["notes"] if isinstance(ref, dict) else ref
        mus, bp = pitched(song / "muscriptor-medium.mid"), pitched(song / "basic-pitch.mid")
        both = [c for c in cluster({"mus": mus, "bp": bp}) if len(c.sources) == 2]
        cons = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets))} for c in both]
        for src, est in zip(SOURCES, (mus, bp, cons)):
            for v, got in voices(est).items():
                s = score([n for n in ref if n["part"] == v], got)
                rows.setdefault(f"{src}.{v}_f1", []).append(s["f1"])
                rows.setdefault(f"{src}.{v}_recall", []).append(s["recall"])
    return {k: round(float(np.mean(v)), 4) for k, v in rows.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=DATA / "eval" / "choralebricks-brass4")
    args = ap.parse_args()
    res = evaluate(args.data)
    for src in SOURCES:
        print(f"{src:18}" + "  ".join(f"{v}: F1 {res[f'{src}.{v}_f1']:.2f} R {res[f'{src}.{v}_recall']:.2f}" for v in "SATB"))


if __name__ == "__main__":
    main()
