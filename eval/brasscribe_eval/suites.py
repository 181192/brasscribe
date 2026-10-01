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
import os
import shutil
import subprocess
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

import numpy as np

from .gpulock import gpu_lock
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
    ci: bool = False  # gates in CI on the redistributable data built by ci_data (ChoraleBricks + our outputs)


HEAVY = {"muscriptor", "beat-this", "mega53", "separator"}


# The Mikkel golden output (data/golden), and the on-device reference clip's layered output.
MIKKEL_GOLDEN = "golden/mikkel-arranged-band"
ONDEVICE_REF = "runs/apple/entertainer-ref"

def _run_adapter(tool: str, src: Path, dst: Path) -> None:
    """Live mode: run an adapter; heavy models wait for the machine-wide GPU mutex."""
    cmd = [str(ADAPTERS / tool / "run.sh"), str(src), str(dst)]
    if tool not in HEAVY:
        subprocess.run(cmd, check=True)
        return
    with gpu_lock(poll=5):
        subprocess.run(cmd, check=True)


def _run_retuned(tool: str, src: Path, dst: Path) -> None:
    """Live mode: an adapter on src as the brass-band profile runs it, retuned to A = 440 when it is out of tune."""
    from brasscribe_engine import tuning

    params, _ = tuning.derive({"audio": src})
    if not params:
        return _run_adapter(tool, src, dst)
    with tempfile.TemporaryDirectory() as tmp:
        audio = Path(tmp) / "retuned.wav"
        q = tuning.shift_audio(src, audio, params["retune"]["shift_cents"])
        part = Path(tmp) / dst.name
        _run_adapter(tool, audio, part)
        tuning.rescale_midi(part, float(q))
        shutil.move(part, dst)


def _need(data: Path, *rels: str) -> None:
    missing = [r for r in rels if not (data / r).exists()]
    if missing:
        raise SkipSuite(f"missing data: {', '.join(missing)}")


SETS = {"chorales": "choralebricks-brass4", "urmp": "urmp-brass"}
SKIPPED = "__skipped__"  # metric key listing eval-set labels whose data was absent


def _present(data: Path, out: dict, labels: tuple[str, ...] = ("chorales", "urmp")) -> list[tuple[str, str]]:
    """(label, eval set) pairs whose data exists; absent ones are recorded as skipped parts of the suite."""
    have = [(lb, SETS[lb]) for lb in labels if (data / "eval" / SETS[lb]).is_dir()]
    if not have:
        raise SkipSuite(f"missing data: {', '.join('eval/' + SETS[lb] for lb in labels)}")
    out[SKIPPED] = [lb for lb in labels if lb not in dict(have)]
    return have


def _songs(d: Path) -> list[Path]:
    return sorted(p for p in d.iterdir() if (p / "reference.json").exists())


def _mean(rows: list[dict], key: str) -> float:
    return float(np.mean([r[key] for r in rows if key in r]))


# ------------------------------------------------------------- transcription

def _transcription(eval_set: str, models: dict[str, list[str]]) -> Callable[[Path, str], dict[str, float]]:
    """Mean metrics per model over an eval set, from <song>/<model>.mid."""
    adapters = {"basic-pitch": "basic-pitch", "muscriptor-medium": "muscriptor"}
    retuned = {"basic-pitch-retuned": "basic-pitch"}

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
                    _run_adapter(adapters[model], song / "mix.wav", mid)
                if not mid.exists() and mode == "live" and model in retuned:
                    _run_retuned(retuned[model], song / "mix.wav", mid)
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
    for name, _, ref in B.cases(data):
        stem_dir = stems / _.name
        if not (stem_dir / "trumpet.flac").exists():
            raise SkipSuite(f"missing {stem_dir.name}/trumpet.flac")
        src = {}
        for key, tool in B.TOOLS.items():
            mid = stem_dir / f"trumpet-{key}.mid"
            if not mid.exists():
                if mode != "live":
                    raise SkipSuite(f"no cached {mid.name} for {stem_dir.name}")
                _run_adapter(tool, stem_dir / "trumpet.flac", mid)
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
    from brasscribe_music.instruments import QUARTET

    from .arrange_bench import QUARTET_KEYS, composition_from_reference, evaluate, reference_row

    out: dict = {}
    for label, d in _present(data, out):
        comps = [composition_from_reference(s, s.name) for s in _songs(data / "eval" / d)]
        rows = [evaluate(c)[0] for c in comps]
        for k in ("melody_kept", "bass_kept", "harmony_fidelity", "impossible", "uncomfortable", "crossings"):
            out[f"{label}.{k}"] = _mean(rows, k)
        if label != "chorales":
            continue
        # The quartet on the chorales, whose S A T B are a brass quartet's own parts, in every difficulty.
        for diff in ("faithful", "standard", "easier"):
            prefix = "quartet" if diff == "faithful" else f"quartet-{diff}"
            q = [evaluate(c, QUARTET, diff)[0] for c in comps]
            for k in QUARTET_KEYS:
                out[f"{prefix}.{k}"] = _mean(q, k)
        # The chorales' own voices under the same four-part metrics (how far "no parallels" is from Bach).
        ref = [reference_row(c) for c in comps]
        for k in ("parallels_per_100", "spacing_faults", "crossings"):
            out[f"quartet-reference.{k}"] = _mean(ref, k)
    return out


def _quartet_audio(data: Path, mode: str) -> dict[str, float]:
    """Record a quartet, get quartet parts: cached MuScriptor and Basic Pitch transcriptions of the
    ChoraleBricks recordings through arrange_song for the quartet, scored against the chorale."""
    from brasscribe_music.arranger import arrange
    from brasscribe_music.instruments import QUARTET

    from .arrange_bench import audio_quartet_row
    from .arrange_song import song_composition

    d = data / "eval" / SETS["chorales"]
    _need(data, f"eval/{SETS['chorales']}")
    # mus-retuned: what the brass-band profile arranges from, Basic Pitch on the recording retuned to A = 440.
    sources = {"mus": ("muscriptor-medium.mid", "basic-pitch.mid"), "bp": ("basic-pitch.mid", None),
               "mus-retuned": ("muscriptor-medium.mid", "basic-pitch-retuned.mid")}
    out: dict = {}
    for label, (main, support) in sources.items():
        rows = []
        for s in _songs(d):
            mids = [s / main] + ([s / support] if support else [])
            if not all(m.exists() for m in mids) or not (s / "beat-this.beats").exists():
                raise SkipSuite(f"no cached {main} / beat-this.beats for {s.name}")
            comp = song_composition(s / "beat-this.beats", s / main, s / support if support else None, s / main, mids, s.name)
            rows.append(audio_quartet_row(comp, arrange(comp, QUARTET), s / "reference.json"))
        for k in rows[0]:
            out[f"{label}.{k}"] = _mean(rows, k)
    return out


def _mikkel_arrangement(data: Path, out: Path, difficulty: str = "faithful") -> Path:
    """Arrange the cached Mikkel layers (no heavy model runs) into out; returns the MusicXML path.

    The solo contour is light SwiftF0 work: taken from the layers dir when cached,
    otherwise computed with the SwiftF0 adapter.
    """
    import sys

    _need(data, "mikkel/repro/layers", "mikkel/repro/mix.beats", MIKKEL_GOLDEN)
    layers = data / "mikkel/repro/layers"
    view = out / "layers"
    view.mkdir(parents=True)
    # MIDI of every layer plus the layer audio (energy gate, separation check, dynamics, rehearsal marks).
    for f in [*layers.glob("*.mid"), *(layers / f"{n}.wav" for n in ("solo", "bass", "drums", "orchestra"))]:
        if f.exists():
            (view / f.name).symlink_to(f.resolve())
    contour = layers / "solo-sw.contour.npz"
    if contour.exists():
        (view / contour.name).symlink_to(contour.resolve())
    else:
        script = ADAPTERS / "swift-f0" / "contour.sh"
        if not script.exists():
            raise SkipSuite(f"no cached solo contour and no {script}")
        subprocess.run([str(script), str(layers / "solo.wav"), str(view / contour.name)], check=True, capture_output=True)
    title = json.loads((data / f"{MIKKEL_GOLDEN}/composition.json").read_text())["title"]
    subprocess.run([sys.executable, "-W", "ignore", "-m", "brasscribe_eval.arrange_layers_song",
                    "--layers", str(view), "--beats", str(data / "mikkel/repro/mix.beats"),
                    "--out", str(out / "score"), "--title", title, "--no-render", "--difficulty", difficulty],
                   check=True, capture_output=True)
    return out / "score" / "brass-band.musicxml"


def _golden_arrange(data: Path, mode: str) -> dict[str, float]:
    """Re-arrange the cached Mikkel layers and compare with the golden output (no heavy models run)."""
    from brasscribe_engine.compare import compare

    with tempfile.TemporaryDirectory() as tmp:
        xml = _mikkel_arrangement(data, Path(tmp))
        c = compare(xml.parent, data / MIKKEL_GOLDEN)
    return {"composition_identical": float(c.composition_identical), "musicxml_identical": float(c.musicxml_identical),
            "parts_identical": float(c.parts_identical), "parts_total": float(len(c.parts)),
            "notes_identical": float(c.notes_identical), "notes_total": float(c.to_dict()["notes_total"]),
            "parts_identical_frac": c.parts_identical / max(1, len(c.parts)),
            "notes_identical_frac": c.notes_identical / max(1, c.to_dict()["notes_total"])}


# Faithful writes the solo's fast notes as played (docs/plan/fast-notes.md §7): Mikkel's Solo Cornet is mostly
# 16ths there, so that one metric of that one part gets a looser limit. Standard and easier keep every threshold.
FAITHFUL_LIMITS = {"Solo Cornet:sixteenth_pct": 65.0}


def _readability(data: Path, mode: str) -> dict[str, float]:
    """qa/tools/musicxml_readability.py --check --baseline on a fresh Mikkel arrangement."""
    import sys

    tool = ROOT / "qa" / "tools" / "musicxml_readability.py"
    baseline = ROOT / "qa" / "reports" / "mikkel-golden-readability.json"
    if not tool.exists() or not baseline.exists():
        raise SkipSuite("qa readability tool or its baseline is missing")
    out: dict[str, float] = {}
    passed = True
    for mode in ("faithful", "standard", "easier"):
        with tempfile.TemporaryDirectory() as tmp:
            xml = _mikkel_arrangement(data, Path(tmp), mode)
            limits = [a for k, v in FAITHFUL_LIMITS.items() for a in ("--limit", f"{k}={v}")] if mode == "faithful" else []
            gate = subprocess.run([sys.executable, str(tool), str(xml), "--check", "--baseline", str(baseline), "--json",
                                   *limits], capture_output=True, text=True)
        if gate.returncode not in (0, 1):
            raise RuntimeError(gate.stderr[-1000:])
        passed &= gate.returncode == 0
        out[f"{mode}.passed"] = float(gate.returncode == 0)
        if mode == "faithful":
            report = json.loads(gate.stdout)
            solo = next((p for p in report["parts"] if p["part"] == "Solo Cornet"), {})
            for k in ("sixteenth_pct", "tuplet_pct", "tie_stub_pct", "accidental_pct"):
                if isinstance(solo.get(k), (int, float)):
                    out[f"solo_cornet.{k}"] = float(solo[k])
    agg = report["aggregate"]
    out.update({"passed": float(passed), "violations": float(len(report.get("violations", [])))})
    for k in ("short_lt16_pct", "sixteenth_pct", "tuplet_pct", "tie_stub_pct", "empty_bar_pct_playing_parts",
              "uncertain_pct"):
        if isinstance(agg.get(k), (int, float)):
            out[k] = float(agg[k])
    return out


def _solo_instruments(data: Path, mode: str) -> dict[str, float]:
    """solo_instruments_bench on the frozen ChoraleBricks solo fixtures (in the repository; no models run)."""
    from .solo_instruments_bench import FIXTURES, metrics

    if not FIXTURES.is_dir():
        raise SkipSuite(f"missing fixtures: {FIXTURES}")
    m = metrics(seats=True)
    # The seat's gates (docs/plan/my-instrument.md §6.3): recall on low brass, and a solo take written as played.
    recall = {"baritone": 0.93, "trombone": 0.93, "tuba": 0.85}
    m["seat_gates"] = float(all(m[f"{k}.seat_recall"] >= v for k, v in recall.items())
                            and all(v <= 0.01 for k, v in m.items() if k.endswith(".seat_moved")))
    return m


def _fast_notes(data: Path, mode: str) -> dict[str, float]:
    """fast_notes_bench on the frozen fast-notes fixtures (real trumpet samples; in the repository; no models run)."""
    from .fast_notes import FIXTURES
    from .fast_notes_bench import suite_metrics

    if not FIXTURES.is_dir():
        raise SkipSuite(f"missing fixtures: {FIXTURES}")
    return suite_metrics(FIXTURES)


def _seat_voices(data: Path, mode: str) -> dict[str, float]:
    """seat_voices_bench: each seat's voice picked out of the brass4 mixes by range (cached MIDI)."""
    from .seat_voices_bench import evaluate

    _need(data, "eval/choralebricks-brass4")
    return evaluate(data / "eval" / "choralebricks-brass4")


def _durations(data: Path, mode: str) -> dict[str, float]:
    """duration_bench: written-duration accuracy per rule, reference offsets and SwiftF0-contour offsets."""
    from .duration_bench import RULES, evaluate

    out: dict = {}
    for label, d in _present(data, out):
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
    """freetime_bench: strict-passage accuracy with and without free-time regions, and how often they fire.

    Reported per eval set, and over all pieces when every set is present."""
    from .freetime_bench import evaluate

    out: dict = {}
    every = []
    for label, d in _present(data, out):
        rows = [evaluate(song) for song in _songs(data / "eval" / d) if (song / "beat-this.beats").exists()]
        every += rows
        for prefix, rs in ((label, rows),):
            for v in ("grid", "free"):
                for k in ("position", "subdivision", "duration"):
                    out[f"{prefix}.{v}.{k}"] = float(np.mean([r[v][k] for r in rs]))
            out[f"{prefix}.pieces_with_regions"] = float(sum(bool(r["regions"]) for r in rs))
            out[f"{prefix}.pieces"] = float(len(rs))
    if not out[SKIPPED]:
        for v in ("grid", "free"):
            for k in ("position", "subdivision", "duration"):
                out[f"{v}.{k}"] = float(np.mean([r[v][k] for r in every]))
        out["pieces_with_regions"] = float(sum(bool(r["regions"]) for r in every))
        out["pieces"] = float(len(every))
    else:
        out[SKIPPED] = out[SKIPPED] + ["grid", "free", "pieces_with_regions", "pieces"]
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


def _solo_ondevice(data: Path, mode: str) -> dict[str, float]:
    """The engine's solo profile against the on-device reference (apps/apple/scripts/make-ondevice-reference.sh).

    The reference ran SwiftF0, Basic Pitch (standing in for MuScriptor), the SwiftF0 contour and
    Beat This! small0 on a 30 s URMP trumpet clip, then the layered arranger with only a solo layer
    and the minimal band. Cached mode seeds the engine's cache with those model outputs, so only the
    arrangement runs; live mode runs the light models (SwiftF0, Basic Pitch, contour) itself and
    seeds only the beats. Gates on note-for-note identity of the score and every part."""
    from brasscribe_engine import runner
    from brasscribe_engine.compare import compare
    from brasscribe_engine.config import Settings

    ref = data / ONDEVICE_REF
    clip = data / "runs" / "apple" / "entertainer-tpt1-30s.wav"
    _need(data, f"{ONDEVICE_REF}/layered", "runs/apple/entertainer-tpt1-30s.wav")
    with tempfile.TemporaryDirectory() as tmp:
        seed = Path(tmp) / "seed"
        (seed / "layers").mkdir(parents=True)
        (seed / "beats-small0").mkdir()  # where the solo profile looks for small0 beats to reuse
        shutil.copy(ref / "beats-small0.beats", seed / "beats-small0" / "mix.beats")
        if mode != "live":
            for f in ("solo-sw.mid", "solo-bp.mid", "solo-sw.contour.npz"):
                shutil.copy(ref / "layers" / f, seed / "layers" / f)
        settings = Settings(data_dir=Path(tmp) / "data", adapters_dir=ADAPTERS)
        m = runner.run(settings, clip, "solo", title="Reference", params={"audio": False, "muscriptor": False},
                       reuse=seed, allow_heavy=False)
        if m["status"] != "succeeded":
            raise RuntimeError(m.get("error") or m["status"])
        c = compare(settings.runs_dir / m["run_id"] / "outputs", ref / "layered")
        d = c.to_dict()
    extra = list(c.extra_files.values())
    return {"composition_identical": float(c.composition_identical), "musicxml_identical": float(c.musicxml_identical),
            "parts_identical_frac": c.parts_identical / max(1, len(c.parts)),
            "notes_identical_frac": c.notes_identical / max(1, d["notes_total"]),
            "part_files_identical_frac": sum(extra) / max(1, len(extra)), "notes_total": float(d["notes_total"])}


# ------------------------------------------------------------------- bass tab

def _bass_tab(data: Path, mode: str) -> dict[str, float]:
    """The engine's bass-tab profile on Slakh bass lines (bass_tab_bench), a full song and the bass alone.

    Cached mode scores the model outputs next to the eval data and runs only the profile's own stages
    and the Rust core. Live mode builds the set from the Slakh tracks and runs the models it lacks."""
    from brasscribe_engine import bass_tab

    from . import bass_tab_bench as B

    source = data / B.SOURCE
    if not B.entries(data):
        if mode != "live" or not source.is_dir():
            raise SkipSuite(f"missing data: eval/{B.SET} (built from {B.SOURCE} in live mode)")
        B.build(source, data)
    try:
        bass_tab.core_cli()
    except bass_tab.CoreCliMissing as e:
        raise SkipSuite(str(e)) from e
    # The low register, synthesized: made in live mode where FluidSynth and the SoundFont are.
    if not B.entries(data, B.SYNTH_SET) and mode == "live" and shutil.which("fluidsynth") and (data / B.SOUNDFONT).exists():
        B.synthesize(data)
    low = B.entries(data, B.SYNTH_SET)
    for entry in B.entries(data) + low:
        missing = [f for m in B.MODES for f in B.FILES[m].values() if not (entry / f).exists()]
        if missing and mode != "live":
            raise SkipSuite(f"no cached {missing[0]} for {entry.name}")
        if missing:
            try:
                B.prepare(entry, *B.audio_of(entry, source if source.is_dir() else None))
            except FileNotFoundError as e:
                raise SkipSuite(str(e)) from e
    out: dict[str, float] = {}
    for m in B.MODES:
        metrics, _ = B.evaluate(data, m)
        out.update({f"{m}.{k}": v for k, v in metrics.items()})
    # Each group of the low-register set apart: its numbers are not Slakh's.
    labels = {g: g.replace("-", "_") for g in B.GROUPS}
    out[SKIPPED] = [] if low else list(labels.values())
    for group, label in labels.items() if low else ():
        for m in B.MODES:
            metrics, _ = B.evaluate(data, m, eval_set=B.SYNTH_SET, group=group)
            out.update({f"{label}.{m}.{k}": v for k, v in metrics.items()})
    return out


# -------------------------------------------------------------------- registry

_CHORALE_KEYS = ["onset_f1", "onoff_f1", "octave_err_rate", "onset100_f1"]
SUITES: dict[str, Suite] = {s.name: s for s in [
    Suite("chorales-transcription", "transcription per model on ChoraleBricks brass quartets (cached MIDI)",
          _transcription("choralebricks-brass4", {m: _CHORALE_KEYS for m in [
              "basic-pitch", "basic-pitch-retuned", "muscriptor-medium", "muscriptor-large", "muscriptor-medium-brass",
              "muscriptor-large-brass"]}),
          ("eval/choralebricks-brass4",), ci=True),
    Suite("urmp-transcription", "transcription per model on URMP brass (cached MIDI)",
          _transcription("urmp-brass", {m: ["onset_f1", "onset100_f1", "octave_err_rate"] for m in ["basic-pitch", "muscriptor-medium"]}),
          ("eval/urmp-brass",)),
    Suite("slakh-transcription", "pipelines A and B on Slakh trumpet-lead songs (cached MIDI)",
          _transcription("slakh-trumpet", {m: ["onset100_f1", "onset_f1"] for m in [
              "basic-pitch", "muscriptor-medium", "pipeB-sw-muscriptor", "pipeB-sw-basicpitch"]}),
          ("eval/slakh-trumpet",)),
    Suite("quant-chorales", "beat grid + quantizer vs notated positions, chorales", _quant("choralebricks-brass4"),
          ("eval/choralebricks-brass4",), ci=True),
    Suite("quant-urmp", "beat grid + quantizer vs notated positions, URMP", _quant("urmp-brass"), ("eval/urmp-brass",)),
    Suite("melody", "melody top line from MuScriptor/Basic Pitch consensus", _melody,
          ("eval/slakh-trumpet", "eval/urmp-brass", "eval/choralebricks-brass4")),
    Suite("consensus-chorales", "MuScriptor + Basic Pitch consensus on chorales (leave-one-song-out precision)",
          _consensus("choralebricks-brass4", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False)],
                     [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), ("eval/choralebricks-brass4",), ci=True),
    Suite("consensus-chorales-retuned", "the same, with Basic Pitch on the recording retuned to A = 440",
          _consensus("choralebricks-brass4", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch-retuned.mid", False)],
                     [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]), ("eval/choralebricks-brass4",), ci=True),
    Suite("consensus-urmp", "MuScriptor + Basic Pitch consensus on URMP brass",
          _consensus("urmp-brass", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False)], [0.8]),
          ("eval/urmp-brass",)),
    Suite("consensus-slakh", "four-source consensus on Slakh (both models on mix and SW stems)",
          _consensus("slakh-trumpet", [("mus", "muscriptor-medium.mid", False), ("bp", "basic-pitch.mid", False),
                                       ("musB", "pipeB-sw-muscriptor.mid", True), ("bpB", "pipeB-sw-basicpitch.mid", True)],
                     [0.7, 0.8]), ("eval/slakh-trumpet",)),
    Suite("solo-vote", "SwiftF0 / MuScriptor / Basic Pitch vote on Mega-53 solo stems (cached MIDI)", _solo_vote,
          ("mega53-out-bench", "eval/choralebricks-brass4", "eval/slakh-trumpet")),
    Suite("arrange", "minimal-band and quartet arrangers on ground-truth scores (no audio)", _arrange,
          ("eval/choralebricks-brass4", "eval/urmp-brass"), ci=True),
    Suite("quartet-audio", "quartet from cached transcriptions of the ChoraleBricks recordings, vs the chorale",
          _quartet_audio, ("eval/choralebricks-brass4",), ci=True),
    Suite("mikkel-golden", "re-arrange cached Mikkel layers and compare with the golden output", _golden_arrange,
          ("mikkel/repro/layers", MIKKEL_GOLDEN)),
    Suite("readability", "QA readability gate (qa/tools/musicxml_readability.py --check --baseline) on a fresh Mikkel arrangement",
          _readability, ("mikkel/repro/layers", MIKKEL_GOLDEN)),
    Suite("solo-instruments", "the solo path per brass instrument on frozen ChoraleBricks stems (SwiftF0/Basic Pitch MIDI)",
          _solo_instruments, (), ci=True),
    Suite("fast-notes", "fast runs, repeated notes and two-note alternations through the solo path, stage by stage "
          "(frozen SwiftF0/Basic Pitch/Beat This! outputs on real trumpet samples)", _fast_notes, (), ci=True),
    Suite("seat-voices", "each seat's voice picked out of the brass4 mixes by its range (MuScriptor, Basic Pitch, consensus)",
          _seat_voices, ("eval/choralebricks-brass4",), ci=True),
    Suite("durations", "written durations and staccato from performed lengths (duration_bench)", _durations,
          ("eval/urmp-brass", "eval/choralebricks-brass4"), ci=True),
    Suite("freetime", "free-time detection on rubato/fermata material (freetime_bench)", _freetime,
          ("eval/urmp-brass", "eval/choralebricks-brass4"), ci=True),
    Suite("solo-ondevice", "engine solo profile vs the on-device reference (URMP Entertainer trumpet, 30 s), note for note",
          _solo_ondevice, (ONDEVICE_REF, "runs/apple/entertainer-tpt1-30s.wav")),
    Suite("bass-tab", "the bass-tab profile on Slakh bass lines, from a full song and from the bass alone: notes, octave, "
          "range, playability, tempo and meter, hand travel (cached model outputs)", _bass_tab, ("eval/slakh-bass",)),
    Suite("musescore-roundtrip", "a fresh Mikkel arrangement re-exported by MuseScore keeps every part's pitches",
          _musescore, ("mikkel/repro/layers", MIKKEL_GOLDEN), tools=("mscore",)),
]}

GROUPS = {
    "cpu": [n for n, s in SUITES.items() if s.cpu],
    "ci": [n for n, s in SUITES.items() if s.ci],
    "all": list(SUITES),
}


def run_suite(name: str, mode: str = "cached", data: Path | None = None) -> dict:
    from .paths import DATA

    suite = SUITES[name]
    t0 = time.time()
    try:
        metrics = suite.fn(Path(data or DATA), mode)
        skipped = metrics.pop(SKIPPED, [])
        return {"suite": name, "status": "ran", "metrics": metrics, "skipped_parts": skipped,
                "seconds": round(time.time() - t0, 2)}
    except SkipSuite as e:
        return {"suite": name, "status": "skipped", "reason": str(e), "metrics": {}, "seconds": round(time.time() - t0, 2)}
    except (Exception, SystemExit) as e:  # noqa: BLE001 - a broken suite is a failure, not a crash of the whole run
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
                if v is not None and not np.isfinite(v):
                    v = None  # NaN or inf: nothing was measured
                if v is None and (metric.split(".")[0] in r.get("skipped_parts", []) or metric in r.get("skipped_parts", [])):
                    status = "skipped"
                elif v is None:
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
        if s.get("skipped_parts"):
            head += f"  (no data for: {', '.join(s['skipped_parts'])})"
        lines.append(head)
        for c in s["checks"]:
            if c["status"] != "pass" or True:
                if c["status"] == "skipped":
                    continue
                mark = {"pass": " ", "improved": "+", "regressed": "!", "missing": "?"}.get(c["status"], " ")
                val = "-" if c["value"] is None else f"{c['value']:.3f}"
                lines.append(f"   {mark} {c['metric']:38s} {val:>7s}  baseline {c['baseline']:.3f} ±{c['tolerance']}  {c['status']}")
    counts = {}
    for s in report["suites"]:
        counts[s["status"]] = counts.get(s["status"], 0) + 1
    verdict = "FAILED" if not report["passed"] else ("PASSED" if counts.get("pass") else "NOTHING GATED (no data)")
    lines.append(verdict + "  " +", ".join(f"{v} {k}" for k, v in sorted(counts.items())))
    return "\n".join(lines)
