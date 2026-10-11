"""Calibrate solo-note confidence on notes with ground truth, and choose the "?" thresholds.

Sets (solo line built the way arrange_layers_song builds it: each source reduced to its top
line, clustered across sources, SwiftF0-supported candidates kept):
  stems   Mega-53 trumpet stems of 10 ChoraleBricks mixes and 2 Slakh songs (sources sw, mus, bp;
          solo_vote_bench cases), contours from data/runs/music-core/stem-contours
  single  every URMP and ChoraleBricks single part (sources sw, bp; solo_notes.py), a clean recording
A candidate is correct when mir_eval matches it to a reference note (onset 100 ms, pitch).

Fits a logistic regression (brasscribe_music.confidence.FEATURES) on the even-numbered songs
of each set and reports on the odd ones (held out): reliability per bin, and per set the flag
rate / error recall / flag precision at the chosen thresholds, before (the old vote-count
confidence, "?" below 0.7) and after. --write stores the model in
music/src/brasscribe_music/calibration.json.

    uv run python -W ignore -m brasscribe_eval.confidence_bench --single ../data/runs/music-core/solo-beats \\
        --stem-contours ../data/runs/music-core/stem-contours [--write]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import mir_eval
import numpy as np
from brasscribe_music import confidence as C
from brasscribe_music.durations import Contour

from .consensus import cluster
from .lead_sheet import line
from .score import LOOSE_TOL, load_notes, to_arrays
from .solo_vote_bench import cases as stem_cases

OLD_CONF = {3: 0.98, 2: 0.91}  # the vote-count confidence arrange_layers_song used; else 0.54
OLD_MARK = 0.7


def candidates(sources: dict[str, list[dict]], lo: int, hi: int) -> list[dict]:
    votes = {k: line(v, lo, hi, top=True) for k, v in sources.items()}
    cand = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)),
             "sources": set(c.sources)} for c in cluster(votes) if "sw" in c.sources]
    kept = line(cand, lo, hi, top=True)
    return kept


def label(ref: list[dict], est: list[dict]) -> np.ndarray:
    ok = np.zeros(len(est), bool)
    if not est or not ref:
        return ok
    ri, rp = to_arrays(ref)
    ei, ep = to_arrays(est)
    for _, j in mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=LOOSE_TOL, offset_ratio=None):
        ok[j] = True
    return ok


def recording_key(ref: list[dict]) -> str:
    """Identical recordings share their annotation: URMP reuses tracks across piece variants
    (15/16 Surprise, 26/27 King, ...), and they must not land on both sides of the split."""
    import hashlib

    return hashlib.sha1(json.dumps(sorted((round(n["onset"], 3), n["pitch"]) for n in ref)).encode()).hexdigest()[:12]


def rows_for(song_id: str, ref: list[dict], sources: dict[str, list[dict]], contour, lo: int, hi: int, set_name: str):
    est = candidates(sources, lo, hi)
    ok = label(ref, est)
    key = recording_key(ref)
    out = []
    for n, y in zip(est, ok):
        sup = C.support(contour, n["onset"], n["pitch"])
        base = {"set": set_name, "song": song_id, "rec": key, "y": bool(y), "votes": len(n["sources"])}
        out.append(dict(base, x=C.features(n["sources"], n["offset"] - n["onset"], sup, separated=set_name == "stems")))
        # The same note without a contour, so the model also covers runs that have none.
        out.append(dict(base, x=C.features(n["sources"], n["offset"] - n["onset"], None, separated=set_name == "stems"),
                        dropped=True))
    return out


def collect(single_root: Path | None, stem_contours: Path | None) -> list[dict]:
    rows = []
    for name, d, ref in stem_cases():
        if not (d / "trumpet-sw.mid").exists():
            continue
        src = {k: load_notes(d / f"trumpet-{k}.mid") for k in ("sw", "mus", "bp")}
        cf = stem_contours / f"{d.name}.npz" if stem_contours else None
        rows += rows_for(name, ref, src, Contour.load(cf) if cf and cf.exists() else None, 52, 88, "stems")
    if single_root:
        for set_dir in sorted(p for p in single_root.iterdir() if p.is_dir()):
            for song in sorted(p for p in set_dir.iterdir() if (p / "reference.json").exists()):
                ref_all = json.loads((song / "reference.json").read_text())["notes"]
                for sw in sorted(song.glob("*-sw.mid")):
                    if not sw.with_name(sw.name.replace("-sw.mid", "-bp.mid")).exists():
                        continue
                    part = sw.name[: -len("-sw.mid")]
                    ref = [n for n in ref_all if n["part"] == part]
                    if len(ref) < 8:
                        continue
                    src = {"sw": load_notes(sw), "bp": load_notes(song / f"{part}-bp.mid")}
                    cf = song / f"{part}-sw.contour.npz"
                    rows += rows_for(f"{set_dir.name}/{song.name}/{part}", ref, src,
                                     Contour.load(cf) if cf.exists() else None, 24, 100, "single")
    return rows


def fit(rows: list[dict], l2: float = 1e-2, iters: int = 50) -> dict[str, float]:
    X = np.array([[r["x"][k] for k in C.FEATURES] for r in rows])
    y = np.array([r["y"] for r in rows], float)
    w = np.zeros(X.shape[1])
    for _ in range(iters):  # Newton / IRLS
        p = 1 / (1 + np.exp(-X @ w))
        g = X.T @ (p - y) + l2 * w
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w))
        w -= np.linalg.solve(H, g)
    return dict(zip(C.FEATURES, map(float, w)))


def split(rows):
    """Even / odd recordings (not songs: a recording reused by two URMP pieces stays on one side)."""
    recs = sorted({r["rec"] for r in rows})
    train = {s for i, s in enumerate(recs) if i % 2 == 0}
    return [r for r in rows if r["rec"] in train], [r for r in rows if r["rec"] not in train]


def dedup(rows):
    """One copy of each recording's notes (the reused URMP tracks count once)."""
    first: dict[str, str] = {}
    return [r for r in rows if first.setdefault(r["rec"], r["song"]) == r["song"]]


def flag_stats(p_wrong: np.ndarray, wrong: np.ndarray, t: float) -> dict:
    f = p_wrong >= t
    return {"flag_rate": round(float(f.mean()), 3), "error_recall": round(float(f[wrong].mean()), 3) if wrong.any() else 1.0,
            "flag_precision": round(float(wrong[f].mean()), 3) if f.any() else 0.0}


def reliability(p: np.ndarray, y: np.ndarray, bins: int = 5) -> list[tuple[float, float, int]]:
    edges = np.quantile(p, np.linspace(0, 1, bins + 1))
    out = []
    for a, b in zip(edges, edges[1:]):
        m = (p >= a) & (p <= b)
        if m.any():
            out.append((round(float(p[m].mean()), 3), round(float(y[m].mean()), 3), int(m.sum())))
    return out


def mix_classes(eval_dirs: list[Path]) -> dict:
    """Precision per agreement class of MuScriptor and Basic Pitch on full mixes (consensus notes)."""
    out: dict[str, list[bool]] = {}
    for d in eval_dirs:
        for song in sorted(p for p in d.iterdir() if (p / "reference.json").exists()):
            if not (song / "muscriptor-medium.mid").exists() or not (song / "basic-pitch.mid").exists():
                continue
            ref = load_notes(song / "reference.json")
            src = {"mus": load_notes(song / "muscriptor-medium.mid"), "bp": load_notes(song / "basic-pitch.mid")}
            cand = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)),
                     "k": "+".join(sorted(c.sources))} for c in cluster(src)]
            for n, y in zip(cand, label(ref, cand)):
                out.setdefault(f"{d.name}:{n['k']}", []).append(bool(y))
    return {k: {"n": len(v), "precision": round(float(np.mean(v)), 3)} for k, v in sorted(out.items())}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--single", type=Path, help="solo_beats/solo_notes output root")
    ap.add_argument("--stem-contours", type=Path)
    ap.add_argument("--mark-risk", type=float, help="probability of being wrong that earns a ? (default: from --target-flag)")
    ap.add_argument("--target-flag", type=float, default=0.08, help="share of clean training notes to mark")
    ap.add_argument("--refit-all", action="store_true", help="write weights refitted on all rows (thresholds from the split)")
    ap.add_argument("--very-risk", type=float, default=0.6, help="probability of being wrong for a boxed mark")
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--mixes", type=Path, nargs="*", default=[], help="eval sets for the consensus classes on mixes")
    args = ap.parse_args()
    rows = dedup(collect(args.single, args.stem_contours))
    train, test = split(rows)
    ranges = {}
    for k in C.CLAMPED:
        # Per input, the range of the rows where it is informative (a contour present; for the
        # separated interaction, the stems), so clamping never moves the training data itself much.
        vals = [r["x"][k] for r in train if not r.get("dropped") and (k != "sep_support" or r["set"] == "stems")]
        ranges[k] = (round(float(np.quantile(vals, 0.05)), 4), round(float(np.quantile(vals, 0.95)), 4))
    ranges["sep_support"] = (0.0, ranges["sep_support"][1])  # zero outside stems must stay reachable
    for r in rows:
        r["x"] = {k: min(max(v, ranges[k][0]), ranges[k][1]) if k in ranges and not (k == "support" and r.get("dropped"))
                  else v for k, v in r["x"].items()}
    w = fit(train)
    model = C.Model(w, 0.0, 0.0, ranges)
    for r in rows:
        r["p"] = C.p_correct(r["x"], model)
        r["old"] = OLD_CONF.get(r["votes"], 0.54)
    # "?" at the risk that flags args.target_flag of the clean training notes (with a contour);
    # boxed for the top tier, notes very likely wrong.
    clean = np.sort([1 - r["p"] for r in train if r["set"] == "single" and not r.get("dropped")])[::-1]
    mark = round(float(clean[int(args.target_flag * len(clean))]), 3) if args.mark_risk is None else args.mark_risk
    very = args.very_risk
    model = C.Model(w, round(mark, 4), round(very, 4), ranges)
    report = {"weights": {k: round(v, 4) for k, v in w.items()}, "mark_risk": model.mark_risk, "very_risk": model.very_risk,
              "rows": {s: sum(r["set"] == s and not r.get("dropped") for r in rows) for s in ("stems", "single")},
              "recordings": len({r["rec"] for r in rows})}
    for s in ("stems", "single", "no_contour"):
        sub = [r for r in test if (r["set"] == s and not r.get("dropped")) or (s == "no_contour" and r.get("dropped"))]
        if not sub:
            continue
        pw = np.array([1 - r["p"] for r in sub])
        old = np.array([1 - r["old"] for r in sub])
        wrong = np.array([not r["y"] for r in sub])
        report[s] = {
            "notes": len(sub), "error_rate": round(float(wrong.mean()), 3),
            "before": flag_stats(old, wrong, 1 - OLD_MARK + 1e-9),
            "after": flag_stats(pw, wrong, model.mark_risk),
            "after_very": flag_stats(pw, wrong, model.very_risk),
            "reliability_p_correct_vs_actual": reliability(1 - pw, ~wrong),
            "curve": [dict(threshold=round(float(t), 3), **flag_stats(pw, wrong, t))
                      for t in np.quantile(pw, [0.5, 0.7, 0.8, 0.85, 0.9, 0.92, 0.95, 0.98])],
            "per_class": {k: {"n": int(sum(1 for r in sub if "+".join(sorted(r_src(r))) == k)),
                              "precision": round(float(np.mean([r["y"] for r in sub if "+".join(sorted(r_src(r))) == k] or [0])), 3)}
                          for k in sorted({"+".join(sorted(r_src(r))) for r in sub})},
        }
    if args.mixes:
        report["mix_classes"] = mix_classes(args.mixes)
    print(json.dumps(report, indent=1))
    if args.write:
        if args.refit_all:
            report["weights"] = {k: round(v, 4) for k, v in fit(rows).items()}
        C.CALIBRATION.write_text(json.dumps({"weights": report["weights"], "mark_risk": model.mark_risk,
                                             "very_risk": model.very_risk, "ranges": ranges,
                                             "fitted_on": report["rows"]}, indent=1) + "\n")
        print("wrote", C.CALIBRATION)


def r_src(r: dict) -> set[str]:
    x = r["x"]
    return {"sw"} | ({"mus"} if x["mus"] else set()) | ({"bp"} if x["bp"] else set())


if __name__ == "__main__":
    main()
