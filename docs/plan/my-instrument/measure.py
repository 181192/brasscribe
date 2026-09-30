"""What the solo path does for each brass instrument (ChoraleBricks single-instrument stems).

For every brass stem: SwiftF0 and Basic Pitch alone, then the on-device solo rule
(SwiftF0 spine, confirmed by Basic Pitch, which also stands in for MuScriptor) with
today's fixed line window (MIDI 52-88) and with the player's own instrument range.
Then where the arranger writes the line: on Solo Cornet (today) or on the player's
instrument (proposed), as the share of notes moved by an octave from what was played.
"""
from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

import mir_eval
import numpy as np
import pretty_midi

from brasscribe_eval.arrange_solo import solo_line
from brasscribe_eval.lead_sheet import line
from brasscribe_eval.consensus import cluster
from brasscribe_eval.paths import DATA
from brasscribe_music.arranger import _place_line
from brasscribe_music.instruments import MINIMAL_BAND, BRASS_BAND, INSTRUMENTS, Part
from brasscribe_music.score_model import Note

CB = DATA / "choralebricks" / "01_AudioAndAnnotations"
MID = Path(__file__).parent / "mid"
TOL = 0.10
# ChoraleBricks instrument -> closest brass-band instrument (for its range and placement).
MAP = {"tp": ("Trumpet", "bb-cornet"), "fh": ("Flugelhorn", "flugelhorn"), "fho": ("French horn", "eb-tenor-horn"),
       "bar": ("Baritone", "euphonium"), "tb": ("Trombone", "tenor-trombone"), "tba": ("Tuba", "eb-bass")}


def midi_notes(p: Path) -> list[dict]:
    pm = pretty_midi.PrettyMIDI(str(p))
    return [{"pitch": n.pitch, "onset": n.start, "offset": n.end} for i in pm.instruments if not i.is_drum for n in i.notes]


def ref_notes(p: Path) -> list[dict]:
    rows = list(csv.DictReader(p.open(), delimiter=";"))
    return [{"pitch": int(r["pitch"]), "onset": float(r["start_sec"]), "offset": float(r["end_sec"])} for r in rows]


def arrays(ns):
    if not ns:
        return np.zeros((0, 2)), np.zeros(0)
    return (np.array([[n["onset"], max(n["offset"], n["onset"] + 0.01)] for n in ns]),
            mir_eval.util.midi_to_hz(np.array([n["pitch"] for n in ns], float)))


def f1(ref, est):
    ri, rp = arrays(ref)
    ei, ep = arrays(est)
    if not est:
        return 0.0, 0.0, 0.0, 0.0
    p, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None)
    m = {i for i, _ in mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None)}
    octv = sum(1 for i, n in enumerate(ref) if i not in m and any(
        abs(e["onset"] - n["onset"]) <= TOL and abs(e["pitch"] - n["pitch"]) in (12, 24) for e in est))
    return p, r, f, octv / max(1, len(ref))


def vote(sw, bp, lo, hi):
    votes = {"sw": line(sw, lo, hi, top=True), "mus": line(bp, lo, hi, top=True), "bp": line(bp, lo, hi, top=True)}
    cand = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)), "conf": len(c.sources) > 1}
            for c in cluster(votes) if "sw" in c.sources]
    return line(cand, lo, hi, top=True)


def moved_share(notes: list[dict], part: Part) -> float:
    """Share of notes the arranger writes an octave (or more) away from the pitch it was given."""
    if not notes:
        return float("nan")
    ns = [Note(n["pitch"], int(round(n["onset"] * 48)), max(1, int(round((n["offset"] - n["onset"]) * 48)))) for n in notes]
    placed = _place_line(ns, part, [])
    by = {(n.start): n.pitch for n in placed}
    moved = sum(1 for n in ns if n.start in by and by[n.start] != n.pitch)
    dropped = sum(1 for n in ns if n.start not in by)
    return (moved + dropped) / len(ns)


def main() -> None:
    rows = defaultdict(lambda: defaultdict(list))
    for song in sorted(p for p in CB.iterdir() if p.is_dir()):
        for w in sorted((song / "tracks").glob("*.wav")):
            num, abbr = w.stem.split("_", 1)
            if abbr not in MAP:
                continue
            sw_p, bp_p = MID / f"{song.name}.{w.stem}.sw.mid", MID / f"{song.name}.{w.stem}.bp.mid"
            refp = song / "annotations" / f"{w.stem}_notes.csv"
            if not (sw_p.exists() and bp_p.exists() and refp.exists()):
                continue
            name, inst_id = MAP[abbr]
            inst = INSTRUMENTS[inst_id]
            ref = ref_notes(refp)
            sw, bp = midi_notes(sw_p), midi_notes(bp_p)
            key = name
            R = rows[key]
            R["n"].append(len(ref))
            R["pitches"].extend(n["pitch"] for n in ref)
            R["below52"].append(sum(n["pitch"] < 52 for n in ref) / len(ref))
            for tag, est in (("sw", sw), ("bp", bp)):
                p, r, f, o = f1(ref, est)
                R[f"{tag}_f1"].append(f); R[f"{tag}_oct"].append(o)
            today = vote(sw, bp, 52, 88)
            lo, hi = inst.pro
            mine = vote(sw, bp, lo, hi)
            for tag, est in (("today", today), ("mine", mine)):
                p, r, f, o = f1(ref, est)
                R[f"{tag}_f1"].append(f); R[f"{tag}_rec"].append(r); R[f"{tag}_oct"].append(o)
            R["confirmed"].append(sum(n.get("conf", False) for n in mine) / max(1, len(mine)))
            R["cornet_moved"].append(moved_share(mine, MINIMAL_BAND.by_name("Solo Cornet")))
            R["own_moved"].append(moved_share(mine, Part("own", inst)))
            R["ref_cornet_moved"].append(moved_share(ref, MINIMAL_BAND.by_name("Solo Cornet")))
            R["ref_own_moved"].append(moved_share(ref, Part("own", inst)))

    out = {}
    print(f"{'instrument':12} {'stems':>5} {'range':>9} {'<E3':>5} | {'SW F1':>5} {'SW oct':>6} | {'BP F1':>5} {'BP oct':>6} | "
          f"{'today F1':>8} {'rec':>5} | {'own F1':>6} {'rec':>5} {'oct':>5} | {'ref→Cnt':>7} {'ref→own':>7}")
    for k in ("Trumpet", "Flugelhorn", "French horn", "Trombone", "Baritone", "Tuba"):
        R = rows.get(k)
        if not R:
            continue
        m = lambda x: float(np.nanmean(R[x]))
        ps = R["pitches"]
        lo, hi = int(np.percentile(ps, 2)), int(np.percentile(ps, 98))
        out[k] = {x: round(m(x), 3) for x in R if x not in ("n", "pitches")} | {"stems": len(R["n"]), "notes": int(sum(R["n"])),
                 "p2": lo, "p98": hi}
        print(f"{k:12} {len(R['n']):5} {pretty_midi.note_number_to_name(lo):>4}-{pretty_midi.note_number_to_name(hi):<4} {m('below52'):5.0%} | "
              f"{m('sw_f1'):5.2f} {m('sw_oct'):6.1%} | {m('bp_f1'):5.2f} {m('bp_oct'):6.1%} | {m('today_f1'):8.2f} {m('today_rec'):5.2f} | "
              f"{m('mine_f1'):6.2f} {m('mine_rec'):5.2f} {m('mine_oct'):5.1%} | {m('ref_cornet_moved'):7.0%} {m('ref_own_moved'):7.0%} | conf {m('confirmed'):4.0%}")
    Path(__file__).with_name("results.json").write_text(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
