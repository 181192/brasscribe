"""What the solo path writes for each brass instrument (ChoraleBricks single-instrument stems).

Frozen inputs, no models run: eval/fixtures/choralebricks-solo/<song>/<stem>.{sw,bp}.mid (SwiftF0 and
Basic Pitch on the stem), <stem>.contour.npz (the SwiftF0 frame contour: note ends and confidence),
<stem>.beats (Beat This! small0 on the stem) and <stem>.notes.csv (the ChoraleBricks note annotation,
sounding pitch). Every stem goes through the real solo path,
arrange_layers_song with only a solo layer (Basic Pitch also stands in for MuScriptor, as on the
phone), once as today (no seat) and, with `seats=True`, once for the player's seat.

Per instrument (mean over its stems), scored with mir_eval onset F1 at 100 ms against the annotation:
  sw_f1, bp_f1        the trackers alone
  today_f1/_recall    the written solo line without a seat (the fixed MIDI 52-88 window)
  seat_f1/_recall     the same with the seat (the window of the seat's instrument)
  octave_err          share of annotated notes missed with an estimate an octave or two off (seat)
  bp_agrees           share of the solo line's notes Basic Pitch also found (seat)
  cornet_moved        share of the written notes the arranger puts in another octave than the line (today)
  seat_moved          the same on the seat's part (place_as_played: only notes outside the pro range)
  q_false_alarm       share of correct notes marked "?" (seat)
  q_hit               share of wrong notes marked "?" (seat)
  q_missed            wrong notes without a "?", per 100 written notes (seat; lower is better)

    python -m brasscribe_eval.solo_instruments_bench [--json FILE]
"""

from __future__ import annotations

import argparse
import contextlib
import csv
import io
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import mir_eval
import numpy as np

from .paths import ROOT

FIXTURES = ROOT / "eval" / "fixtures" / "choralebricks-solo"
TOL = 0.10
# ChoraleBricks instrument -> (label, the closest brass-band seat). French horn stands in for the tenor
# horn and the (German) baritone for the euphonium; the tuba plays the bass an octave down (E♭ Bass).
INSTRUMENTS = {"tp": ("trumpet", "solo-cornet"), "fh": ("flugelhorn", "flugelhorn"), "fho": ("horn", "solo-horn"),
               "tb": ("trombone", "1st-trombone"), "bar": ("baritone", "euphonium"), "tba": ("tuba", "eb-bass")}
LOW_BRASS = ("trombone", "baritone", "tuba")


def stems(root: Path = FIXTURES) -> list[tuple[Path, str]]:
    """(fixture directory, stem name) of every stem with all four fixture files."""
    out = []
    for song in sorted(p for p in root.iterdir() if p.is_dir()):
        for sw in sorted(song.glob("*.sw.mid")):
            stem = sw.name[: -len(".sw.mid")]
            if stem.split("_", 1)[1] in INSTRUMENTS and all((song / f"{stem}{x}").exists()
                                                             for x in (".bp.mid", ".beats", ".notes.csv")):
                out.append((song, stem))
    return out


def reference(path: Path) -> list[dict]:
    rows = list(csv.DictReader(path.open(), delimiter=";"))
    return [{"pitch": int(r["pitch"]), "onset": float(r["start_sec"]), "offset": float(r["end_sec"])} for r in rows]


def _arrays(ns: list[dict]):
    if not ns:
        return np.zeros((0, 2)), np.zeros(0)
    return (np.array([[n["onset"], max(n["offset"], n["onset"] + 0.01)] for n in ns]),
            mir_eval.util.midi_to_hz(np.array([n["pitch"] for n in ns], float)))


def score(ref: list[dict], est: list[dict]) -> dict:
    """Onset F1 and recall (100 ms), octave errors, and which estimated notes are right."""
    if not est:
        return {"f1": 0.0, "recall": 0.0, "octave_err": 0.0, "right": []}
    ri, rp = _arrays(ref)
    ei, ep = _arrays(est)
    _, r, f, _ = mir_eval.transcription.precision_recall_f1_overlap(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None)
    pairs = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None)
    matched_ref, matched_est = {i for i, _ in pairs}, {j for _, j in pairs}
    octv = sum(1 for i, n in enumerate(ref) if i not in matched_ref and any(
        abs(e["onset"] - n["onset"]) <= TOL and abs(e["pitch"] - n["pitch"]) in (12, 24) for e in est))
    return {"f1": float(f), "recall": float(r), "octave_err": octv / max(1, len(ref)),
            "right": [j in matched_est for j in range(len(est))]}


def solo_take(song: Path, stem: str, seat: str | None, work: Path):
    """(Composition, Arrangement) of one stem through arrange_layers_song, as the solo profile runs it."""
    from . import arrange_layers_song

    layers = work / "layers"
    shutil.rmtree(layers, ignore_errors=True)
    layers.mkdir(parents=True)
    shutil.copy(song / f"{stem}.sw.mid", layers / "solo-sw.mid")
    shutil.copy(song / f"{stem}.bp.mid", layers / "solo-bp.mid")
    shutil.copy(song / f"{stem}.bp.mid", layers / "solo-mus.mid")  # Basic Pitch stands in for MuScriptor
    if (song / f"{stem}.contour.npz").exists():
        shutil.copy(song / f"{stem}.contour.npz", layers / "solo-sw.contour.npz")
    argv = ["--layers", str(layers), "--beats", str(song / f"{stem}.beats"), "--out", str(work / "out"),
            "--title", stem, "--no-render", "--lineup", "minimal", *(["--seat", seat] if seat else [])]
    with contextlib.redirect_stdout(io.StringIO()):
        return arrange_layers_song.build(arrange_layers_song.parse_args(argv))


def _solo(comp) -> list:
    return [n for v in comp.voices if v.layer == "solo" for n in v.notes]


def _moved(comp, arr) -> float:
    """Share of the solo line's notes the arrangement writes in another octave (or drops)."""
    line = _solo(comp)
    if not line:
        return float("nan")
    lead = next(p for p in arr.lineup.parts if p.name == arr.lineup.lead)
    by_start = {n.start: n.pitch for n in arr.parts.get(lead.name, [])}
    return sum(1 for n in line if by_start.get(n.start) != n.pitch) / len(line)


def _as_dicts(notes) -> list[dict]:
    return [{"pitch": n.pitch, "onset": n.onset_s, "offset": n.offset_s} for n in notes if n.onset_s is not None]


def evaluate(seats: bool = False, root: Path = FIXTURES, notes: list | None = None) -> dict[str, dict[str, float]]:
    """Per-instrument metrics; with `notes`, every seat-take note is appended to it as
    (song, instrument, confidence, pitch, right)."""
    from brasscribe_music.confidence import Model

    from .arrange_layers_song import pitched

    mark = 1 - Model.load().mark_risk
    rows: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    with tempfile.TemporaryDirectory() as tmp:
        for song, stem in stems(root):
            label, seat = INSTRUMENTS[stem.split("_", 1)[1]]
            R = rows[label]
            ref = reference(song / f"{stem}.notes.csv")
            R["stems"].append(1)
            for tag in ("sw", "bp"):
                R[f"{tag}_f1"].append(score(ref, pitched(song / f"{stem}.{tag}.mid"))["f1"])
            comp, arr = solo_take(song, stem, None, Path(tmp))
            s = score(ref, _as_dicts(_solo(comp)))
            R["today_f1"].append(s["f1"])
            R["today_recall"].append(s["recall"])
            R["cornet_moved"].append(_moved(comp, arr))
            if not seats:
                continue
            comp, arr = solo_take(song, stem, seat, Path(tmp))
            line = [n for n in _solo(comp) if n.onset_s is not None]
            s = score(ref, _as_dicts(line))
            R["seat_f1"].append(s["f1"])
            R["seat_recall"].append(s["recall"])
            R["octave_err"].append(s["octave_err"])
            R["seat_moved"].append(_moved(comp, arr))
            bp = pitched(song / f"{stem}.bp.mid")
            R["bp_agrees"].append(float(np.mean([any(b["pitch"] == n.pitch and abs(b["onset"] - n.onset_s) <= TOL for b in bp)
                                                  for n in line])) if line else float("nan"))
            right = s["right"]
            if notes is not None:
                notes.extend((song.name, label, n.confidence, n.pitch, r) for n, r in zip(line, right))
            marked = [n.confidence < mark for n in line]
            ok = [m for m, r in zip(marked, right) if r]
            bad = [m for m, r in zip(marked, right) if not r]
            if ok:
                R["q_false_alarm"].append(float(np.mean(ok)))
            if bad:
                R["q_hit"].append(float(np.mean(bad)))
            # wrong notes the reader is not warned about, per 100 notes: q_hit is a share of the wrong notes,
            # which falls when the easy-to-flag wrong notes stop being made at all
            R["q_missed"].append(100 * sum(1 for m in bad if not m) / max(1, len(line)))
    out = {}
    for label, R in rows.items():
        out[label] = {k: (float(len(v)) if k == "stems" else round(float(np.nanmean(v)), 4)) for k, v in R.items()}
    return out


def metrics(seats: bool = False, root: Path = FIXTURES) -> dict[str, float]:
    """Flat suite metrics: <instrument>.<metric>."""
    return {f"{label}.{k}": v for label, m in evaluate(seats, root).items() for k, v in m.items()
            if k != "stems" and not np.isnan(v)}


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-4, 1 - 1e-4)
    return np.log(p / (1 - p))


LOW_REGISTER = 52  # E3, the floor of the solo window without a seat: "low" is the octaves below it


def fit_low(notes: list, grid: np.ndarray = np.round(np.arange(-3.0, 6.01, 0.05), 2)) -> dict:
    """What a low-register input (octaves below E3) would weigh in the confidence model with every other
    weight held, by maximum
    likelihood on the seat-take notes; also left out song by song (fitted on the other songs, the
    "?" rates measured on the one left out)."""
    from brasscribe_music.confidence import Model

    mark = 1 - Model.load().mark_risk
    songs = np.array([n[0] for n in notes])
    z = _logit(np.array([n[2] for n in notes], float))
    low = np.array([max(0, LOW_REGISTER - n[3]) / 12 for n in notes], float)
    y = np.array([n[4] for n in notes], float)

    def best(mask: np.ndarray) -> float:
        ll = [np.sum(y[mask] * -np.log1p(np.exp(-(z[mask] + w * low[mask])))
                     + (1 - y[mask]) * -np.log1p(np.exp(z[mask] + w * low[mask]))) for w in grid]
        return float(grid[int(np.argmax(ll))])

    held = np.zeros(len(notes), bool)
    marked_lo = np.zeros(len(notes), bool)
    for song in sorted(set(songs)):
        out = songs == song
        w = best(~out)
        marked_lo[out] = 1 / (1 + np.exp(-(z[out] + w * low[out]))) < mark
        held |= out
    before = 1 / (1 + np.exp(-z)) < mark
    rate = lambda m, sel: float(np.mean(m[sel])) if sel.any() else float("nan")  # noqa: E731
    lowmask = low > 0
    return {"low": best(np.ones(len(notes), bool)), "notes": len(notes), "low_notes": int(lowmask.sum()),
            "false_alarm_low_before": rate(before, lowmask & (y == 1)), "false_alarm_low_after": rate(marked_lo, lowmask & (y == 1)),
            "hit_low_before": rate(before, lowmask & (y == 0)), "hit_low_after": rate(marked_lo, lowmask & (y == 0))}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--fit-low", action="store_true",
                    help="fit the confidence model's low-register weight on the seat takes (leave-one-song-out check)")
    ap.add_argument("--no-seat", action="store_true", help="only today's path (no seat)")
    ap.add_argument("--json", type=Path)
    args = ap.parse_args()
    notes: list = []
    res = evaluate(seats=not args.no_seat or args.fit_low, notes=notes)
    keys = sorted({k for m in res.values() for k in m})
    print(f"{'':11}" + " ".join(f"{k:>13}" for k in keys))
    for label, m in res.items():
        print(f"{label:11}" + " ".join(f"{m.get(k, float('nan')):13.3f}" for k in keys))
    if args.fit_low:
        fit = fit_low(notes)
        print(json.dumps(fit, indent=1))
        res["fit_low"] = fit
    if args.json:
        args.json.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
