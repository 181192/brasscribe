"""Difficulty modes, lineups, soprano doubling and figuration, measured.

Per mode (faithful, standard, easier) and lineup:
  sixteenth_solo / sixteenth_rest   share of notes shorter than an 8th (Solo Cornet / all other pitched parts)
  outside_reading / outside_easy    share of pitched notes outside the part's reading / easy range
  uncomfortable                     notes outside the playable comfortable range (as arrange_bench)
  harmony_fidelity                  mean Jaccard of pitch-class sets per source onset, source vs band
  melody_kept                       source melody notes present in Solo Cornet (onset + pitch class)
  contour                           share of the faithful Solo Cornet line's turning points (local highs
                                    and lows) still played, same pitch within an 8th
  key_changes                       key signatures the key plan writes for this mode (Mikkel only)
  soprano_notes                     Soprano Cornet notes (doubling at climaxes; Mikkel only)
  figuration_recall                 source orchestra attacks on the 8th grid that a pad or choir part re-attacks
                                    (Mikkel only)

Sets: the ground-truth arrange_bench compositions (chorales, URMP) through the
minimal arranger, and the Mikkel layered composition through the layered
arranger for both lineups.

    uv run python -W ignore -m brasscribe_eval.difficulty_bench ../data/eval/choralebricks-brass4 ../data/eval/urmp-brass \\
        --mikkel ../data/golden/mikkel-arranged-band.soloist/composition.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
from brasscribe_music.arranger import CHOIR_PARTS, PAD_PARTS, arrange, arrange_layers
from brasscribe_music.difficulty import KEY_CHANGE_PENALTY, MODES, apply_difficulty, easy_range
from brasscribe_music.instruments import BRASS_BAND, MINIMAL_BAND, QUARTET
from brasscribe_music.keys import key_plan
from brasscribe_music.score_model import Composition, VoiceRole

from .arrange_bench import composition_from_reference


def contour(a, b, end: int) -> float:
    """Share of the faithful line's turning points (local highs and lows) that the other line still
    plays: a note of the same pitch starting within an 8th of it."""
    a = sorted(a, key=lambda n: n.start)
    turns = [y for x, y, z in zip(a, a[1:], a[2:]) if (y.pitch - x.pitch) * (z.pitch - y.pitch) < 0]
    if not turns:
        return 1.0
    have = [(n.start, n.pitch) for n in b]
    return sum(any(p == t.pitch and abs(s - t.start) <= 12 for s, p in have) for t in turns) / len(turns)


def metrics(comp: Composition, parts: dict, lineup, faithful_solo=None) -> dict:
    pitched = [(p, n) for p in lineup.parts if p.instrument.clef != "percussion" for n in parts.get(p.name, [])]
    solo = [n for p, n in pitched if p.name == lineup.lead]
    rest = [n for p, n in pitched if p.name != lineup.lead]
    src = [n for v in comp.voices if v.role != VoiceRole.RHYTHM and v.layer != "drums" for n in v.notes]
    band = [n for _, n in pitched]
    jac = []
    for t in sorted({n.start for n in src}):
        a = {n.pitch % 12 for n in src if n.start <= t < n.end}
        b = {n.pitch % 12 for n in band if n.start <= t < n.end}
        if a:
            jac.append(len(a & b) / len(a | b))
    mel = [n for v in comp.voices if v.role == VoiceRole.MELODY for n in v.notes]
    got = {(n.start, n.pitch % 12) for n in solo}
    out = {
        "sixteenth_solo": float(np.mean([n.dur < 12 for n in solo])) if solo else 0.0,
        "sixteenth_rest": float(np.mean([n.dur < 12 for n in rest])) if rest else 0.0,
        "outside_reading": float(np.mean([not p.instrument.preferred[0] <= n.pitch <= p.instrument.preferred[1]
                                          for p, n in pitched])) if pitched else 0.0,
        "outside_easy": float(np.mean([not easy_range(p)[0] <= n.pitch <= easy_range(p)[1] for p, n in pitched]))
        if pitched else 0.0,
        "uncomfortable": int(sum(p.instrument.check(n.pitch) == "uncomfortable" for p, n in pitched)),
        "harmony_fidelity": float(np.mean(jac)) if jac else 0.0,
        "melody_kept": sum((n.start, n.pitch % 12) in got for n in mel) / max(1, len(mel)),
    }
    if faithful_solo is not None:
        out["contour"] = contour(faithful_solo, solo, comp.end_tick)
    return out


def ground_truth(eval_dirs: list[Path]) -> dict:
    res = {}
    for d in eval_dirs:
        rows = {m: [] for m in MODES}
        for song in sorted(p for p in d.iterdir() if (p / "reference.json").exists()):
            comp = composition_from_reference(song, song.name)
            arr = arrange(comp)
            faithful_solo = arr.parts[arr.lineup.lead]
            for m in MODES:
                parts = apply_difficulty(arr.parts, arr.lineup, m)
                rows[m].append(metrics(comp, parts, arr.lineup, faithful_solo))
        res[d.name] = {m: {k: round(float(np.mean([r[k] for r in rs])), 3) for k in rs[0]} for m, rs in rows.items()}
    return res


def mikkel(comp_path: Path) -> dict:
    comp = Composition.from_json(comp_path)
    bar = comp.meters[0].beats * comp.ticks_per_beat
    tonal = [n for v in comp.voices if v.layer in ("solo", "strings") for n in v.notes]
    bass = [n for v in comp.voices if v.layer == "bass" for n in v.notes]
    src_on = sorted({n.start for v in comp.voices if v.layer in ("strings", "brass") for n in v.notes if n.start % 12 == 0})
    res = {}
    for lname, lineup in (("band", BRASS_BAND), ("minimal", MINIMAL_BAND), ("quartet", QUARTET)):
        faithful_solo = None
        for m in MODES:
            arr = arrange_layers(comp, lineup, difficulty=m)
            if m == "faithful":
                faithful_solo = arr.parts[lineup.lead]
            r = metrics(comp, arr.parts, lineup, faithful_solo)
            pen = KEY_CHANGE_PENALTY[m]
            r["key_changes"] = len(key_plan(tonal, bar, bass=bass, **({"penalty": pen} if pen else {})).keys) - 1
            r["soprano_notes"] = len(arr.parts.get("Soprano Cornet", []))
            accompaniment = ([p.name for p in lineup.parts if p.name not in (lineup.lead, lineup.bass)] if lineup.satb
                             else PAD_PARTS + CHOIR_PARTS)
            acc = [n.start for name in accompaniment for n in arr.parts.get(name, [])]
            accs = set(acc)
            r["figuration_recall"] = round(sum(o in accs for o in src_on) / max(1, len(src_on)), 3)
            r["parts"] = sum(bool(v) for v in arr.parts.values())
            res[f"{lname}/{m}"] = {k: round(v, 3) if isinstance(v, float) else v for k, v in r.items()}
    return res


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dirs", type=Path, nargs="*")
    ap.add_argument("--mikkel", type=Path, help="layered composition.json (e.g. the golden Mikkel)")
    args = ap.parse_args()
    out = {}
    if args.eval_dirs:
        out.update(ground_truth(args.eval_dirs))
    if args.mikkel:
        out["mikkel"] = mikkel(args.mikkel)
    print(json.dumps(out, indent=1))


if __name__ == "__main__":
    main()
