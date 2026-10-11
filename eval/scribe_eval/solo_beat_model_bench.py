"""Which Beat This! checkpoint writes the better bars for a solo take: small0 (the device's) against final0.

Every single part of URMP and ChoraleBricks that solo_beats.py has beats for goes through the solo path,
arrange_layers_song with only a solo layer, as the engine's solo profile runs it (SwiftF0 the spine, Basic
Pitch standing in for MuScriptor as on the device), once on each checkpoint's beats of the part's own
recording. The written solo line is scored against the part's annotation:

  onset_f1          pitch and onset (100 ms): what the beats do not change much
  written_f1        the same notes, counted right only when they also sit where the score has them in the
                    bar (in quarters): metre, bar phase and the grid together
  bar_position_acc  of the notes matched in pitch and onset, the share in the right place in the bar
  meter_match       parts whose bar is as long, in quarters, as the score's (the tracked beat's length in
                    quarters is read from the matched notes, so a tracker at half or double speed is not
                    counted twice)

The beats are those of solo_beats.py, one folder per checkpoint:

    python -m brasscribe_eval.solo_beats --urmp <URMP Dataset> --choralebricks <ChoraleBricks audio> \\
        --model small0 --out <data>/runs/music-core/solo-beats
    python -m brasscribe_eval.solo_beats ... --model final0 --out <data>/runs/music-core/solo-beats-final0
    python -m brasscribe_eval.solo_beat_model_bench [--data DIR] [--list]

Only the beats differ between the two folders: the transcriptions and the references are the small0
folder's.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
from fractions import Fraction
from pathlib import Path

import mir_eval
import numpy as np

SMALL = "runs/music-core/solo-beats"
FINAL = "runs/music-core/solo-beats-final0"
MODELS = {"small0": SMALL, "final0": FINAL}
SETS = ("urmp", "choralebricks")
TOL = 0.10
BEAT_QUARTERS = (0.5, 1.0, 1.5, 2.0, 3.0)
MIN_NOTES = 8


def parts(data: Path, set_name: str) -> list[tuple[Path, str]]:
    """(song folder in the small0 set, part) of every part with beats from both checkpoints and its transcriptions."""
    root = Path(data) / SMALL / set_name
    out = []
    for song in sorted(p for p in root.iterdir() if (p / "reference.json").exists()) if root.is_dir() else ():
        for beats in sorted(song.glob("*.beats")):
            part = beats.stem
            final = Path(data) / FINAL / set_name / song.name / beats.name
            if final.exists() and (song / f"{part}-sw.mid").exists() and (song / f"{part}-bp.mid").exists():
                out.append((song, part))
    return out


def solo_line(song: Path, part: str, beats: Path, work: Path):
    """The Composition the solo path writes for one part on `beats`."""
    from . import arrange_layers_song

    layers = work / "layers"
    shutil.rmtree(layers, ignore_errors=True)
    layers.mkdir(parents=True)
    shutil.copy(song / f"{part}-sw.mid", layers / "solo-sw.mid")
    shutil.copy(song / f"{part}-bp.mid", layers / "solo-bp.mid")
    shutil.copy(song / f"{part}-bp.mid", layers / "solo-mus.mid")  # Basic Pitch stands in for MuScriptor
    if (song / f"{part}-sw.contour.npz").exists():
        shutil.copy(song / f"{part}-sw.contour.npz", layers / "solo-sw.contour.npz")
    argv = ["--layers", str(layers), "--beats", str(beats), "--out", str(work / "out"), "--title", part,
            "--no-render", "--lineup", "minimal"]
    with contextlib.redirect_stdout(io.StringIO()):
        comp, _ = arrange_layers_song.build(arrange_layers_song.parse_args(argv))
    return comp


def _arrays(ns: list[dict]):
    if not ns:
        return np.zeros((0, 2)), np.zeros(0)
    return (np.array([[n["onset"], max(n["offset"], n["onset"] + 0.01)] for n in ns]),
            mir_eval.util.midi_to_hz(np.array([n["pitch"] for n in ns], float)))


def score_part(ref: list[dict], time_sig: str, comp) -> dict:
    """One part's written line against its annotation (the module docstring's metrics)."""
    line = sorted((n for v in comp.voices if v.layer == "solo" for n in v.notes if n.onset_s is not None), key=lambda n: n.onset_s)
    est = [{"pitch": n.pitch, "onset": n.onset_s, "offset": n.offset_s or n.onset_s + 0.05} for n in line]
    ri, rp = _arrays(ref)
    ei, ep = _arrays(est)
    pairs = mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=TOL, offset_ratio=None) if est else []
    tpb = comp.ticks_per_beat
    bpb = comp.meters[0].beats if comp.meters else 4
    beats = {j: line[j].start / tpb for _, j in pairs}
    ordered = sorted(pairs, key=lambda p: ref[p[0]]["quarter"])
    ratios = [(ref[i2]["quarter"] - ref[i1]["quarter"]) / (beats[j2] - beats[j1])
              for (i1, j1), (i2, j2) in zip(ordered, ordered[1:]) if beats[j2] - beats[j1] > 0 and ref[i2]["quarter"] > ref[i1]["quarter"]]
    raw = float(np.median(ratios)) if ratios else 1.0
    beat_q = Fraction(min(BEAT_QUARTERS, key=lambda v: abs(np.log(v / raw)))).limit_denominator(4)
    num, den = (int(x) for x in time_sig.split("/"))
    bar_q = Fraction(num * 4, den)
    right = 0
    for i, j in pairs:
        r = ref[i]
        want = (Fraction(r["measure"]).limit_denominator(48) % 1) * bar_q if "measure" in r \
            else Fraction(r["quarter"]).limit_denominator(48) % bar_q
        ours = (Fraction(beats[j]).limit_denominator(48) % bpb) * beat_q
        right += abs(float(ours % bar_q - want)) < 1e-3
    n_ref, n_est, n_pair = len(ref), len(est), len(pairs)
    f1 = lambda k: 2 * k / (n_ref + n_est) if n_ref + n_est else 0.0  # noqa: E731
    return {"onset_f1": f1(n_pair), "written_f1": f1(right), "bar_position_acc": right / n_pair if n_pair else 0.0,
            "meter_match": float(Fraction(bpb) * beat_q == bar_q), "beats_per_bar": bpb, "beat_quarters": float(beat_q),
            "notes": n_ref}


def evaluate(data: Path, set_name: str) -> tuple[dict[str, float], list[dict]]:
    """Per checkpoint: mean metrics over the set's parts (written_f1 and onset_f1 also over all its notes), and rows."""
    rows = []
    with tempfile.TemporaryDirectory() as tmp:
        for song, part in parts(data, set_name):
            ref_all = json.loads((song / "reference.json").read_text())
            ref = [n for n in ref_all["notes"] if n["part"] == part and "quarter" in n]
            if len(ref) < MIN_NOTES:
                continue
            row = {"song": song.name, "part": part, "time_sig": ref_all.get("time_sig", "4/4")}
            for model, folder in MODELS.items():
                comp = solo_line(song, part, Path(data) / folder / set_name / song.name / f"{part}.beats", Path(tmp))
                row[model] = score_part(ref, row["time_sig"], comp)
            rows.append(row)
    out: dict[str, float] = {"parts": float(len(rows))}
    for model in MODELS:
        for k in ("onset_f1", "written_f1", "bar_position_acc", "meter_match"):
            out[f"{model}.{k}"] = float(np.mean([r[model][k] for r in rows])) if rows else float("nan")
    for k in ("written_f1", "bar_position_acc", "meter_match"):
        out[f"final0_better.{k}"] = float(sum(r["final0"][k] > r["small0"][k] + 1e-9 for r in rows))
        out[f"small0_better.{k}"] = float(sum(r["small0"][k] > r["final0"][k] + 1e-9 for r in rows))
    return out, rows


def main() -> None:
    from .paths import DATA

    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--data", type=Path, default=DATA)
    ap.add_argument("--list", action="store_true", help="print every part")
    args = ap.parse_args()
    summary = {}
    for set_name in SETS:
        out, rows = evaluate(args.data, set_name)
        summary[set_name] = {k: round(v, 3) for k, v in out.items()}
        for r in rows if args.list else ():
            s, f = r["small0"], r["final0"]
            print(f"{set_name}/{r['song'][:30]:30s} {r['part']:8s} {r['time_sig']:5s} "
                  f"bpb {s['beats_per_bar']}x{s['beat_quarters']}->{f['beats_per_bar']}x{f['beat_quarters']} "
                  f"written {s['written_f1']:.2f}->{f['written_f1']:.2f} pos {s['bar_position_acc']:.2f}->{f['bar_position_acc']:.2f} "
                  f"meter {int(s['meter_match'])}->{int(f['meter_match'])}")
    print(json.dumps(summary, indent=1))


if __name__ == "__main__":
    main()
