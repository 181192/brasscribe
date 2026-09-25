"""Named benchmark suites with a regression gate (`brasscribe bench <suite>`).

Each suite returns flat metrics. In `cached` mode (the default, and what CPU CI
runs) suites only score model outputs that already exist next to the eval
data (e.g. data/eval/<set>/<song>/muscriptor-medium.mid); no model runs. In
`live` mode the transcription suites run adapters for missing outputs.

The gate compares every metric with eval/baselines.json (numbers taken from
docs/research/10-benchmark-results.md), default tolerance ±0.01. A suite
whose data is missing is reported as skipped, never as passed.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .paths import ADAPTERS, ROOT

BASELINES = ROOT / "eval" / "baselines.json"


class SkipSuite(Exception):
    """The suite's data (or a tool it needs) is not available."""


@dataclass(frozen=True)
class Suite:
    name: str
    description: str
    fn: Callable[[Path, str], dict[str, float]]
    requires: tuple[str, ...] = ()
    cpu: bool = True
    tools: tuple[str, ...] = field(default=())


def _need(data: Path, *rels: str) -> None:
    missing = [r for r in rels if not (data / r).exists()]
    if missing:
        raise SkipSuite(f"missing data: {', '.join(missing)}")


def _songs(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if (p / "reference.json").exists())


def _mean(rows: list[dict], key: str) -> float:
    return float(np.mean([r[key] for r in rows if key in r]))


# ------------------------------------------------------------- transcription

def _transcription(eval_set: str, models: dict[str, list[str]]) -> Callable[[Path, str], dict[str, float]]:
    """Mean metrics per model over an eval set, from <song>/<model>.mid."""
    adapters = {"basic-pitch": "basic-pitch", "muscriptor-medium": "muscriptor"}

    def fn(data: Path, mode: str) -> dict[str, float]:
        from .score import load_notes, score

        root = data / "eval" / eval_set
        _need(data, f"eval/{eval_set}")
        out: dict[str, float] = {}
        for model, keys in models.items():
            rows = []
            for song in _songs(root):
                mid = song / f"{model}.mid"
                if not mid.exists() and mode == "live" and model in adapters:
                    subprocess.run([str(ADAPTERS / adapters[model] / "run.sh"), str(song / "mix.wav"), str(mid)], check=True)
                if not mid.exists():
                    raise SkipSuite(f"no cached {model}.mid for {song.name}")
                rows.append(score(load_notes(song / "reference.json"), load_notes(mid)))
            for k in keys:
                out[f"{model}.{k}"] = _mean(rows, k)
        return out

    return fn


# -------------------------------------------------------------------- rhythm

def _quant(eval_set: str) -> Callable[[Path, str], dict[str, float]]:
    def fn(data: Path, mode: str) -> dict[str, float]:
        from .quant_bench import evaluate, reference_beats

        _need(data, f"eval/{eval_set}")
        out: dict[str, float] = {}
        songs = _songs(data / "eval" / eval_set)
        ref_rows = [evaluate(s, None, beats_override=reference_beats(s)) for s in songs]
        bt = [s for s in songs if (s / "beat-this.beats").exists()]
        bt_rows = [evaluate(s, None, "beat-this.beats") for s in bt]
        for label, rows in (("reference_beats", ref_rows), ("beat_this", bt_rows)):
            for k in ("position_acc", "subdivision_acc", "duration_acc"):
                out[f"{label}.{k}"] = _mean(rows, k)
        out["beat_this.songs"] = float(len(bt))
        return out

    return fn


# -------------------------------------------------------------------- melody

def _melody(data: Path, mode: str) -> dict[str, float]:
    from .consensus import consensus, load_sources
    from .lead_sheet import line
    from .score import load_notes, score

    _need(data, "eval/slakh-trumpet", "eval/urmp-brass", "eval/choralebricks-brass4")
    d = data / "eval"
    cases = []
    other = "mix_(other)_BS-Roformer-SW"
    for t, part in (("Track00006", "S02-Trumpet"), ("Track00014", "S00-Trumpet")):
        s = d / "slakh-trumpet" / t
        src = {"mus": load_sources({"m": s / "pipeB-sw-muscriptor.mid"}, True)[f"m/{other}"],
               "bp": load_sources({"b": s / "pipeB-sw-basicpitch.mid"}, True)[f"b/{other}"]}
        cases.append(("slakh", [n for n in load_notes(s / "reference.json") if n["part"] == part], src))
    for song in _songs(d / "urmp-brass"):
        cases.append(("urmp", [n for n in load_notes(song / "reference.json") if n["part"].startswith("1-")],
                      {"mus": load_notes(song / "muscriptor-medium.mid"), "bp": load_notes(song / "basic-pitch.mid")}))
    for song in _songs(d / "choralebricks-brass4"):
        cases.append(("chorales", [n for n in load_notes(song / "reference.json") if n["part"] == "S"],
                      {"mus": load_notes(song / "muscriptor-medium.mid"), "bp": load_notes(song / "basic-pitch.mid")}))
    out = {}
    for thr, label in ((0.0, "union"), (0.5, "muscriptor_supported"), (0.7, "agreement")):
        fs: dict[str, list[float]] = {}
        for name, ref, src in cases:
            cand, _ = consensus(src, {"mus": 0.6, "bp": 0.4}, thr)
            fs.setdefault(name, []).append(score(ref, line(cand, 52, 88, top=True))["onset100_f1"])
        means = {k: float(np.mean(v)) for k, v in fs.items()}
        for k, v in means.items():
            out[f"{label}.{k}"] = v
        out[f"{label}.mean"] = float(np.mean(list(means.values())))
    return out


# ----------------------------------------------------------------- consensus

def _consensus(eval_set: str, sources: list[tuple[str, str, bool]], thresholds: list[float]):
    def fn(data: Path, mode: str) -> dict[str, float]:
        from .consensus import consensus, load_sources
        from .consensus_bench import precision_of
        from .score import load_notes, score

        _need(data, f"eval/{eval_set}")
        songs = _songs(data / "eval" / eval_set)
        refs, per_song = {}, {}
        for song in songs:
            refs[song] = load_notes(song / "reference.json")
            srcs = {}
            for label, name, split in sources:
                if not (song / name).exists():
                    raise SkipSuite(f"no cached {name} for {song.name}")
                srcs.update(load_sources({label: song / name}, split))
            per_song[song] = srcs
        counts = {s: {k: precision_of(n, refs[s]) for k, n in per_song[s].items()} for s in songs}
        out: dict[str, float] = {}
        for t in thresholds:
            rows = []
            for song in songs:
                prec = {}
                for k in per_song[song]:
                    m = sum(counts[o].get(k, (0, 0))[0] for o in songs if o != song)
                    n = sum(counts[o].get(k, (0, 0))[1] for o in songs if o != song)
                    prec[k] = m / n if n else 0.3
                notes, _ = consensus(per_song[song], prec, t)
                rows.append(score(refs[song], notes))
            for k in ("onset100_f1", "onset100_p", "onset100_r"):
                out[f"t{t:.1f}.{k}"] = _mean(rows, k)
        out["best.onset100_f1"] = max(v for k, v in out.items() if k.endswith(".onset100_f1"))
        return out

    return fn


# ---------------------------------------------------------------- solo vote

def _solo_vote(data: Path, mode: str) -> dict[str, float]:
    from collections import defaultdict

    from . import solo_vote_bench as B
    from .consensus import cluster
    from .lead_sheet import line
    from .score import score

    _need(data, "mega53-out-bench", "eval/choralebricks-brass4", "eval/slakh-trumpet")
    alone, vote2 = defaultdict(list), []
    combo = defaultdict(lambda: [0, 0])
    stems = data / "mega53-out-bench"
    for name, _, ref in B.cases():
        stem_dir = stems / _.name
        if not (stem_dir / "trumpet.flac").exists():
            raise SkipSuite(f"missing {stem_dir.name}/trumpet.flac")
        src = {}
        for key, tool in B.TOOLS.items():
            mid = stem_dir / f"trumpet-{key}.mid"
            if not mid.exists():
                if mode != "live":
                    raise SkipSuite(f"no cached {mid.name} for {stem_dir.name}")
                subprocess.run([str(ADAPTERS / tool / "run.sh"), str(stem_dir / "trumpet.flac"), str(mid)], check=True)
            from .score import load_notes

            src[key] = line(load_notes(mid), 52, 88, top=True)
        for k, notes in src.items():
            alone[k].append(score(ref, notes)["onset100_f1"])
        notes = [{"pitch": c.pitch, "onset": float(np.median(c.onsets)), "offset": float(np.median(c.offsets)),
                  "votes": len(c.sources), "combo": "+".join(sorted(c.sources))} for c in cluster(src)]
        ok = B.matched(ref, notes)
        for j, n in enumerate(notes):
            combo[n["combo"]][0] += j in ok
            combo[n["combo"]][1] += 1
        vote2.append(score(ref, line([n for n in notes if n["votes"] >= 2], 52, 88, top=True)))
    out = {f"{k}.onset100_f1": float(np.mean(v)) for k, v in alone.items()}
    for k in ("onset100_f1", "onset100_p", "onset100_r"):
        out[f"vote2.{k}"] = _mean(vote2, k)
    for c, (good, total) in combo.items():
        out[f"precision.{c}"] = good / total
    return out


# ---------------------------------------------------------------- arrangement

def _arrange(data: Path, mode: str) -> dict[str, float]:
    from .arrange_bench import composition_from_reference, evaluate

    _need(data, "eval/choralebricks-brass4", "eval/urmp-brass")
    out = {}
    for label, d in (("chorales", "choralebricks-brass4"), ("urmp", "urmp-brass")):
        rows = [evaluate(composition_from_reference(s, s.name))[0] for s in _songs(data / "eval" / d)]
        for k in ("melody_kept", "bass_kept", "harmony_fidelity", "impossible", "uncomfortable", "crossings"):
            out[f"{label}.{k}"] = _mean(rows, k)
    return out


def _mikkel_arrangement(data: Path, out: Path) -> Path:
    """Arrange the cached Mikkel layers (no heavy model runs) into out; returns the MusicXML path.

    The solo contour is light SwiftF0 work: taken from the layers dir when cached,
    otherwise computed with the SwiftF0 adapter.
    """
    import sys

    _need(data, "mikkel/repro/layers", "mikkel/repro/mix.beats", "golden/mikkel-arranged-band")
    layers = data / "mikkel/repro/layers"
    view = out / "layers"
    view.mkdir(parents=True)
    for f in layers.glob("*.mid"):
        (view / f.name).symlink_to(f.resolve())
    contour = layers / "solo-sw.contour.npz"
    if contour.exists():
        (view / contour.name).symlink_to(contour.resolve())
    else:
        script = ADAPTERS / "swift-f0" / "contour.sh"
        if not script.exists():
            raise SkipSuite(f"no cached solo contour and no {script}")
        subprocess.run([str(script), str(layers / "solo.wav"), str(view / contour.name)], check=True, capture_output=True)
    title = json.loads((data / "golden/mikkel-arranged-band/composition.json").read_text())["title"]
    subprocess.run([sys.executable, "-W", "ignore", "-m", "brasscribe_eval.arrange_layers_song",
                    "--layers", str(view), "--beats", str(data / "mikkel/repro/mix.beats"),
                    "--out", str(out / "score"), "--title", title, "--no-render"], check=True, capture_output=True)
    return out / "score" / "brass-band.musicxml"


def _golden_arrange(data: Path, mode: str) -> dict[str, float]:
    """Re-arrange the cached Mikkel layers and compare with the golden output (no heavy models run)."""
    from brasscribe_engine.compare import compare

    with tempfile.TemporaryDirectory() as tmp:
        xml = _mikkel_arrangement(data, Path(tmp))
        c = compare(xml.parent, data / "golden/mikkel-arranged-band")
    return {"composition_identical": float(c.composition_identical), "musicxml_identical": float(c.musicxml_identical),
            "parts_identical": float(c.parts_identical), "parts_total": float(len(c.parts)),
            "notes_identical": float(c.notes_identical), "notes_total": float(c.to_dict()["notes_total"]),
            "parts_identical_frac": c.parts_identical / max(1, len(c.parts)),
            "notes_identical_frac": c.notes_identical / max(1, c.to_dict()["notes_total"])}


def _readability(data: Path, mode: str) -> dict[str, float]:
    """qa/tools/musicxml_readability.py --check --baseline on a fresh Mikkel arrangement."""
    import sys

    tool = ROOT / "qa" / "tools" / "musicxml_readability.py"
    baseline = ROOT / "qa" / "reports" / "mikkel-golden-readability.json"
    if not tool.exists() or not baseline.exists():
        raise SkipSuite("qa readability tool or its baseline is missing")
    with tempfile.TemporaryDirectory() as tmp:
        xml = _mikkel_arrangement(data, Path(tmp))
        gate = subprocess.run([sys.executable, str(tool), str(xml), "--check", "--baseline", str(baseline), "--json"],
                              capture_output=True, text=True)
    if gate.returncode not in (0, 1):
        raise RuntimeError(gate.stderr[-1000:])
    report = json.loads(gate.stdout)
    agg = report["aggregate"]
    out = {"passed": float(gate.returncode == 0), "violations": float(len(report.get("violations", [])))}
    for k in ("short_lt16_pct", "sixteenth_pct", "tuplet_pct", "tie_stub_pct", "empty_bar_pct_playing_parts",
              "uncertain_pct"):
        if isinstance(agg.get(k), (int, float)):
            out[k] = float(agg[k])
    return out


def _durations(data: Path, mode: str) -> dict[str, float]:
    """duration_bench: written-duration accuracy per rule, reference offsets and SwiftF0-contour offsets."""
    from .duration_bench import RULES, evaluate

    _need(data, "eval/urmp-brass", "eval/choralebricks-brass4")
    out: dict[str, float] = {}
    for label, d in (("urmp", "urmp-brass"), ("chorales", "choralebricks-brass4")):
        variants = [("", None)]
        contours = data / "runs" / "contours" / d
        if contours.is_dir():
            variants.append((".contours", contours))
        for suffix, cdir in variants:
            rows = [evaluate(song, cdir) for song in _songs(data / "eval" / d)]
            tot = sum(r["n"] for r in rows)
            for k in RULES:
                out[f"{label}{suffix}.{k}"] = sum(r[k] * r["n"] for r in rows) / tot
            out[f"{label}{suffix}.staccato"] = float(sum(r["staccato"] for r in rows))
            if cdir is not None:
                out[f"{label}{suffix}.offset_within_100ms"] = sum(r["offset_within_100ms"] * r["n"] for r in rows) / tot
    return out


def _freetime(data: Path, mode: str) -> dict[str, float]:
    """freetime_bench: strict-passage accuracy with and without free-time regions, and how often they fire."""
    from .freetime_bench import evaluate

    _need(data, "eval/urmp-brass", "eval/choralebricks-brass4")
    rows = [evaluate(song) for d in ("urmp-brass", "choralebricks-brass4") for song in _songs(data / "eval" / d)
            if (song / "beat-this.beats").exists()]
    out: dict[str, float] = {}
    for v in ("grid", "free"):
        for k in ("position", "subdivision", "duration"):
            out[f"{v}.{k}"] = float(np.mean([r[v][k] for r in rows]))
    out["pieces_with_regions"] = float(sum(bool(r["regions"]) for r in rows))
    out["pieces"] = float(len(rows))
    return out


def _musescore(data: Path, mode: str) -> dict[str, float]:
    import contextlib
    import io

    from .musescore_roundtrip import check

    if not shutil.which("mscore"):
        raise SkipSuite("mscore (MuseScore CLI) not installed")
    with tempfile.TemporaryDirectory() as tmp:
        xml = _mikkel_arrangement(data, Path(tmp))
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            ok = check(xml, xml.parent / "composition.json")
    lines = [ln for ln in buf.getvalue().splitlines() if "sound=" in ln]
    match = sum(ln.rstrip().endswith("OK") for ln in lines)
    return {"all_match": float(ok), "pitched_parts": float(len(lines)), "pitched_parts_match": float(match)}


# -------------------------------------------------------------------- registry

_CHORALE_KEYS = ["onset_f1", "onoff_f1", "octave_err_rate", "onset100_f1"]
SUITES: dict[str, Suite] = {s.name: s for s in [
    Suite("chorales-transcription", "transcription per model on ChoraleBricks brass quartets (cached MIDI)",
          _transcription("choralebricks-brass4", {m: _CHORALE_KEYS for m in [
              "basic-pitch", "muscriptor-medium", "muscriptor-large", "muscriptor-medium-brass", "muscriptor-large-brass"]}),
          ("eval/choralebricks-brass4",)),
    Suite("urmp-transcription", "transcription per model on URMP brass (cached MIDI)",
          _transcription("urmp-brass", {m: ["onset_f1", "onset100_f1", "octave_err_rate"] for m in ["basic-pitch", "muscriptor-medium"]}),
          ("eval/urmp-brass",)),
    Suite("slakh-transcription", "pipelines A and B on Slakh trumpet-lead songs (cached MIDI)",
          _transcription("slakh-trumpet", {m: ["onset100_f1", "onset_f1"] for m in [
              "basic-pitch", "muscriptor-medium", "pipeB-sw-muscriptor", "pipeB-sw-basicpitch"]}),
          ("eval/slakh-trumpet",)),
    Suite("quant-chorales", "beat grid + quantizer vs notated positions, chorales", _quant("choralebricks-brass4"),
          ("eval/choralebricks-brass4",)),
    Suite("quant-urmp", "beat grid + quantizer vs notated positions, URMP", _quant("urmp-brass"), ("eval/urmp-brass",)),
    Suite("melody", "melody top line from MuScriptor/Basic Pitch consensus", _melody,
          ("eval/slakh-trumpet", "eval/urmp-brass", "eval/choralebricks-brass4")),
    Suite("consensus-chorales", "MuScriptor + Basic Pitch consensus on chorales (leave-one-song-out precision)",
          _consensus("choralebricks-brass4", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False)],
                     [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), ("eval/choralebricks-brass4",)),
    Suite("consensus-urmp", "MuScriptor + Basic Pitch consensus on URMP brass",
          _consensus("urmp-brass", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False)], [0.8]),
          ("eval/urmp-brass",)),
    Suite("consensus-slakh", "four-source consensus on Slakh (both models on mix and SW stems)",
          _consensus("slakh-trumpet", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False),
                                       ("musB", "pipeB-sw-muscriptor.mid", True), ("bpB", "pipeB-sw-basicpitch.mid", True)],
                     [0.7, 0.8]), ("eval/slakh-trumpet",)),
    Suite("solo-vote", "SwiftF0 / MuScriptor / Basic Pitch vote on Mega-53 solo stems (cached MIDI)", _solo_vote,
          ("mega53-out-bench", "eval/choralebricks-brass4", "eval/slakh-trumpet")),
    Suite("arrange", "minimal-band arranger on ground-truth scores (no audio)", _arrange,
          ("eval/choralebricks-brass4", "eval/urmp-brass")),
    Suite("mikkel-golden", "re-arrange cached Mikkel layers and compare with the golden output", _golden_arrange,
          ("mikkel/repro/layers", "golden/mikkel-arranged-band")),
    Suite("readability", "QA readability gate (qa/tools/musicxml_readability.py --check --baseline) on a fresh Mikkel arrangement",
          _readability, ("mikkel/repro/layers", "golden/mikkel-arranged-band")),
    Suite("durations", "written durations and staccato from performed lengths (duration_bench)", _durations,
          ("eval/urmp-brass", "eval/choralebricks-brass4")),
    Suite("freetime", "free-time detection on rubato/fermata material (freetime_bench)", _freetime,
          ("eval/urmp-brass", "eval/choralebricks-brass4")),
    Suite("musescore-roundtrip", "a fresh Mikkel arrangement re-exported by MuseScore keeps every part's pitches",
          _musescore, ("mikkel/repro/layers", "golden/mikkel-arranged-band"), tools=("mscore",)),
]}

GROUPS = {
    "cpu": [n for n, s in SUITES.items() if s.cpu],
    "all": list(SUITES),
}


def run_suite(name: str, mode: str = "cached", data: Path | None = None) -> dict:
    from .paths import DATA

    suite = SUITES[name]
    t0 = time.time()
    try:
        metrics = suite.fn(Path(data or DATA), mode)
        return {"suite": name, "status": "ran", "metrics": metrics, "seconds": round(time.time() - t0, 2)}
    except SkipSuite as e:
        return {"suite": name, "status": "skipped", "reason": str(e), "metrics": {}, "seconds": round(time.time() - t0, 2)}
    except Exception as e:  # noqa: BLE001 - a broken suite is a failure, not a crash of the whole run
        return {"suite": name, "status": "error", "reason": f"{type(e).__name__}: {e}", "metrics": {},
                "seconds": round(time.time() - t0, 2)}


def run_many(name: str, mode: str = "cached", data: Path | None = None) -> list[dict]:
    names = GROUPS.get(name) or [n for n in name.split(",")]
    unknown = [n for n in names if n not in SUITES]
    if unknown:
        raise SystemExit(f"unknown suite(s) {', '.join(unknown)}; choose from {', '.join([*SUITES, *GROUPS])}")
    return [run_suite(n, mode, data) for n in names]


def load_baselines(path: Path = BASELINES) -> dict:
    return json.loads(path.read_text())


def gate(results: list[dict], baselines: dict | None = None, allow_improved: bool = False,
         require_data: bool = False) -> dict:
    """Compare results with baselines; fills per-suite status and checks."""
    b = baselines or load_baselines()
    default_tol = b.get("tolerance", 0.01)
    suites_out, passed = [], True
    for r in results:
        base = b["suites"].get(r["suite"], {})
        checks = []
        if r["status"] == "ran":
            for metric, spec in base.get("metrics", {}).items():
                spec = spec if isinstance(spec, dict) else {"value": spec}
                tol = spec.get("tolerance", default_tol)
                higher = spec.get("higher_is_better", True)
                v = r["metrics"].get(metric)
                if v is None:
                    status = "missing"
                else:
                    d = v - spec["value"]
                    status = "pass" if abs(d) <= tol + 1e-9 else ("improved" if (d > 0) == higher else "regressed")
                checks.append({"metric": metric, "value": None if v is None else round(v, 4), "baseline": spec["value"],
                               "tolerance": tol, "status": status})
            bad = {"missing", "regressed"} | (set() if allow_improved else {"improved"})
            status = "fail" if any(c["status"] in bad for c in checks) else "pass"
        elif r["status"] == "skipped":
            status = "fail" if require_data else "skipped"
        else:
            status = "error"
        passed &= status in ("pass", "skipped")
        suites_out.append({**r, "status": status, "checks": checks,
                           "metrics": {k: round(float(v), 4) for k, v in r["metrics"].items()}})
    return {"passed": passed, "suites": suites_out}


def format_report(report: dict) -> str:
    lines = []
    for s in report["suites"]:
        head = f"{s['suite']:22s} {s['status'].upper():8s} {s['seconds']:6.1f}s"
        if s.get("reason"):
            head += f"  ({s['reason']})"
        lines.append(head)
        for c in s["checks"]:
            if c["status"] != "pass" or True:
                mark = {"pass": " ", "improved": "+", "regressed": "!", "missing": "?"}.get(c["status"], " ")
                val = "-" if c["value"] is None else f"{c['value']:.3f}"
                lines.append(f"   {mark} {c['metric']:38s} {val:>7s}  baseline {c['baseline']:.3f} ±{c['tolerance']}  {c['status']}")
    counts = {}
    for s in report["suites"]:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    verdict = "FAILED" if not report["passed"] else ("PASSED" if counts.get("pass") else "NOTHING GATED (no data)")
    lines.append(verdict + "  " +", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    return "\n".join(lines)
