"""HT-Demucs parity: ONNX / Core ML core vs PyTorch CPU fp32, through demucs.apply.apply_model.

The converted core replaces the network between STFT and iSTFT (see convert.py); chunking,
overlap-add and the STFT stay upstream code. apply_model runs with shifts=0 so the reference
is deterministic (the demucs CLI default of one random shift would make two PyTorch runs
differ). Brass lands in 'other' (and low brass partly in 'bass'), so those stems are
transcribed for the note-F1 check.

  uv run python parity.py                       # -> convert/reports/htdemucs.json
  uv run python parity.py bench <backend> [seconds]
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import parity as P  # noqa: E402
from common import separation as S  # noqa: E402

import convert as C  # noqa: E402

UNITS = ["CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "ALL"]
BACKENDS = (["onnx-ort-cpu", "onnx-ort-coreml"] + [f"coreml-fp32-{u}" for u in ("CPU_ONLY", "CPU_AND_GPU", "ALL")]
            + [f"coreml-fp16-{u}" for u in ("CPU_AND_GPU", "CPU_AND_NE", "ALL")])
TRANSCRIBE = ["other", "bass"]
WORK = C.OUT / "parity"


def make_model(backend: str):
    torch.backends.mha.set_fastpath_enabled(False)
    model = C.load()
    if backend == "torch-cpu":
        return model
    if backend.startswith("onnx-"):
        sess = P.ort_session(C.OUT / f"{C.NAME}-core.onnx", backend.rsplit("-", 1)[1], verbose=True)

        def run(mix, mag):
            spec, wave = sess.run(["spec", "wave"], {"mix": mix.numpy(), "mag": mag.numpy()})
            return torch.from_numpy(spec), torch.from_numpy(wave)
    else:
        import coremltools as ct
        _, precision, units = backend.split("-", 2)
        ml = ct.models.MLModel(str(C.OUT / f"{C.NAME}-core-{precision}.mlpackage"),
                               compute_units=getattr(ct.ComputeUnit, units))

        def run(mix, mag):
            out = ml.predict({"mix": mix.numpy().astype(np.float32), "mag": mag.numpy().astype(np.float32)})
            return torch.from_numpy(out["spec"].astype(np.float32)), torch.from_numpy(out["wave"].astype(np.float32))
    model.forward = lambda mix: C.split_forward(model, run, mix)
    return model


def separate(model, clip: P.Clip) -> dict[str, np.ndarray]:
    from demucs.apply import apply_model
    mix = torch.from_numpy(P.load_stereo(clip, model.samplerate))[None]
    with torch.no_grad():
        out = apply_model(model, mix, shifts=0, split=True, overlap=0.25, progress=False, device="cpu")[0]
    return {s: out[i].numpy() for i, s in enumerate(model.sources)}


def bench(backend: str, seconds: float) -> dict:
    if backend.startswith("coreml"):
        import coremltools  # noqa: F401
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    model = make_model(backend)
    load = time.perf_counter() - t
    clip = P.Clip("bench", P.DATA / "mikkel" / "mikkel.wav", "mix", 60.0, seconds)
    timing = P.time_runs(lambda: separate(model, clip), n=2)
    return {"backend": backend, "audio_s": seconds, "load_s": load, **timing, "rtf": timing["median_s"] / seconds,
            "peak_rss_mb": P.peak_rss_bytes() / 2**20, "baseline_rss_mb": base / 2**20,
            "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20}


def main() -> None:
    clips = P.separator_clips()
    ref_model = make_model("torch-cpu")
    sr = ref_model.samplerate
    ref = {c.name: separate(ref_model, c) for c in clips}
    results, gate = {}, {}
    for backend in BACKENDS:
        model = make_model(backend)
        est = {c.name: separate(model, c) for c in clips}
        results[backend] = S.compare(ref, est, sr, TRANSCRIBE, WORK, backend)
        gate[backend] = S.passes(results[backend])
        r = results[backend]
        print(backend, r["sdr_db_min"], r["swift_f0_note_f1"]["f1"], r["basic_pitch_note_f1"]["f1"], flush=True)
    benches = {}
    for backend in ["torch-cpu"] + BACKENDS:
        benches[backend] = P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", backend, "30"])
        print("bench", backend, json.dumps(benches[backend]), flush=True)
    plans = {f"{p}-{u}": P.coreml_compute_plan(C.OUT / f"{C.NAME}-core-{p}.mlpackage", u)
             for p in ("fp32", "fp16") for u in UNITS}
    artifacts = {f.name: {"size_bytes": P.size_bytes(f), "sha256": P.sha256(f)}
                 for f in sorted(C.OUT.iterdir()) if f.suffix in (".onnx", ".mlpackage")}
    report = {
        "reference": {"runtime": "PyTorch CPU fp32", "model": "demucs.pretrained htdemucs (single model)",
                      "pipeline": "demucs.apply.apply_model(shifts=0, split=True, overlap=0.25)"},
        "graph_boundary": "STFT/_magnitude and _mask/iSTFT run on the host; the core is the rest of HTDemucs.forward",
        "metric": "stem SDR vs PyTorch stem; note F1 (50 ms onsets) of SwiftF0 and Basic Pitch on converted vs "
                  "PyTorch 'other' and 'bass' stems; gate on both note F1s",
        "clips": [f"{c.name} [{c.start}s +{c.duration}s]" for c in clips],
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "coreml_compute_plan": plans,
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("demucs", "torch", "onnxruntime", "coremltools", "swift-f0", "mir_eval"),
        "command": "cd convert/demucs && uv run python convert.py && uv run python parity.py",
    }
    print("wrote", P.write_report("htdemucs", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], float(sys.argv[3]) if len(sys.argv) > 3 else 30.0)))
    else:
        main()
