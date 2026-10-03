"""SwiftF0 parity: converted models vs the upstream ONNX model on ONNX Runtime CPU.

SwiftF0 ships no PyTorch weights, so the reference is the upstream package as the adapter
runs it. Each backend replaces only the model call inside the upstream `SwiftF0` class
(session.run), so resampling, windowing, silence gating and note segmentation stay the
package's own code.

  uv run python parity.py            # full parity + benchmarks -> convert/reports/swift-f0.json
  uv run python parity.py bench <backend> [seconds]   # one isolated benchmark (JSON on stdout)
"""

from __future__ import annotations

import os

# ONNX Runtime reports to Microsoft unless this is set before it starts.
os.environ.setdefault("ORT_DISABLE_TELEMETRY", "1")

import json
import math
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import parity as P  # noqa: E402

from swift_f0 import SwiftF0, segment_notes  # noqa: E402
from swift_f0.core import HOP, SAMPLE_RATE  # noqa: E402

import convert as C  # noqa: E402

UNITS = ["CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "ALL"]
BACKENDS = (["ort-cpu-static", "ort-coreml-static"]
            + [f"coreml-{p}-{u}" for p in ("fp32", "fp16") for u in UNITS]
            + ["coreml-split-CPU_AND_NE", "coreml-split-CPU_AND_GPU"])


class PaddedSession:
    """Runs a fixed-length model on shorter audio: zero-pad, run, keep the real frames."""

    def __init__(self, run, samples: int):
        self._run, self.samples = run, samples

    def run(self, names, feed):
        audio = feed["audio"]
        n = audio.shape[1]
        frames = max(1, n // HOP)
        if n > self.samples:
            raise ValueError(f"window of {n} samples exceeds the model's {self.samples}")
        padded = np.zeros((1, self.samples), np.float32)
        padded[:, :n] = audio
        pitch, confidence = self._run(padded, float(feed["fmin"]), float(feed["fmax"]))
        return [pitch[:, :frames], confidence[:, :frames]]


def _split_runner(length: str, trunk_units: str):
    """Chain the three mixed-precision models (mixed.py): fp32 front/head on the GPU, fp16 trunk."""
    import coremltools as ct
    models = {}
    for part in ("front", "trunk", "head"):
        units = trunk_units if part == "trunk" else "CPU_AND_GPU"
        ml = ct.models.MLModel(str(C.OUT / f"swift-f0-{length}-mixed-{part}.mlpackage"),
                               compute_units=getattr(ct.ComputeUnit, units))
        meta = ml.user_defined_metadata
        models[part] = (ml, meta["onnx_inputs"].split(","), meta["onnx_outputs"].split(","))

    def call(part, tensors):
        ml, ins, outs = models[part]
        res = ml.predict({f"in{i}": tensors[n] for i, n in enumerate(ins)})
        tensors.update({n: res[f"out{i}"] for i, n in enumerate(outs)})

    def run(a, lo, hi):
        tensors = {"audio": a, "fmin": np.array([lo], np.float32), "fmax": np.array([hi], np.float32)}
        for part in ("front", "trunk", "head"):
            call(part, tensors)
        return tensors["pitch"].astype(np.float64), tensors["confidence"].astype(np.float64)
    return run


def make_detector(backend: str, length: str = "window") -> SwiftF0:
    det = SwiftF0()
    if backend == "ort-cpu-upstream":
        return det
    samples = C.LENGTHS[length]
    if backend.startswith("ort-"):
        sess = P.ort_session(C.OUT / f"swift-f0-{length}.onnx", "coreml" if "coreml" in backend else "cpu",
                             verbose="coreml" in backend)

        def run(a, lo, hi):
            return sess.run(["pitch", "confidence"], {"audio": a, "fmin": np.asarray(lo, np.float32),
                                                      "fmax": np.asarray(hi, np.float32)})
    elif backend.startswith("coreml-split-"):
        run = _split_runner(length, backend.rsplit("-", 1)[1])
    else:
        import coremltools as ct
        _, precision, units = backend.split("-", 2)
        ml = ct.models.MLModel(str(C.OUT / f"swift-f0-{length}-{precision}.mlpackage"),
                               compute_units=getattr(ct.ComputeUnit, units))

        def run(a, lo, hi):
            out = ml.predict({"audio": a, "fmin": np.array([lo], np.float32), "fmax": np.array([hi], np.float32)})
            return out["pitch"].astype(np.float64), out["confidence"].astype(np.float64)
    det.session = PaddedSession(run, samples)
    return det


def to_notes(result) -> P.Notes:
    return [(n.start, n.end, float(round(69 + 12 * math.log2(n.pitch_hz / 440.0))))
            for n in segment_notes(result, pitch_hold_ms=80.0)]


def detect(det: SwiftF0, clip: P.Clip):
    audio, sr = P.load_audio(clip)
    return det.detect(audio, sr)


def stream(det: SwiftF0, clip: P.Clip):
    from swift_f0 import concat
    audio, sr = P.load_audio(clip, sr=SAMPLE_RATE, mono=True)
    s = det.stream()
    parts = [s.push(audio[i:i + SAMPLE_RATE], SAMPLE_RATE) for i in range(0, len(audio), SAMPLE_RATE)]
    parts.append(s.flush())
    return concat(parts)


def frame_stats(ref, est) -> dict:
    n = min(len(ref.pitch_hz), len(est.pitch_hz))
    rv, ev = ref.confidence[:n] >= 0.5, est.confidence[:n] >= 0.5
    both = rv & ev
    cents = np.abs(1200 * np.log2(est.pitch_hz[:n][both] / ref.pitch_hz[:n][both])) if both.any() else np.zeros(1)
    return {"frames": int(n), "voicing_agree": float(np.mean(rv == ev)), "cents_p99": float(np.percentile(cents, 99)),
            "conf_max_abs": float(np.max(np.abs(ref.confidence[:n] - est.confidence[:n])))}


def bench(backend: str, seconds: float) -> dict:
    if backend.startswith("coreml"):
        import coremltools  # noqa: F401  (count the runtime import in the baseline)
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    det = make_detector(backend)
    load = time.perf_counter() - t
    rng = np.random.default_rng(0)
    tt = np.arange(int(seconds * SAMPLE_RATE)) / SAMPLE_RATE
    audio = (0.3 * np.sin(2 * np.pi * 330 * tt) + 0.01 * rng.standard_normal(len(tt))).astype(np.float32)
    timing = P.time_runs(lambda: det.detect(audio, SAMPLE_RATE), n=5)
    return {"backend": backend, "audio_s": seconds, "load_s": load, **timing,
            "rtf": timing["median_s"] / seconds, "peak_rss_mb": P.peak_rss_bytes() / 2**20,
            "baseline_rss_mb": base / 2**20, "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20}


def main() -> None:
    clips = P.eval_parts() + P.eval_mixes()
    ref_det = make_detector("ort-cpu-upstream")
    refs = {c.name: detect(ref_det, c) for c in clips}
    ref_notes = {k: to_notes(v) for k, v in refs.items()}
    results = {}
    for backend in BACKENDS:
        det = make_detector(backend)
        per_clip, frames = {}, {}
        for c in clips:
            est = detect(det, c)
            per_clip[c.name] = P.note_match(ref_notes[c.name], to_notes(est))
            frames[c.name] = frame_stats(refs[c.name], est)
        parts = {k: v for k, v in per_clip.items() if not k.startswith(("choralebricks-brass4/", "urmp-brass/"))}
        mixes = {k: v for k, v in per_clip.items() if k not in parts}
        results[backend] = {
            "note_f1": P.pool(per_clip), "note_f1_parts": P.pool(parts), "note_f1_mixes": P.pool(mixes),
            "frames": {"voicing_agree_min": min(f["voicing_agree"] for f in frames.values()),
                       "cents_p99_max": max(f["cents_p99"] for f in frames.values()),
                       "conf_max_abs": max(f["conf_max_abs"] for f in frames.values())},
            "per_clip_f1": {k: round(v["f1"], 4) for k, v in per_clip.items()},
        }
        print(backend, json.dumps(results[backend]["note_f1"]), flush=True)

    # Streaming: 1 s pushes through the 128-frame model vs the upstream batch result.
    stream_clips = [c for c in clips if c.kind == "part"][:12]
    for backend in ("ort-coreml-static", "coreml-fp32-ALL", "coreml-fp16-ALL", "coreml-split-CPU_AND_NE"):
        det = make_detector(backend, "stream")
        per_clip = {c.name: P.note_match(ref_notes[c.name], to_notes(stream(det, c))) for c in stream_clips}
        results[f"stream/{backend}"] = {"note_f1": P.pool(per_clip),
                                        "per_clip_f1": {k: round(v["f1"], 4) for k, v in per_clip.items()}}
        print("stream", backend, json.dumps(results[f"stream/{backend}"]["note_f1"]), flush=True)

    benches = {}
    for backend in ["ort-cpu-upstream"] + BACKENDS:
        benches[backend] = P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", backend, "30"])
        print("bench", backend, json.dumps(benches[backend]), flush=True)

    plans = {f"{p}-{u}": P.coreml_compute_plan(C.OUT / f"swift-f0-window-{p}.mlpackage", u)
             for p in ("fp32", "fp16") for u in UNITS}
    plans["mixed-trunk-CPU_AND_NE"] = P.coreml_compute_plan(C.OUT / "swift-f0-window-mixed-trunk.mlpackage", "CPU_AND_NE")
    artifacts = {}
    for f in sorted(C.OUT.iterdir()):
        artifacts[f.name] = {"size_bytes": P.size_bytes(f), "sha256": P.sha256(f)}
    gate = {b: r["note_f1"]["f1"] >= P.THRESHOLD for b, r in results.items()}
    report = {
        "reference": {"runtime": "onnxruntime CPU", "model": "swift_f0/model.onnx (upstream package)",
                      "sha256": P.sha256(C.UPSTREAM), "size_bytes": C.UPSTREAM.stat().st_size,
                      "note_segmentation": "swift_f0.segment_notes(pitch_hold_ms=80)"},
        "clips": {"parts": sum(c.kind == "part" for c in clips), "mixes": sum(c.kind == "mix" for c in clips)},
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "coreml_compute_plan_window": plans,
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("swift-f0", "onnxruntime", "coremltools", "torch", "onnx2torch", "onnxsim", "mir_eval"),
        "command": "cd convert/swift-f0 && uv run python convert.py && uv run python mixed.py && uv run python parity.py",
    }
    print("wrote", P.write_report("swift-f0", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 30.0)))
    else:
        main()
