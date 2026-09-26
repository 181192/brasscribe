"""Shared parity metrics, clip lists, benchmarking and report writing for model conversions.

Every conversion compares a converted model's output against the reference framework's
output on the same audio. Note parity uses the same mir_eval call as the engine's scorer
(onset within 50 ms, pitch within 50 cents, offsets ignored), with the reference output
as ground truth and the converted output as the estimate.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import resource
import statistics
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
MAIN = Path("/Users/k/private/brasscribe")
DATA = MAIN / "data"
MODELS = MAIN / "models"
CONVERTED = MODELS / "converted"
REPORTS = REPO / "convert" / "reports"
ADAPTERS = MAIN / "ml" / "adapters"
ONSET_TOL = 0.05
THRESHOLD = 0.98


# ---------------------------------------------------------------- clips

@dataclass
class Clip:
    name: str
    path: Path
    kind: str  # "part" (one monophonic instrument) or "mix"
    start: float = 0.0
    duration: float | None = None


def eval_mixes() -> list[Clip]:
    out = []
    for suite in ("choralebricks-brass4", "urmp-brass"):
        for d in sorted((DATA / "eval" / suite).iterdir()):
            if (d / "mix.wav").exists():
                out.append(Clip(f"{suite}/{d.name}", d / "mix.wav", "mix"))
    return out


def eval_parts() -> list[Clip]:
    """Isolated monophonic brass recordings behind the eval mixes."""
    out = []
    urmp = DATA / "urmp" / "Dataset"
    for d in sorted((DATA / "eval" / "urmp-brass").iterdir()):
        if not d.is_dir():
            continue
        for wav in sorted((urmp / d.name).glob("AuSep_*.wav")):
            out.append(Clip(f"urmp/{wav.stem}", wav, "part"))
    cb = DATA / "choralebricks" / "01_AudioAndAnnotations"
    import csv
    with open(cb / "metadata_tracks.csv") as f:
        rows = list(csv.DictReader(f, delimiter=";"))
    quartet = {"S": "Trumpet", "A": "Flugelhorn", "T": "Baritone", "B": "Tuba"}
    for r in rows:
        if quartet.get(r["part"]) == r["instrument"]:
            p = cb / r["song_id"] / "tracks_normalized" / r["path_audio"]
            if p.exists():
                out.append(Clip(f"choralebricks/{r['song_id']}/{r['part']}-{r['instrument']}", p, "part"))
    return sorted(out, key=lambda c: c.name)


def separator_clips() -> list[Clip]:
    """Short excerpts for the (slow) separators: three eval mixes and a Mikkel excerpt."""
    mixes = {c.name: c for c in eval_mixes()}
    picks = ["choralebricks-brass4/Bach_IchStehAnDeinerKrippe", "urmp-brass/05_Entertainer_tpt_tpt",
             "urmp-brass/43_Chorale_tpt_tpt_hn_tbn_tba"]
    out = [Clip(n, mixes[n].path, "mix", 0.0, 30.0) for n in picks]
    out.append(Clip("mikkel/excerpt-60s", DATA / "mikkel" / "mikkel.wav", "mix", 60.0, 30.0))
    return out


# ---------------------------------------------------------------- note parity

Notes = list[tuple[float, float, float]]  # (onset s, offset s, midi pitch)


def midi_notes(path: Path) -> Notes:
    import pretty_midi
    pm = pretty_midi.PrettyMIDI(str(path))
    return sorted((n.start, n.end, float(n.pitch)) for i in pm.instruments if not i.is_drum for n in i.notes)


def _arrays(notes: Notes):
    import mir_eval
    if not notes:
        return np.zeros((0, 2)), np.zeros(0)
    iv = np.array([[a, max(b, a + 0.01)] for a, b, _ in notes])
    return iv, mir_eval.util.midi_to_hz(np.array([p for _, _, p in notes]))


def note_match(ref: Notes, est: Notes) -> dict:
    import mir_eval
    ri, rp = _arrays(ref)
    ei, ep = _arrays(est)
    matched = 0
    if len(ref) and len(est):
        matched = len(mir_eval.transcription.match_notes(ri, rp, ei, ep, onset_tolerance=ONSET_TOL, offset_ratio=None))
    return _prf(len(ref), len(est), matched)


def event_match(ref: np.ndarray, est: np.ndarray, window: float = ONSET_TOL) -> dict:
    """One-to-one event matching within a window (beats, downbeats)."""
    import mir_eval
    matched = len(mir_eval.util.match_events(np.asarray(ref), np.asarray(est), window)) if len(ref) and len(est) else 0
    return _prf(len(ref), len(est), matched)


def _prf(n_ref: int, n_est: int, matched: int) -> dict:
    if n_ref == 0 and n_est == 0:
        return {"n_ref": 0, "n_est": 0, "matched": 0, "p": 1.0, "r": 1.0, "f1": 1.0}
    p = matched / n_est if n_est else 0.0
    r = matched / n_ref if n_ref else 0.0
    f = 2 * p * r / (p + r) if p + r else 0.0
    return {"n_ref": n_ref, "n_est": n_est, "matched": matched, "p": p, "r": r, "f1": f}


def pool(per_clip: dict[str, dict]) -> dict:
    """Pooled P/R/F1 over clips plus the worst clip."""
    n_ref = sum(v["n_ref"] for v in per_clip.values())
    n_est = sum(v["n_est"] for v in per_clip.values())
    matched = sum(v["matched"] for v in per_clip.values())
    out = _prf(n_ref, n_est, matched)
    if per_clip:
        worst = min(per_clip, key=lambda k: per_clip[k]["f1"])
        out.update(min_f1=per_clip[worst]["f1"], min_clip=worst, n_clips=len(per_clip))
    return out


def sdr(ref: np.ndarray, est: np.ndarray) -> float:
    """Plain SDR in dB of an estimate against a reference signal."""
    n = min(len(ref), len(est))
    ref, est = ref[:n].astype(np.float64), est[:n].astype(np.float64)
    err = np.sum((ref - est) ** 2)
    return float("inf") if err == 0 else float(10 * np.log10(np.sum(ref ** 2) / max(err, 1e-20) + 1e-20))


# ---------------------------------------------------------------- audio

def load_audio(clip: Clip, sr: int | None = None, mono: bool = False) -> tuple[np.ndarray, int]:
    """Audio as float32 (samples, channels) or (samples,) when mono, optionally resampled."""
    import soundfile as sf
    info = sf.info(str(clip.path))
    start = int(clip.start * info.samplerate)
    stop = None if clip.duration is None else start + int(clip.duration * info.samplerate)
    y, rate = sf.read(str(clip.path), start=start, stop=stop, dtype="float32", always_2d=True)
    if mono:
        y = y.mean(axis=1)
    if sr is not None and sr != rate:
        import soxr
        y = soxr.resample(y, rate, sr).astype(np.float32)
        rate = sr
    return y, rate


def load_stereo(clip: Clip, sr: int) -> np.ndarray:
    """(2, samples) float32 at sr; mono files are duplicated, as the separators' own CLIs do."""
    y, _ = load_audio(clip, sr=sr)
    if y.shape[1] == 1:
        y = np.repeat(y, 2, axis=1)
    return np.ascontiguousarray(y[:, :2].T)


# ---------------------------------------------------------------- benchmarking

def peak_rss_bytes() -> int:
    r = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return int(r if sys.platform == "darwin" else r * 1024)  # bytes on macOS, KiB on Linux


def time_runs(fn, n: int = 5, warmup: int = 1) -> dict:
    for _ in range(warmup):
        fn()
    times = []
    for _ in range(n):
        t = time.perf_counter()
        fn()
        times.append(time.perf_counter() - t)
    return {"median_s": statistics.median(times), "min_s": min(times), "runs": n}


def run_isolated(cmd: list[str], env: dict | None = None, timeout: float = 3600) -> dict:
    """Run a benchmark in a fresh process; it must print one JSON object as its last stdout line.

    ONNX Runtime's CoreML partition summary is parsed from stderr when present.
    """
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, **(env or {})}, timeout=timeout)
    lines = [l for l in proc.stdout.strip().splitlines() if l.startswith("{")]
    if proc.returncode != 0 or not lines:
        return {"error": (proc.stderr or proc.stdout)[-2000:], "returncode": proc.returncode}
    out = json.loads(lines[-1])
    m = re.findall(r"number of partitions supported by CoreML: (\d+) number of nodes in the graph: (\d+) "
                   r"number of nodes supported by CoreML: (\d+)", proc.stderr)
    if m:
        parts, total, supported = map(int, m[-1])
        out["coreml_ep"] = {"partitions": parts, "nodes_total": total, "nodes_on_coreml": supported}
    return out


def ort_session(path: Path, provider: str, compute_units: str = "ALL", verbose: bool = False, static_shapes: bool = True,
                low_memory: bool = False):
    """ONNX Runtime session on CPU or the CoreML EP (ML Program format).

    low_memory turns off the CPU arena and memory-pattern planning, which otherwise keep
    peak buffers for every intermediate of very large graphs.
    """
    import onnxruntime as ort
    so = ort.SessionOptions()
    if low_memory:
        so.enable_cpu_mem_arena = False
        so.enable_mem_pattern = False
    if verbose:
        so.log_severity_level = 1
    if provider == "coreml":
        opts = {"ModelFormat": "MLProgram", "MLComputeUnits": compute_units,
                "RequireStaticInputShapes": "1" if static_shapes else "0"}
        providers = [("CoreMLExecutionProvider", opts), "CPUExecutionProvider"]
    else:
        providers = ["CPUExecutionProvider"]
    return ort.InferenceSession(str(path), so, providers=providers)


def coreml_compute_plan(mlpackage: Path, compute_units: str) -> dict | None:
    """Per-op preferred device counts from Core ML's compute plan (macOS 14.4+)."""
    try:
        import coremltools as ct
        from coremltools.models.compute_plan import MLComputePlan
        compiled = ct.models.utils.compile_model(str(mlpackage))
        plan = MLComputePlan.load_from_path(path=compiled, compute_units=getattr(ct.ComputeUnit, compute_units))
        counts: dict[str, int] = {}
        program = plan.model_structure.program
        for fn in program.functions.values():
            for op in fn.block.operations:
                usage = plan.get_compute_device_usage_for_mlprogram_operation(op)
                if usage is None:
                    continue
                dev = type(usage.preferred_compute_device).__name__.replace("MLComputeDevice", "").replace("ComputeDevice", "")
                counts[dev] = counts.get(dev, 0) + 1
        return counts
    except Exception as e:  # compute plan is diagnostic only
        return {"error": str(e)[:300]}


# ---------------------------------------------------------------- reports

def sha256(path: Path) -> str:
    h = hashlib.sha256()
    if path.is_dir():
        for p in sorted(path.rglob("*")):
            if p.is_file():
                h.update(p.read_bytes())
    else:
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
    return h.hexdigest()


def size_bytes(path: Path) -> int:
    if path.is_dir():
        return sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    size = path.stat().st_size
    data = path.with_name(path.name + ".data")
    return size + (data.stat().st_size if data.exists() else 0)


def versions(*pkgs: str) -> dict:
    from importlib.metadata import PackageNotFoundError, version
    out = {"python": platform.python_version(), "macos": platform.mac_ver()[0], "machine": platform.machine()}
    for p in pkgs:
        try:
            out[p] = version(p)
        except PackageNotFoundError:
            pass
    return out


def device() -> str:
    try:
        return subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"], capture_output=True, text=True).stdout.strip()
    except OSError:
        return platform.processor()


def write_report(model: str, report: dict) -> Path:
    REPORTS.mkdir(parents=True, exist_ok=True)
    path = REPORTS / f"{model}.json"
    report = {"model": model, "device": device(), "threshold_f1": THRESHOLD, **report}
    path.write_text(json.dumps(report, indent=1, default=_json_default) + "\n")
    return path


def _json_default(o):
    if isinstance(o, (np.floating, np.integer)):
        return o.item()
    if isinstance(o, Path):
        return str(o)
    raise TypeError(type(o))


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(MAIN))
    except ValueError:
        return str(path)
