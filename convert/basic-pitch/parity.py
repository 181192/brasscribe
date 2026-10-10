"""Basic Pitch parity: the upstream Core ML, TFLite and ONNX exports vs the TensorFlow SavedModel.

Basic Pitch is a TensorFlow model; Spotify ships all four formats in the package, so nothing
is converted here. Each backend is a `basic_pitch.inference.Model` whose `predict` goes to a
different runtime; windowing, output unwrapping and note creation are the package's own
`predict()` with its CLI defaults, as the adapter runs it.

  uv run python parity.py                 # full parity + benchmarks -> convert/reports/basic-pitch.json
  uv run python parity.py bench <backend> [seconds]
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import parity as P  # noqa: E402

import basic_pitch  # noqa: E402
from basic_pitch import inference  # noqa: E402
from basic_pitch.inference import Model  # noqa: E402

import convert as C  # noqa: E402

SAVED = Path(basic_pitch.__file__).parent / "saved_models" / "icassp_2022"
UNITS = ["CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "ALL"]
BACKENDS = (["tflite-litert-cpu", "onnx-ort-cpu", "onnx-b1-ort-cpu", "onnx-b1-ort-coreml"]
            + [f"coreml-upstream-{u}" for u in UNITS]
            + [f"coreml-b1-{p}-{u}" for p in ("fp32", "fp16") for u in UNITS])
MLPACKAGES = {"upstream": SAVED / "nmp.mlpackage", "b1-fp32": C.OUT / "nmp-b1-fp32.mlpackage",
              "b1-fp16": C.OUT / "nmp-b1-fp16.mlpackage"}


def _units(backend: str) -> str:
    return next(u for u in UNITS if backend.endswith("-" + u))


def make_model(backend: str) -> Model:
    m = object.__new__(Model)
    if backend == "tf-savedmodel":
        import tensorflow as tf
        m.model_type, m.model = Model.MODEL_TYPES.TENSORFLOW, tf.saved_model.load(str(SAVED / "nmp"))
    elif backend.startswith("coreml-"):
        import coremltools as ct
        units = _units(backend)
        m.model_type = Model.MODEL_TYPES.COREML
        m.model = ct.models.MLModel(str(MLPACKAGES[backend[len("coreml-"):-len(units) - 1]]),
                                    compute_units=getattr(ct.ComputeUnit, units))
    elif backend == "tflite-litert-cpu":
        from ai_edge_litert.interpreter import Interpreter
        m.model_type = Model.MODEL_TYPES.TFLITE
        m.interpreter = Interpreter(str(SAVED / "nmp.tflite"))
        m.model = m.interpreter.get_signature_runner()
    elif backend.startswith("onnx-"):
        m.model_type = Model.MODEL_TYPES.ONNX
        path = C.STATIC if backend.startswith("onnx-b1-") else SAVED / "nmp.onnx"
        m.model = P.ort_session(path, backend.rsplit("-", 1)[1], verbose=True)
    else:
        raise ValueError(backend)
    return m


def transcribe(model: Model, path: Path) -> P.Notes:
    with contextlib.redirect_stdout(io.StringIO()):  # the Core ML branch prints per window
        _, _, events = inference.predict(str(path), model)
    return sorted((s, e, float(p)) for s, e, p, *_ in events)


def bench(backend: str, seconds: float) -> dict:
    import soundfile as sf
    if backend.startswith("coreml"):
        import coremltools  # noqa: F401
    if backend.startswith("tf"):
        import tensorflow  # noqa: F401
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    model = make_model(backend)
    load = time.perf_counter() - t
    clip = P.eval_mixes()[0]
    y, sr = P.load_audio(P.Clip(clip.name, clip.path, "mix", 0.0, seconds))
    tmp = P.CONVERTED / "basic-pitch" / "bench.wav"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    sf.write(tmp, y, sr)
    timing = P.time_runs(lambda: transcribe(model, tmp), n=3)
    return {"backend": backend, "audio_s": seconds, "load_s": load, **timing, "rtf": timing["median_s"] / seconds,
            "peak_rss_mb": P.peak_rss_bytes() / 2**20, "baseline_rss_mb": base / 2**20,
            "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20,
            "note": "latency includes librosa load/resample and note creation, as the adapter runs it"}


def main() -> None:
    clips = P.eval_mixes() + P.eval_parts()
    ref_model = make_model("tf-savedmodel")
    ref = {c.name: transcribe(ref_model, c.path) for c in clips}
    results = {}
    for backend in BACKENDS:
        model = make_model(backend)
        per_clip = {c.name: P.note_match(ref[c.name], transcribe(model, c.path)) for c in clips}
        mixes = {k: v for k, v in per_clip.items() if k.startswith(("choralebricks-brass4/", "urmp-brass/"))}
        parts = {k: v for k, v in per_clip.items() if k not in mixes}
        results[backend] = {"note_f1": P.pool(per_clip), "note_f1_mixes": P.pool(mixes), "note_f1_parts": P.pool(parts),
                            "per_clip_f1": {k: round(v["f1"], 4) for k, v in per_clip.items()}}
        print(backend, json.dumps(results[backend]["note_f1"]), flush=True)

    benches = {}
    for backend in ["tf-savedmodel"] + BACKENDS:
        benches[backend] = P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", backend, "30"])
        print("bench", backend, json.dumps(benches[backend]), flush=True)
    plans = {f"{name}-{u}": P.coreml_compute_plan(path, u) for name, path in MLPACKAGES.items() for u in UNITS}
    artifacts = {f"upstream/{f.name}": {"size_bytes": P.size_bytes(f), "sha256": P.sha256(f)}
                 for f in sorted(SAVED.iterdir())}
    artifacts.update({f.name: {"size_bytes": P.size_bytes(f), "sha256": P.sha256(f)}
                      for f in sorted(C.OUT.iterdir()) if f.suffix in (".onnx", ".mlpackage")})
    gate = {b: r["note_f1"]["f1"] >= P.THRESHOLD for b, r in results.items()}
    report = {
        "reference": {"runtime": "TensorFlow SavedModel (CPU)", "model": "basic_pitch/saved_models/icassp_2022/nmp",
                      "note_creation": "basic_pitch.inference.predict defaults (onset 0.5, frame 0.3, min 127.7 ms)"},
        "converted": "upstream Core ML/TFLite/ONNX exports as shipped, plus batch-1 ONNX and Core ML (convert.py)",
        "clips": {"mixes": sum(c.kind == "mix" for c in clips), "parts": sum(c.kind == "part" for c in clips)},
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "coreml_compute_plan": plans,
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("basic-pitch", "tensorflow-macos", "coremltools", "onnxruntime", "ai-edge-litert", "mir_eval"),
        "command": "cd convert/basic-pitch && uv run python convert.py && uv run python parity.py",
    }
    print("wrote", P.write_report("basic-pitch", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 30.0)))
    else:
        main()
