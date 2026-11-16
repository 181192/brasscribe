"""What a player's correction of the beat recovers, through the engine's own code.

For every piece of a brass ensemble set (reference notes with notated positions, Beat This! beats) a player who
knows the score corrects the beat, and the share of notes on their written position is measured again:

  tracked   the beats as tracked, the level chosen from the notes as the engine does
  level     the best level a player can choose (none, as-tracked, double, triple, half or third with its phase)
  holds     every held note the tracker counted through marked, with its written length, on the engine's level
  both      the best level, then the holds on it
  two       the better of the two trackers per piece (source: alternative), where a second tracker's beats exist

Each correction is the JSON an app would send. It goes through the engine's check of the option
(profiles.beat_correction) and the stage that applies it (stages.correct_beats), and the notes are put on the
corrected beats as the arranger does: with a level given the beats are written as they are, otherwise the
level is chosen from the notes. Nothing here knows more than the API's caller would.

    pixi run python -W ignore -m scribe_eval.beat_correction_bench data/eval/choralebricks-brass4 data/eval/urmp-brass
"""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path

import numpy as np

from .quant_bench import evaluate
from .score import load_notes

TRACKED = "beat-this.beats"
ALTERNATIVE = "md-beat-this.beats"  # a second tracker's beats, where a run of one left them
LEVELS = [None, {"level": "as-tracked"}, {"level": "double"}, {"level": "triple"},
          *({"level": "half", "phase": p} for p in range(2)), *({"level": "third", "phase": p} for p in range(3))]
MIN_BEATS = 4  # a level that leaves fewer beats is not offered
HOLD_QUARTERS = 2  # a note this long with no other starting under it can be a hold


def applied(beats_file: Path, beat: dict | None) -> tuple[np.ndarray, tuple[str, ...]]:
    """The beats of `beats_file` after the correction `beat` (the API's JSON), and what the arranger is told
    was given: through the engine's option check and its correcting stage."""
    from scribe_engine import profiles
    from scribe_engine import stages as S
    from scribe_music.beats import Correction

    said = profiles.beat_correction({"beat": beat})
    if said is None:
        return np.loadtxt(beats_file, ndmin=2), ()
    with tempfile.TemporaryDirectory() as tmp:
        ctx = type("ctx", (), {"inputs": {"beats": beats_file}, "out": Path(tmp), "params": {"beat": said},
                               "stage": type("stage", (), {"name": "beats.corrected"}), "log": staticmethod(lambda m: None)})
        S.correct_beats(ctx)
        table = np.loadtxt(Path(tmp) / "mix.beats", ndmin=2)
    given = Correction(said.get("level"), said.get("phase", 0), said.get("beats_per_bar"), said.get("first_downbeat_s"),
                       tuple(S.hold(h) for h in said.get("holds", ()))).given
    return table, given


def position(song: Path, beats_file: Path, beat: dict | None) -> float | None:
    """Share of the reference notes on their written position with the correction; None when it cannot be applied."""
    from scribe_engine.dag import StageFailed

    try:
        table, given = applied(beats_file, beat)
    except StageFailed:
        return None
    if len(table) < MIN_BEATS:
        return None
    return evaluate(song, None, beats_override=table[:, 0], auto_level="level" not in given)["position_acc"]


def engine_level(song: Path, beats_file: Path) -> dict:
    """The level the engine chooses for the piece on its own, as a correction names it."""
    from scribe_engine.beat_hints import chosen_level
    from scribe_music.quantize import choose_level

    times = np.loadtxt(beats_file, ndmin=2)[:, 0]
    onsets = np.array([r["onset"] for r in load_notes(song / "reference.json") if "quarter" in r])
    return {"level": chosen_level(times, choose_level(times, onsets))}


def holds(song: Path, times: np.ndarray) -> list[dict]:
    """The holds a player who knows the score would mark on the beats `times`: where no part starts a note for
    HOLD_QUARTERS notated quarters or more and more beats were tracked in the gap than the score has, the span
    from that note to the next and its written length in beats."""
    ref = [r for r in load_notes(song / "reference.json") if "quarter" in r]
    qs, ts = np.array([r["quarter"] for r in ref]), np.array([r["onset"] for r in ref])
    uq = np.unique(qs)
    ut = np.array([np.median(ts[qs == q]) for q in uq])
    per_q = len(times[(times >= ut[0]) & (times <= ut[-1])]) / max(1.0, uq[-1] - uq[0])
    unit = 1 / round(1 / per_q) if per_q < 0.75 else float(round(per_q))  # the level tracked, in beats per quarter
    out = []
    for q0, t0, q1, t1 in zip(uq, ut, uq[1:], ut[1:]):
        if q1 - q0 < HOLD_QUARTERS:
            continue
        inside = int(np.sum((times > t0 + 0.05) & (times < t1 - 0.05)))
        want = (q1 - q0) * unit
        if round(inside + 1 - want) > 0:
            out.append({"start_s": float(t0), "end_s": float(t1), "beats": max(1, int(round(want)))})
    return out


def corrected(song: Path) -> dict:
    """The position accuracies of one piece (see the module), the corrections that gave them, and their counts."""
    tracked = song / TRACKED
    base = position(song, tracked, None)
    by_level = [(position(song, tracked, lv), lv) for lv in LEVELS]
    best_acc, best = max(((a, lv) for a, lv in by_level if a is not None), key=lambda x: x[0])
    own = engine_level(song, tracked)  # the level in force, which an app sends with the holds (the job's beat_hints)
    marked = holds(song, applied(tracked, own)[0][:, 0])
    held = position(song, tracked, {**own, "holds": marked}) if marked else base
    on_level = holds(song, applied(tracked, best or own)[0][:, 0])
    both = position(song, tracked, {**(best or own), "holds": on_level}) if on_level else best_acc
    out = {"tracked": base, "level": best_acc, "holds": held, "both": both, "best_level": best, "n_holds": len(on_level)}
    if (song / ALTERNATIVE).exists():
        other = position(song, song / ALTERNATIVE, None)
        out.update({"alternative": other, "two": max(base, other)})
    return out


KEYS = ("tracked", "level", "holds", "both", "alternative", "two")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("eval_dir", type=Path, nargs="+")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    report = {}
    for d in args.eval_dir:
        rows = {}
        for song in sorted(p for p in d.iterdir() if (p / "reference.json").exists() and (p / TRACKED).exists()):
            r = rows[song.name] = corrected(song)
            lv = r["best_level"]
            print(f"  {song.name[:38]:38s} " + "  ".join(f"{k} {r[k]:.2f}" for k in KEYS if k in r)
                  + f"  | level {lv['level'] + (' from ' + str(lv['phase']) if 'phase' in lv else '') if lv else 'not changed'}, {r['n_holds']} holds")
        means = {k: round(float(np.mean([r[k] for r in rows.values() if k in r])), 3) for k in KEYS if any(k in r for r in rows.values())}
        print(f"{d.name}: " + "  ".join(f"{k} {v:.3f}" for k, v in means.items())
              + f"  | {sum(r['best_level'] is not None for r in rows.values())} of {len(rows)} pieces gain from a level, "
                f"{sum(r['n_holds'] > 0 for r in rows.values())} have holds")
        report[d.name] = {"mean": means, "pieces": rows}
    if args.json:
        args.json.write_text(json.dumps(report, indent=1))


if __name__ == "__main__":
    main()
