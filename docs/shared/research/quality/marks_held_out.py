"""The review marks, held out for real: the confidence model fitted on the URMP parts and the separated stems
and scored on the ChoraleBricks parts, as it is ("today") and with how far the contour sits from the written
semitone as one or two more inputs (docs/shared/research/18-quality-revisit.md).

    cd eval && uv run python -W ignore ../docs/shared/research/quality/marks_held_out.py \
        ../data/runs/music-core/solo-beats ../data/runs/music-core/stem-contours
"""
import json, sys
from pathlib import Path
import numpy as np
from scribe_music import confidence as C
from scribe_music.durations import Contour
from scribe_eval import confidence_bench as B
from scribe_eval.score import load_notes
from scribe_eval.solo_vote_bench import cases as stem_cases

def tuning(c):
    m = c.midi[np.isfinite(c.midi)]
    if len(m) < 20: return 0.0
    d = m - np.round(m)
    return float(np.median(d))

def pitch_feats(c, tune, onset, offset, pitch):
    if c is None: return 0.0, 0.0
    a, b = np.searchsorted(c.t, onset), np.searchsorted(c.t, max(offset, onset + 0.05))
    m = c.midi[a:b]; m = m[np.isfinite(m)]
    if len(m) == 0: return 0.0, 0.0
    dev = ((m - tune - pitch) + 6) % 12 - 6
    near = dev[np.abs(dev) <= 1.5]
    if len(near) == 0: return 0.5, 1.0
    off = float(abs(np.median(near)))                    # semitones from the written pitch
    other = float(np.mean(np.abs(near) > 0.5))           # share of frames nearer another semitone
    return min(off, 1.0), other

def rows_for(song_id, ref, sources, contour, lo, hi, set_name):
    est = B.candidates(sources, lo, hi); ok = B.label(ref, est); key = B.recording_key(ref)
    tune = tuning(contour) if contour is not None else 0.0
    out = []
    for n, y in zip(est, ok):
        sup = C.support(contour, n["onset"], n["pitch"])
        x = C.features(n["sources"], n["offset"] - n["onset"], sup, separated=set_name == "stems")
        x["off_pitch"], x["other_pitch"] = pitch_feats(contour, tune, n["onset"], n["offset"], n["pitch"])
        out.append({"set": set_name, "song": song_id, "rec": key, "y": bool(y), "x": x})
    return out

single = Path(sys.argv[1]); stemc = Path(sys.argv[2]); rows = []
for name, d, ref in stem_cases():
    if not (d / "trumpet-sw.mid").exists(): continue
    src = {k: load_notes(d / f"trumpet-{k}.mid") for k in ("sw", "mus", "bp")}
    cf = stemc / f"{d.name}.npz"
    rows += rows_for(name, ref, src, Contour.load(cf) if cf.exists() else None, 52, 88, "stems")
for set_dir in sorted(p for p in single.iterdir() if p.is_dir()):
    for song in sorted(p for p in set_dir.iterdir() if (p / "reference.json").exists()):
        ref_all = json.loads((song / "reference.json").read_text())["notes"]
        for sw in sorted(song.glob("*-sw.mid")):
            part = sw.name[:-len("-sw.mid")]
            if not (song / f"{part}-bp.mid").exists(): continue
            ref = [n for n in ref_all if n["part"] == part]
            if len(ref) < 8: continue
            cf = song / f"{part}-sw.contour.npz"
            rows += rows_for(f"{set_dir.name}/{song.name}/{part}", ref, {"sw": load_notes(sw), "bp": load_notes(song / f"{part}-bp.mid")},
                             Contour.load(cf) if cf.exists() else None, 24, 100, "single")
rows = B.dedup(rows)
train = [r for r in rows if not r["song"].startswith("choralebricks/")]
test = [r for r in rows if r["song"].startswith("choralebricks/")]
print("train", len(train), "held out (ChoraleBricks parts)", len(test), "error rate", round(1 - np.mean([r["y"] for r in test]), 3))
def fit(rows, feats, l2=1e-2):
    X = np.array([[r["x"][k] for k in feats] for r in rows]); y = np.array([r["y"] for r in rows], float); w = np.zeros(X.shape[1])
    for _ in range(50):
        p = 1 / (1 + np.exp(-X @ w)); g = X.T @ (p - y) + l2 * w
        H = (X * (p * (1 - p))[:, None]).T @ X + l2 * np.eye(len(w)); w -= np.linalg.solve(H, g)
    return w
for name, feats in (("today", C.FEATURES), ("+off_pitch", C.FEATURES + ("off_pitch",)), ("+other_pitch", C.FEATURES + ("other_pitch",)), ("+both", C.FEATURES + ("off_pitch", "other_pitch"))):
    w = fit(train, feats)
    def risk(rs): return 1 - 1 / (1 + np.exp(-np.array([[r["x"][k] for k in feats] for r in rs]) @ w))
    out = []
    for label, rs in (("held-out", test), ("train", train)):
        pw = risk(rs); wrong = np.array([not r["y"] for r in rs])
        for rate in (0.05, 0.08, 0.12):
            t = np.quantile(pw, 1 - rate); f = pw >= t
            out.append(f"{label} flag {rate:.2f}: recall {f[wrong].mean():.3f} precision {wrong[f].mean():.3f}")
    print(f"{name:13s}", " | ".join(out), "| w", {k: round(float(v), 2) for k, v in zip(feats, w) if k in ("off_pitch", "other_pitch")})
