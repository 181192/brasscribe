"""The faithful soloist rule (trumpet.md §2.1) against today's placement, on played lines.

Input lines are ChoraleBricks note annotations (what each player played, sounding pitch) and,
where cached, the SwiftF0 transcription of the same stem (`--tracked DIR` with
<song>.<stem>.sw.mid, from docs/plan/my-instrument/run_adapters.sh). Each line goes on the
small band's Solo Cornet (B♭ cornet, solo range 52-84) as a faithful lead, and the script counts
notes written in another octave than played (for tracked lines: than the annotation at the same
onset, within 0.1 s). Run from the repo root:

    uv run --project music --with pretty_midi python docs/plan/trumpet/soloist_rule.py [--tracked DIR] [--phrase]

--phrase measures the variant that moves a whole phrase when any note is outside (not taken).
"""
from __future__ import annotations

import csv
import sys
from collections import defaultdict
from pathlib import Path

from dataclasses import replace

from brasscribe_music.arranger import _hold_small_gaps, _moved, _phrases, _place_line, place_soloist
from brasscribe_music.instruments import MINIMAL_BAND, Part
from brasscribe_music.score_model import Note

REPO = Path(__file__).resolve().parents[3]
CB = REPO / "data/choralebricks/01_AudioAndAnnotations"
NAMES = {"tp": "Trumpet", "fh": "Flugelhorn", "fho": "French horn", "bar": "Baritone", "tb": "Trombone", "tba": "Tuba"}
SOLO = (52, 84)
SHARE = 0.95
# "note": arranger.place_soloist (a phrase keeps its octave, and only the notes outside move);
# "phrase": the variant not taken, where a phrase moves as a whole when any note is outside.
RULE = "phrase" if "--phrase" in sys.argv else "note"
TPS = 48  # ticks per second for the tick mapping (as my-instrument/measure.py)
TOL = 5  # ticks, about 0.1 s


def soloist(notes: list[Note], lo: int, hi: int) -> list[Note] | None:
    """The rule (arranger.place_soloist): None when under SHARE of the line is inside."""
    if not notes or sum(lo <= n.pitch <= hi for n in notes) < SHARE * len(notes):
        return None
    if RULE == "note":
        return place_soloist(notes, Part("Solo Cornet", replace(MINIMAL_BAND.by_name("Solo Cornet").instrument, solo=(lo, hi))), [])
    placed: list[Note] = []
    for ph in _phrases(notes):
        ps = [n.pitch for n in ph]
        prev = placed[-1].pitch if placed else None
        ks = [k for k in (0, -1, 1, -2, 2, -3, 3) if all(lo <= p + 12 * k <= hi for p in ps)]
        if ks:
            best = min(ks, key=lambda k: (abs(k), abs(ps[0] + 12 * k - prev) if prev is not None else 0))
            placed.extend(_moved(n, n.pitch + 12 * best) for n in ph)
            continue
        for n in ph:
            opts = [n.pitch % 12 + 12 * j for j in range(11) if lo <= n.pitch % 12 + 12 * j <= hi]
            r = placed[-1].pitch if placed else n.pitch
            placed.append(_moved(n, min(opts, key=lambda x: (abs(x - r), x))))
    return _hold_small_gaps(placed)


def ref_notes(p: Path) -> list[Note]:
    rows = list(csv.DictReader(p.open(), delimiter=";"))
    return [Note(int(r["pitch"]), round(float(r["start_sec"]) * TPS), max(1, round((float(r["end_sec"]) - float(r["start_sec"])) * TPS)))
            for r in rows]


def tracked_notes(p: Path) -> list[Note]:
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(p))
    return [Note(n.pitch, round(n.start * TPS), max(1, round((n.end - n.start) * TPS))) for i in pm.instruments for n in i.notes]


def moved(line: list[Note], placed: list[Note], truth: dict[int, int]) -> tuple[int, int]:
    """(notes compared, notes written in another octave than the played note).

    A placed note is compared with the annotated note of the same pitch class whose onset is
    nearest, within TOL ticks (0.1 s, the onset tolerance of the my-instrument measurements)."""
    ref = sorted(truth.items())
    pairs = []
    for n in placed:
        near = [(abs(t - n.start), p) for t, p in ref if abs(t - n.start) <= TOL and p % 12 == n.pitch % 12]
        if near:
            pairs.append((n.pitch, min(near)[1]))
    return len(pairs), sum(a != b for a, b in pairs)


def main() -> None:
    tracked = Path(sys.argv[sys.argv.index("--tracked") + 1]) if "--tracked" in sys.argv else None
    part = MINIMAL_BAND.by_name("Solo Cornet")
    rows = defaultdict(lambda: defaultdict(int))
    for song in sorted(p for p in CB.iterdir() if p.is_dir()):
        for ann in sorted((song / "annotations").glob("*_notes.csv")):
            abbr = ann.stem.split("_")[1]
            if abbr not in NAMES:
                continue
            ref = ref_notes(ann)
            truth = {n.start: n.pitch for n in ref}
            srcs = [("played", ref)]
            if tracked and (t := tracked / f"{song.name}.{ann.stem.removesuffix('_notes')}.sw.mid").exists():
                srcs.append(("tracked", tracked_notes(t)))
            for tag, line in srcs:
                R = rows[(NAMES[abbr], tag)]
                R["stems"] += 1
                n0, m0 = moved(line, _place_line(line, part, []), truth)
                rule = soloist(line, *SOLO)
                R["gated"] += rule is not None
                n1, m1 = moved(line, rule if rule is not None else _place_line(line, part, []), truth)
                R["n"] += n0
                R["today"] += m0
                R["rule"] += m1
    print(f"{'instrument':12} {'line':8} {'stems':>5} {'in register':>11} {'notes':>6} {'today moved':>11} {'rule moved':>10}")
    for (name, tag), R in rows.items():
        print(f"{name:12} {tag:8} {R['stems']:5} {R['gated']:11} {R['n']:6} {R['today'] / max(1, R['n']):11.1%} {R['rule'] / max(1, R['n']):10.1%}")


if __name__ == "__main__":
    main()
