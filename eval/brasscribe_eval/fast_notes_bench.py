"""Where fast notes and two-note alternations are lost: a stage-by-stage waterfall of the solo path.

Every clip of the fast-notes set (fast_notes.py: frozen tracker outputs in eval/fixtures/fast-notes, or
data/eval/fast-notes) goes through the real solo path, arrange_layers_song with only a solo layer and Basic
Pitch standing in for MuScriptor (as on the phone), with the oracle beats and with Beat This! small0.
It is scored at each stage against the performed ground truth:

  contour    the SwiftF0 frame contour: the note's pitch holds for at least half of its middle frames
  sw, bp     the trackers' notes (SwiftF0 segment_notes at 80 ms hold; Basic Pitch)
  line       the solo line: SwiftF0-anchored consensus, line(), contour note ends
  q_ref      the reference notes themselves quantized on the same grid: what quantization loses on its own
  quantized  the line on the beat grid (quantize), mapped back to seconds through the beat grid
  written    the Composition's solo voice (ticks back to seconds)
  lead:<d>   the arranged lead part at difficulty d (faithful, standard, easier)

Metrics (notes matched one to one; a reference note's window is 50 ms, or less where its neighbours are
closer: half the smaller inter-onset interval):
  onset_f1    onset F1, any pitch
  onset25_f1  the same at 25 ms
  note_f1     onset + pitch F1
  fig_recall  note recall on the figure under test (the two bars of fast notes)
  alt_kept    alternation clips: share of clips whose figure keeps >= 80 % of its notes on the right pitches
  extra       control clips: extra notes per reference note in the figure span (false splits; must be 0)

    python -m brasscribe_eval.fast_notes_bench [--only PATTERN] [--beats oracle,small0] [--json FILE]
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import shutil
import tempfile
from collections import defaultdict
from pathlib import Path

import numpy as np
from scipy.optimize import linear_sum_assignment

from .fast_notes import FIXTURES, OUT

STAGES = ("contour", "sw", "bp", "line", "q_ref", "quantized", "written", "lead:faithful", "lead:standard", "lead:easier")
TOL = 0.05


def clips(root: Path | None = None) -> list[Path]:
    for r in ([root] if root else [FIXTURES, OUT]):
        if r.exists() and any(r.iterdir()):
            return sorted(p for p in r.iterdir() if (p / "reference.json").exists() and (p / "sw.contour.npz").exists())
    return []


def tolerances(ref: list[dict], tol: float) -> np.ndarray:
    on = np.array([n["onset"] for n in ref])
    ioi = np.diff(on)
    near = np.minimum(np.r_[np.inf, ioi], np.r_[ioi, np.inf])
    return np.minimum(tol, near / 2)


def match(ref: list[dict], est: list[dict], tol: float = TOL, pitch: bool = True) -> list[tuple[int, int]]:
    """One-to-one matching (Hungarian on onset distance) inside each reference note's window."""
    if not ref or not est:
        return []
    tols = tolerances(ref, tol)
    ro = np.array([n["onset"] for n in ref])[:, None]
    eo = np.array([n["onset"] for n in est])[None, :]
    d = np.abs(ro - eo)
    ok = d <= tols[:, None]
    if pitch:
        ok &= np.array([n["pitch"] for n in ref])[:, None] == np.array([n["pitch"] for n in est])[None, :]
    cost = np.where(ok, d, 1e6)
    r, c = linear_sum_assignment(cost)
    return [(i, j) for i, j in zip(r, c) if ok[i, j]]


def f1(n_match: int, n_ref: int, n_est: int) -> float:
    return 2 * n_match / (n_ref + n_est) if n_ref + n_est else 1.0


def contour_present(ref: list[dict], contour_npz: Path) -> list[dict]:
    """Reference notes whose pitch the contour holds for at least half of the note's middle half."""
    d = np.load(contour_npz)
    t, hz, conf = d["t"], d["pitch_hz"], d["confidence"]
    with np.errstate(divide="ignore", invalid="ignore"):
        midi = np.where(hz > 0, 69 + 12 * np.log2(hz / 440), np.nan)
    out = []
    for n in ref:
        a = n["onset"] + 0.25 * (n["offset"] - n["onset"])
        b = n["offset"] - 0.25 * (n["offset"] - n["onset"])
        m = (t >= a) & (t <= b)
        if not m.any():
            m = np.abs(t - (a + b) / 2) == np.abs(t - (a + b) / 2).min()
        good = (np.abs(np.nan_to_num(midi[m], nan=99) - n["pitch"]) < 0.5) & (conf[m] > 0.5)
        if good.mean() >= 0.5:
            out.append(n)
    return out


def _seconds(ticks: list[int], times: np.ndarray) -> np.ndarray:
    from brasscribe_music.quantize import TICKS_PER_BEAT, BeatMap

    return BeatMap(times).to_seconds(np.asarray(ticks, float) / TICKS_PER_BEAT)


def run_clip(clip: Path, beats: str, work: Path, argv_extra: list[str] | None = None, seg=None,
             ref: list[dict] | None = None) -> dict[str, list[dict]]:
    """Estimated notes (pitch, onset in seconds) at every stage for one clip."""
    from brasscribe_music.arranger import arrange_layers, composition_lineup
    from brasscribe_music.quantize import TICKS_PER_BEAT

    from . import arrange_layers_song as A
    from .arrange_layers_song import pitched

    layers = work / "layers"
    shutil.rmtree(layers, ignore_errors=True)
    layers.mkdir(parents=True)
    sw = clip / "sw.mid"
    if seg is not None:  # re-segment the contour (ablation)
        seg(clip / "sw.contour.npz", layers / "solo-sw.mid")
    elif sw.exists():
        shutil.copy(sw, layers / "solo-sw.mid")
    if (clip / "bp.mid").exists():
        shutil.copy(clip / "bp.mid", layers / "solo-bp.mid")
        shutil.copy(clip / "bp.mid", layers / "solo-mus.mid")
    shutil.copy(clip / "sw.contour.npz", layers / "solo-sw.contour.npz")
    bf = clip / ("oracle.beats" if beats == "oracle" else f"{beats}.beats")
    out: dict[str, list[dict]] = {"sw": pitched(layers / "solo-sw.mid"), "bp": pitched(clip / "bp.mid")}
    if not out["sw"]:
        return {**out, **{s: [] for s in STAGES if s not in out}}
    argv = ["--layers", str(layers), "--beats", str(bf), "--out", str(work / "out"), "--title", clip.name,
            "--no-render", "--lineup", "minimal", *(argv_extra or [])]
    trace: dict = {}
    with contextlib.redirect_stdout(io.StringIO()):
        comp, _ = A.build(A.parse_args(argv), trace)
    times, pickup = trace["times"], trace["pickup"]
    out["line"] = trace["line"]
    q = trace["quantized"]
    if ref:
        from brasscribe_music.quantize import quantize

        qr = quantize([dict(n) for n in ref], times, monophonic=True, auto_level=False, coarse=trace["coarse"])
        out["q_ref"] = [{"pitch": x.pitch, "onset": float(s)} for x, s in zip(qr, _seconds([x.start for x in qr], times))]
    out["quantized"] = [{"pitch": p, "onset": float(s)} for (p, _, _), s in zip(q, _seconds([x[1] for x in q], times))]
    solo = [n for v in comp.voices if v.layer == "solo" for n in v.notes]
    out["written"] = [{"pitch": n.pitch, "onset": float(s)} for n, s in
                      zip(solo, _seconds([n.start + pickup for n in solo], times))]
    for d in ("faithful", "standard", "easier"):
        with contextlib.redirect_stdout(io.StringIO()):
            arr = arrange_layers(comp, composition_lineup(comp)[0], difficulty=d)
        lead = arr.parts.get(arr.lineup.lead, [])
        lead = [n for n in lead if n.pitch > 0]
        out[f"lead:{d}"] = [{"pitch": n.pitch, "onset": float(s)} for n, s in
                            zip(lead, _seconds([n.start + pickup for n in lead], times))]
    return out


def score_clip(ref_doc: dict, est: dict[str, list[dict]], clip: Path) -> dict[str, dict]:
    ref = ref_doc["notes"]
    fig = [i for i, n in enumerate(ref) if n["role"] == "figure"]
    lo = ref[fig[0]]["onset"] - 0.03 if fig else 0
    hi = ref[fig[-1]]["offset"] if fig else 0
    kind = ref_doc["spec"]["kind"]
    res = {}
    est = {**est, "contour": contour_present(ref, clip / "sw.contour.npz")}
    for stage in STAGES:
        e = est.get(stage, [])
        m_on = match(ref, e, pitch=False)
        m_on25 = match(ref, e, 0.025, pitch=False)
        m = match(ref, e)
        matched = {i for i, _ in m}
        r = {"onset_f1": f1(len(m_on), len(ref), len(e)), "onset25_f1": f1(len(m_on25), len(ref), len(e)),
             "note_f1": f1(len(m), len(ref), len(e)),
             "fig_recall": sum(i in matched for i in fig) / max(1, len(fig))}
        if stage == "contour":  # a contour is not a note list: only recall means anything
            r = {"fig_recall": r["fig_recall"]}
        if kind == "alt" and stage != "contour":
            r["alt_kept"] = float(r["fig_recall"] >= 0.8)
            span = [n for n in e if lo <= n["onset"] <= hi]
            lower = min(ref[i]["pitch"] for i in fig)
            r["upper_share"] = float(np.mean([n["pitch"] > lower for n in span])) if span else float("nan")
        if kind.startswith("ctl-") and stage != "contour":
            matched_e = {j for _, j in m}
            span = [j for j, n in enumerate(e) if lo <= n["onset"] <= hi]
            r["extra"] = sum(j not in matched_e for j in span) / max(1, len(fig))
        res[stage] = r
    return res


def group_of(spec: dict) -> str:
    k = spec["kind"]
    if k == "urmp":
        return "urmp-trumpet"
    if k == "chorale":
        return f"chorale-{spec['art']}"
    if k.startswith("ctl-"):
        return k
    rate = spec["tempo"] / 60 * spec["subdiv"]
    band = "<=8/s" if rate <= 8 else "9-12/s" if rate <= 12 else ">12/s"
    return f"{k}-{spec['art']} {band}"


def evaluate(root: Path | None = None, beats=("oracle", "small0"), only: str | None = None,
             argv_extra: list[str] | None = None, seg=None, per_clip: dict | None = None) -> dict:
    """Mean metrics per (beats, group, stage)."""
    rows: dict = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    with tempfile.TemporaryDirectory() as tmp:
        for clip in clips(root):
            if only and only not in clip.name:
                continue
            ref_doc = json.loads((clip / "reference.json").read_text())
            for b in beats:
                if b != "oracle" and not (clip / f"{b}.beats").exists():
                    continue
                try:
                    est = run_clip(clip, b, Path(tmp), argv_extra, seg, ref_doc["notes"])
                except (ValueError, IndexError, SystemExit) as e:  # e.g. a beat track with under two beats
                    print(f"{clip.name} ({b} beats): {type(e).__name__}: {e}")
                    est = {}
                sc = score_clip(ref_doc, est, clip)
                if per_clip is not None:
                    per_clip[(b, clip.name)] = sc
                for g in (group_of(ref_doc["spec"]), f"all-{ref_doc['spec']['render']}", "all"):
                    if g.startswith("all") and ref_doc["spec"]["kind"].startswith("ctl-"):
                        continue
                    for stage, r in sc.items():
                        for k, v in r.items():
                            rows[b][g][f"{stage}|{k}"].append(v)
    return {b: {g: {k: round(float(np.nanmean(v)), 3) for k, v in m.items()} | {"clips": len(next(iter(m.values())))}
                for g, m in sorted(G.items())} for b, G in rows.items()}


# ------------------------------------------------------------------ ablations: one knob at a time

def segment_contour(npz: Path, hold_ms: float = 80.0) -> list[dict]:
    """swift_f0.music.segment_notes on a saved contour (the same DP, numpy), as MIDI-pitched notes."""
    d = np.load(npz)
    ts, pitch, confidence, level = d["t"], d["pitch_hz"], d["confidence"], d["loudness_db"]
    frame = 0.016
    n = len(ts)
    valid = np.isfinite(pitch) & (pitch > 0)
    if not valid.any():
        return []
    m = np.zeros(n)
    m[valid] = 69.0 + 12.0 * np.log2(pitch[valid] / 440.0)
    w = np.where(valid, confidence, 0.0)
    cc = np.clip(w, 0.01, 0.99)
    padded = np.pad(level, 4, mode="symmetric")
    left = np.maximum.reduce([padded[j: j + n] for j in range(5)])
    right = np.maximum.reduce([padded[4 + j: 4 + j + n] for j in range(5)])
    q = -np.log(cc / (1.0 - cc)) + np.maximum(0.0, np.minimum(left, right) - level - 10 * np.log10(2.0))
    mu = np.unique(np.floor(m[valid] * 100 + 0.5) / 100)
    beta = hold_ms / 1000 / frame
    vn = np.full(len(mu), np.inf)
    note_start = np.zeros(len(mu), dtype=np.intp)
    back = np.zeros(n + 1, dtype=np.intp)
    kind = np.full(n + 1, -1, dtype=np.intp)
    best = 0.0
    for t in range(n):
        start = best + beta
        new = start < vn
        note_start[new] = t
        np.minimum(vn, start, out=vn)
        vn += np.minimum(np.abs(mu - m[t]), 2.0) * w[t] + q[t]
        j = int(np.argmin(vn))
        if vn[j] < best:
            best = float(vn[j])
            back[t + 1] = note_start[j]
            kind[t + 1] = j
        else:
            back[t + 1] = t
    notes = []
    b = n
    while b > 0:
        a = int(back[b])
        if kind[b] >= 0:
            notes.append({"pitch": int(np.floor(mu[kind[b]] + 0.5)), "onset": float(ts[a]),
                          "offset": float(ts[b - 1] + frame)})
        b = a
    return notes[::-1]


def _write_mid(notes: list[dict], dst: Path) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI()
    inst = pretty_midi.Instrument(0)
    inst.notes = [pretty_midi.Note(80, n["pitch"], n["onset"], max(n["offset"], n["onset"] + 0.002)) for n in notes]
    pm.instruments.append(inst)
    pm.write(str(dst))


def resegment(hold_ms: float):
    return lambda npz, dst: _write_mid(segment_contour(npz, hold_ms), dst)


def collision_grids(onset_beats, coarse=None, extra=(8,), collide=1.0):
    """choose_grids, but a grid that puts two onsets of one beat on the same slot pays `collide` per lost note,
    and 32nds (8) are allowed."""
    from brasscribe_music import quantize as Q

    by_beat: dict[int, list[float]] = {}
    for x in onset_beats:
        k = int(np.floor(x + 1 / 12))
        by_beat.setdefault(k, []).append(x - k)
    grids = {**Q.GRIDS, **{g: 0.06 for g in extra}}
    choice = {}
    for k, fracs in by_beat.items():
        f = np.array(fracs)
        allowed = Q.FREE_GRIDS if Q._in_ranges(k, coarse) else tuple(grids)

        def cost(g):
            slots = np.round(f * g)
            lost = len(slots) - len(np.unique(slots))
            return np.sum((f - slots / g) ** 2) + grids[g] * len(f) + collide * lost
        choice[k] = min(allowed, key=cost)
    return choice


ABLATIONS = {
    "today": {},
    "hold40": {"seg": 40.0},
    "hold20": {"seg": 20.0},
    "line30": {"line": (0.03, 0.02)},
    "grid-collide": {"grids": True},
    "no-free-time": {"argv": ["--no-free-time"]},
    "hold40+line30+grid": {"seg": 40.0, "line": (0.03, 0.02), "grids": True},
}


@contextlib.contextmanager
def ablation(cfg: dict):
    from brasscribe_music import quantize as Q

    from . import arrange_layers_song as A

    saved = (A.line, Q.choose_grids)
    try:
        if "line" in cfg:
            md, merge = cfg["line"]

            def line(notes, lo, hi, top, min_dur=0.06):
                cand = sorted((n for n in notes if lo <= n["pitch"] <= hi and n["offset"] - n["onset"] >= md),
                              key=lambda n: n["onset"])
                out = []
                for n in cand:
                    if out and n["onset"] - out[-1]["onset"] < merge:
                        if (n["pitch"] > out[-1]["pitch"]) if top else (n["pitch"] < out[-1]["pitch"]):
                            out[-1] = n
                        continue
                    out.append(n)
                return out
            A.line = line
        if cfg.get("grids"):
            Q.choose_grids = collision_grids
        yield
    finally:
        A.line, Q.choose_grids = saved


# ------------------------------------------------------------------ Mikkel (no ground truth: proxy counts)

MIKKEL_CONTOUR_SHA = "06d60fa5aae3"  # the contour the golden output was made with (conformance cases.py)


def plateaus(npz: Path, tol: float = 0.35, min_frames: int = 3) -> list[dict]:
    """Stable semitone plateaus of a contour: runs of at least `min_frames` voiced frames (confidence > 0.5)
    within `tol` semitones of one semitone on the piece's own tuning (circular mean of the frames)."""
    d = np.load(npz)
    t, hz, conf = d["t"], d["pitch_hz"], d["confidence"]
    ok = (hz > 0) & (conf > 0.5)
    midi = np.full(len(t), np.nan)
    midi[ok] = 69 + 12 * np.log2(hz[ok] / 440)
    ang = 2 * np.pi * midi[ok]
    tuning = float(np.angle(np.mean(np.exp(1j * ang))) / (2 * np.pi)) if ok.any() else 0.0
    k = np.round(midi - tuning)
    good = ok & (np.abs(midi - tuning - k) <= tol)
    out, a = [], None
    for i in range(len(t) + 1):
        same = i < len(t) and good[i] and a is not None and k[i] == k[a]
        if same:
            continue
        if a is not None and i - a >= min_frames:
            out.append({"pitch": int(k[a]), "onset": float(t[a]), "offset": float(t[i - 1] + 0.016)})
        a = i if i < len(t) and good[i] else None
    # a plateau interrupted by one stray frame and resumed on the same semitone is one note
    merged = []
    for p in out:
        if merged and merged[-1]["pitch"] == p["pitch"] and p["onset"] - merged[-1]["offset"] <= 0.02:
            merged[-1]["offset"] = p["offset"]
        else:
            merged.append(p)
    return merged


def fast_passages(pl: list[dict], ioi: float = 0.16, min_notes: int = 4) -> list[tuple[float, float]]:
    """Time spans of at least `min_notes` consecutive plateaus starting less than `ioi` apart."""
    spans, run = [], [pl[0]] if pl else []
    for a, b in zip(pl, pl[1:]):
        if b["onset"] - a["onset"] < ioi:
            run.append(b)
            continue
        if len(run) >= min_notes:
            spans.append((run[0]["onset"] - 0.02, run[-1]["offset"]))
        run = [b]
    if len(run) >= min_notes:
        spans.append((run[0]["onset"] - 0.02, run[-1]["offset"]))
    return spans


def mikkel_contour() -> Path | None:
    import hashlib

    from .paths import DATA

    here = DATA / "mikkel/repro/layers/solo-sw.contour.npz"
    if here.exists():
        return here
    for p in sorted((DATA / "cache/objects").glob("*/*/files/solo-sw.contour.npz")):
        if hashlib.sha256(p.read_bytes()).hexdigest().startswith(MIKKEL_CONTOUR_SHA):
            return p
    return None


def mikkel(cfg: dict | None = None) -> dict:
    """Notes per stage inside Mikkel's fast passages (found on the solo contour), against the contour's own
    plateaus there: a proxy with no ground truth. Test only; Mikkel is a commercial recording."""
    from .arrange_layers_song import pitched
    from .paths import DATA
    from . import arrange_layers_song as A

    layers, beats, contour = DATA / "mikkel/repro/layers", DATA / "mikkel/repro/mix.beats", mikkel_contour()
    if contour is None or not layers.exists():
        return {}
    cfg = cfg or {}
    pl = plateaus(contour)
    spans = fast_passages(pl)
    with tempfile.TemporaryDirectory() as tmp:
        view = Path(tmp) / "layers"
        view.mkdir()
        for f in layers.iterdir():
            (view / f.name).symlink_to(f)
        if "seg" in cfg:
            (view / "solo-sw.mid").unlink()
            _write_mid(segment_contour(contour, cfg["seg"]), view / "solo-sw.mid")
        argv = ["--layers", str(view), "--beats", str(beats), "--out", str(Path(tmp) / "out"), "--title", "Mikkel",
                "--no-render", "--solo-contour", str(contour), *cfg.get("argv", [])]
        trace: dict = {}
        with ablation(cfg), contextlib.redirect_stdout(io.StringIO()):
            comp, _ = A.build(A.parse_args(argv), trace)
        sw = pitched(view / "solo-sw.mid")
    times, pickup = trace["times"], trace["pickup"]
    q = trace["quantized"]
    solo = [n for v in comp.voices if v.layer == "solo" for n in v.notes]
    stages = {"plateaus": [n["onset"] for n in pl], "sw": [n["onset"] for n in sw],
              "line": [n["onset"] for n in trace["line"]],
              "quantized": list(_seconds([x[1] for x in q], times)),
              "written": list(_seconds([n.start + pickup for n in solo], times))}
    inside = lambda xs: sum(any(a <= x <= b for a, b in spans) for x in xs)  # noqa: E731
    return {"passages": len(spans), "seconds": round(sum(b - a for a, b in spans), 2),
            **{k: inside(v) for k, v in stages.items()}, "total": {k: len(v) for k, v in stages.items()},
            "spans": [(round(a, 2), round(b, 2)) for a, b in spans]}


def table(res: dict, metric: str) -> str:
    lines = []
    for b, G in res.items():
        lines.append(f"\n{metric} ({b} beats)")
        lines.append(f"{'group':28}{'n':>4}" + "".join(f"{s:>15}" for s in STAGES))
        for g, m in G.items():
            lines.append(f"{g:28}{m['clips']:>4}" + "".join(
                f"{m.get(f'{s}|{metric}', float('nan')):>15.3f}" for s in STAGES))
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--only")
    ap.add_argument("--root", type=Path)
    ap.add_argument("--beats", default="oracle,small0")
    ap.add_argument("--metrics", default="fig_recall,note_f1,onset_f1,onset25_f1,alt_kept,upper_share,extra")
    ap.add_argument("--json", type=Path)
    ap.add_argument("--mikkel", action="store_true", help="Mikkel proxy counts (with --ablate: per ablation)")
    ap.add_argument("--ablate", help=f"comma list of {', '.join(ABLATIONS)}: written-stage figure recall per group")
    args = ap.parse_args()
    if args.mikkel:
        for name in (args.ablate or "today").split(","):
            r = mikkel(ABLATIONS[name])
            spans = r.pop("spans", [])
            print(name, json.dumps(r))
        print("passages:", spans)
        return
    if args.ablate:
        out = {}
        for name in args.ablate.split(","):
            cfg = ABLATIONS[name]
            with ablation(cfg):
                out[name] = evaluate(args.root, tuple(args.beats.split(",")), args.only, cfg.get("argv"),
                                     resegment(cfg["seg"]) if "seg" in cfg else None)
        for m in args.metrics.split(","):
            for b in args.beats.split(","):
                groups = sorted({g for r in out.values() for g in r.get(b, {})})
                print(f"\n{m} at the written stage ({b} beats)")
                print(f"{'group':28}" + "".join(f"{k:>20}" for k in out))
                for g in groups:
                    print(f"{g:28}" + "".join(f"{out[k].get(b, {}).get(g, {}).get(f'written|{m}', float('nan')):>20.3f}"
                                              for k in out))
        if args.json:
            args.json.write_text(json.dumps(out, indent=1))
        return
    res = evaluate(args.root, tuple(args.beats.split(",")), args.only)
    for m in args.metrics.split(","):
        print(table(res, m))
    if args.json:
        args.json.write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    main()
