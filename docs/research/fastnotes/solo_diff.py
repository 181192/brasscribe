"""Compare the written solo voice of two composition.json files (before and after a change) on the same recording.

Reports note count, notes shorter than an 8th / 16th, semitone neighbour wiggles (A B A with |A-B| = 1, the
signature of vibrato or a bend split into notes), whole-tone wiggles, and octave-flip pairs, overall and for
held notes that the "before" solo wrote as at least a quarter (where new notes are most likely false splits).

    python docs/research/fastnotes/solo_diff.py before/composition.json after/composition.json
"""

from __future__ import annotations

import json
import sys

TPB = 24  # ticks per beat (composition.json)


def solo(path):
    c = json.load(open(path))
    notes = [n for v in c["voices"] if v.get("layer") == "solo" for n in v["notes"]]
    notes = [n for n in notes if n["pitch"] > 0]
    return sorted(notes, key=lambda n: n["start"])


def stats(ns):
    p = [n["pitch"] for n in ns]
    wig1 = sum(1 for a, b, c in zip(p, p[1:], p[2:]) if a == c and abs(a - b) == 1)
    wig2 = sum(1 for a, b, c in zip(p, p[1:], p[2:]) if a == c and abs(a - b) == 2)
    octs = sum(1 for a, b in zip(p, p[1:]) if abs(a - b) == 12)
    return {"notes": len(ns), "lt_8th": sum(n["dur"] < TPB // 2 for n in ns), "lt_16th": sum(n["dur"] < TPB // 4 for n in ns),
            "semitone_ABA": wig1, "tone_ABA": wig2, "octave_steps": octs,
            "uncertain(<0.5)": sum((n.get("confidence") or 1) < 0.5 for n in ns)}


def main():
    a, b = solo(sys.argv[1]), solo(sys.argv[2])
    sa, sb = stats(a), stats(b)
    for k in sa:
        print(f"{k:18} {sa[k]:6} -> {sb[k]:6}")
    held = [(n["start"], n["start"] + n["dur"]) for n in a if n["dur"] >= TPB]
    inside = [n for n in b if any(s < n["start"] < e for s, e in held)]
    print(f"\nnew onsets inside notes the before-solo held for >= a quarter: {len(inside)} "
          f"(of {len(held)} held notes; semitone from the held pitch: "
          f"{sum(1 for n in inside for s, e in held if s < n['start'] < e and any(abs(m['pitch'] - n['pitch']) == 1 for m in a if m['start'] == s))})")


if __name__ == "__main__":
    main()
