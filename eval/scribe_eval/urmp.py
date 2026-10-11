"""Build eval entries from URMP pieces (real recordings, per-track note annotations).

Each piece gets mix.wav (AuMix), reference.json with performed notes per track
(part = "<n>-<instrument>"), and score.mid. Performed notes are aligned to the
score notes of the same track with DTW on pitch, which gives every performed
note its notated position ("quarter", "dur_quarter") for the rhythm benchmark.
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
from pathlib import Path

import numpy as np
import pretty_midi

BRASS = {"tpt", "hn", "tbn", "tba"}


def hz_to_midi(hz: float) -> int:
    return int(round(69 + 12 * np.log2(hz / 440.0)))


def dtw_align(perf: list[int], score: list[int]) -> list[int | None]:
    """Map each performed note index to a score note index (or None) by pitch DTW."""
    n, m = len(perf), len(score)
    cost = np.full((n + 1, m + 1), np.inf)
    cost[0, :] = np.arange(m + 1) * 1.0
    cost[:, 0] = np.arange(n + 1) * 1.0
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            sub = 0.0 if perf[i - 1] == score[j - 1] else (0.5 if (perf[i - 1] - score[j - 1]) % 12 == 0 else 1.5)
            cost[i, j] = min(cost[i - 1, j - 1] + sub, cost[i - 1, j] + 1.0, cost[i, j - 1] + 1.0)
    i, j, out = n, m, [None] * n
    while i > 0 and j > 0:
        sub = 0.0 if perf[i - 1] == score[j - 1] else (0.5 if (perf[i - 1] - score[j - 1]) % 12 == 0 else 1.5)
        if cost[i, j] == cost[i - 1, j - 1] + sub:
            if sub < 1.0:
                out[i - 1] = j - 1
            i, j = i - 1, j - 1
        elif cost[i, j] == cost[i - 1, j] + 1.0:
            i -= 1
        else:
            j -= 1
    return out


def build(piece: Path, out: Path) -> dict | None:
    m = re.match(r"(\d+)_([A-Za-z]+)_(.+)", piece.name)
    if not m:
        return None
    instruments = m.group(3).split("_")
    score_mid = next(piece.glob("Sco_*.mid"))
    pm = pretty_midi.PrettyMIDI(str(score_mid))
    score_tracks = [sorted((n for n in inst.notes), key=lambda n: (n.start, -n.pitch)) for inst in pm.instruments if not inst.is_drum]

    notes, aligned, total = [], 0, 0
    for k, inst in enumerate(instruments, start=1):
        f = next(piece.glob(f"Notes_{k}_*.txt"))  # file instrument tags are sometimes wrong; the folder name is authoritative
        rows = np.loadtxt(f, ndmin=2)
        perf = [{"pitch": hz_to_midi(hz), "onset": float(t), "offset": float(t + d), "part": f"{k}-{inst}", "instrument": inst}
                for t, hz, d in rows if hz > 0]
        if k - 1 < len(score_tracks):
            sc = score_tracks[k - 1]
            idx = dtw_align([p["pitch"] for p in perf], [n.pitch for n in sc])
            for p, j in zip(perf, idx):
                if j is not None:
                    s = sc[j]
                    q0 = pm.time_to_tick(s.start) / pm.resolution
                    q1 = pm.time_to_tick(s.end) / pm.resolution
                    p["quarter"], p["dur_quarter"] = round(q0 * 24) / 24, round((q1 - q0) * 24) / 24
                    aligned += 1
        total += len(perf)
        notes.extend(perf)

    dest = out / piece.name
    dest.mkdir(parents=True, exist_ok=True)
    shutil.copy(next(piece.glob("AuMix_*.wav")), dest / "mix.wav")
    shutil.copy(score_mid, dest / "score.mid")
    notes.sort(key=lambda n: (n["onset"], n["pitch"]))
    (dest / "reference.json").write_text(json.dumps({"parts": {n["part"]: n["instrument"] for n in notes}, "notes": notes}, indent=1))
    ts = [(t.numerator, t.denominator) for t in pm.time_signature_changes]
    print(f"{piece.name}: {total} notes, {aligned / max(1, total):.0%} aligned to score, time sig {ts[:2]}")
    return {"piece": piece.name, "aligned": aligned / max(1, total)}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", type=Path, required=True, help="URMP Dataset dir with NN_piece_inst folders")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--all", action="store_true", help="include non-brass pieces")
    args = ap.parse_args()
    for piece in sorted(p for p in args.root.iterdir() if p.is_dir() and re.match(r"\d+_", p.name)):
        insts = set(piece.name.split("_")[2:])
        if args.all or insts <= BRASS:
            build(piece, args.out)


if __name__ == "__main__":
    main()
