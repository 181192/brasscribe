"""Draft lead sheet: melody + bass lines -> quantized MusicXML (+ PDF via MuseScore).

Melody is the top line of the melody source within a pitch window; bass is the
bottom line of the bass source. Beats come from Beat This! (time, beat-in-bar).
"""

from __future__ import annotations

from brasscribe_music import musescore

import argparse
import subprocess
from collections import Counter
from pathlib import Path

import numpy as np
from brasscribe_music.musicxml import PartSpec, build_score, write_musicxml
from brasscribe_music.quantize import TICKS_PER_BEAT, fill_gaps, quantize

from .consensus import consensus
from .score import load_notes


SPLIT_MIN_DUR = 0.03  # notes from the contour's pitch-change onsets (onsets.py): 32nds at 150 BPM are 50 ms
SPLIT_MERGE = 0.02


def line(notes: list[dict], lo: int, hi: int, top: bool, min_dur: float = 0.06) -> list[dict]:
    """Extract a monophonic line: highest (or lowest) note among overlapping candidates.

    Notes marked "split" (pitch-change onsets from the contour) are kept down to SPLIT_MIN_DUR, and two of
    them compete for one onset only within SPLIT_MERGE."""
    cand = sorted((n for n in notes if lo <= n["pitch"] <= hi
                   and n["offset"] - n["onset"] >= (SPLIT_MIN_DUR if n.get("split") else min_dur)),
                  key=lambda n: n["onset"])
    out: list[dict] = []
    for n in cand:
        merge = SPLIT_MERGE if n.get("split") and out and out[-1].get("split") else 0.05
        if out and n["onset"] - out[-1]["onset"] < merge:
            better = n["pitch"] > out[-1]["pitch"] if top else n["pitch"] < out[-1]["pitch"]
            if better:
                out[-1] = n
            continue
        out.append(n)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--beats", type=Path, required=True)
    ap.add_argument("--melody", type=Path, required=True, help="primary melody source (MuScriptor)")
    ap.add_argument("--melody-support", type=Path, help="second opinion (Basic Pitch); unconfirmed notes are flagged")
    ap.add_argument("--bass", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True, help="output .musicxml")
    ap.add_argument("--title", default="Draft")
    ap.add_argument("--melody-range", default="52,86", help="MIDI lo,hi (default E3..D6, trumpet)")
    ap.add_argument("--bass-range", default="28,55")
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args()

    b = np.loadtxt(args.beats)
    times, pos = b[:, 0], b[:, 1].astype(int)
    beats_per_bar = Counter(np.diff(np.where(pos == 1)[0])).most_common(1)[0][0]
    bpm = 60 / np.median(np.diff(times))
    first_down = int(np.argmax(pos == 1))
    pickup = first_down * TICKS_PER_BEAT

    mlo, mhi = map(int, args.melody_range.split(","))
    blo, bhi = map(int, args.bass_range.split(","))
    # Melody = top line over MuScriptor-supported notes (best on melody_bench); notes the
    # second model did not confirm keep confidence 0.6 and are flagged in the score.
    sources = {"mus": load_notes(args.melody)}
    if args.melody_support:
        sources["bp"] = load_notes(args.melody_support)
    cand, _ = consensus(sources, {"mus": 0.6, "bp": 0.4}, 0.5)
    melody = fill_gaps(quantize(line(cand, mlo, mhi, top=True), times, monophonic=True), TICKS_PER_BEAT // 2)
    bass = fill_gaps(quantize(line(load_notes(args.bass), blo, bhi, top=False), times, monophonic=True), TICKS_PER_BEAT // 2)

    score = build_score([PartSpec("Melody", melody), PartSpec("Bass", bass, clef="bass")],
                        beats_per_bar=int(beats_per_bar), bpm=float(bpm), title=args.title, pickup_ticks=pickup, low_confidence=0.7)
    write_musicxml(score, args.out)
    print(f"{args.out}: {len(melody)} melody / {len(bass)} bass notes, {beats_per_bar}/4 at {bpm:.0f} BPM")
    if args.pdf:
        pdf = args.out.with_suffix(".pdf")
        pdf.unlink(missing_ok=True)
        # MuseScore 4.7 CLI aborts during shutdown after writing its output; trust the file, not the exit code.
        musescore.convert(args.out, pdf)
        if not pdf.exists():
            raise SystemExit(f"MuseScore did not produce {pdf}")
        print(pdf)


if __name__ == "__main__":
    main()
