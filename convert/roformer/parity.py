"""BS-RoFormer SW / Mega-53 parity: converted core vs PyTorch CPU fp32 through MSST's demix().

The converted core replaces BSRoformer.forward between STFT and complex mask (convert.py);
MSST's chunking (chunk_size from the model config, num_overlap, fades) and the STFT/iSTFT
stay upstream code. Both models are run through the MSST pipeline, including BS-RoFormer SW
(the separator adapter runs SW through audio-separator, whose chunking differs; the network
and weights are the same).

  uv run python parity.py sw|mega53 [backend ...]      # -> convert/reports/<name>.json
  uv run python parity.py bench sw|mega53 <backend> [seconds]
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

BACKENDS = {
    "sw": ["onnx-fp32-ort-cpu", "onnx-fp16-ort-cpu", "coreml-fp16-ALL", "coreml-fp16-CPU_AND_GPU"],
    "mega53": ["onnx-fp32-ort-cpu", "coreml-fp16-ALL"],
}
# Backends that could not run, with what happened (measured on this machine).
BLOCKED = {
    "sw": {"onnx-fp32-ort-coreml": "process killed by the OS (exit 137, out of memory) on the first 13.4 s chunk "
                                    "while the CoreML execution provider compiled/ran the graph (48 GB machine)"},
    "mega53": {"onnx-fp16-ort-cpu": "not run: ORT emulates fp16 on CPU (SW needed 22.5 GB vs 14.2 GB for fp32); "
                                     "the fp32 graph already peaks at 20.7 GB per 20 s chunk on this 48 GB machine. "
                                     "The fp16 ONNX is exported for GPU execution providers"},
}
TRANSCRIBE = {"sw": ["other", "vocals", "bass"], "mega53": ["trumpet", "brass", "bass"]}


def make_model(key: str, backend: str):
    model, config = C.load(key)
    if backend == "torch-cpu":
        return model, config
    name = C.SPECS[key]["name"]
    if backend.startswith("onnx-"):
        _, precision, _, provider = backend.split("-")
        sess = P.ort_session(C.out_dir(key) / f"{name}-core-{precision}.onnx", provider, verbose=True,
                             low_memory=key == "mega53")

        def run(x):
            return torch.from_numpy(sess.run(["mask"], {"x": x.numpy()})[0].astype(np.float32))
    else:
        import coremltools as ct
        _, precision, units = backend.split("-", 2)
        ml = ct.models.MLModel(str(C.out_dir(key) / f"{name}-core-{precision}.mlpackage"),
                               compute_units=getattr(ct.ComputeUnit, units))

        def run(x):
            return torch.from_numpy(ml.predict({"x": x.numpy().astype(np.float32)})["mask"].astype(np.float32))
    model.forward = lambda audio: C.split_forward(model, run, audio)
    return model, config


def separate(model, config, clip: P.Clip) -> dict[str, np.ndarray]:
    from utils.model_utils import demix
    return demix(config, model, P.load_stereo(clip, 44100), torch.device("cpu"), "bs_roformer", pbar=False)


def bench(key: str, backend: str, seconds: float) -> dict:
    if backend.startswith("coreml"):
        import coremltools  # noqa: F401
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    model, config = make_model(key, backend)
    load = time.perf_counter() - t
    clip = P.Clip("bench", P.DATA / "mikkel" / "mikkel.wav", "mix", 60.0, seconds)
    timing = P.time_runs(lambda: separate(model, config, clip), n=1)
    return {"model": key, "backend": backend, "audio_s": seconds, "load_s": load, **timing,
            "rtf": timing["median_s"] / seconds, "peak_rss_mb": P.peak_rss_bytes() / 2**20,
            "baseline_rss_mb": base / 2**20, "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20,
            "note": "one warm-up run, then one timed run"}


def main(key: str, backends: list[str]) -> None:
    clips = P.separator_clips()
    name = C.SPECS[key]["name"]
    work = C.out_dir(key) / "parity"
    model, config = make_model(key, "torch-cpu")
    ref = {c.name: separate(model, config, c) for c in clips}
    del model
    results, gate, benches = {}, {}, {}
    for backend in backends:
        model, config = make_model(key, backend)
        est = {c.name: separate(model, config, c) for c in clips}
        del model
        results[backend] = S.compare(ref, est, 44100, TRANSCRIBE[key], work, backend)
        gate[backend] = S.passes(results[backend])
        r = results[backend]
        print(backend, r["sdr_db_min"], r["swift_f0_note_f1"]["f1"], r["basic_pitch_note_f1"]["f1"], flush=True)
    for backend in ["torch-cpu"] + backends:
        benches[backend] = P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", key, backend, "30"])
        print("bench", backend, json.dumps(benches[backend]), flush=True)
    plans = {u: P.coreml_compute_plan(C.out_dir(key) / f"{name}-core-fp16.mlpackage", u)
             for u in ("CPU_AND_GPU", "CPU_AND_NE", "ALL")
             if (C.out_dir(key) / f"{name}-core-fp16.mlpackage").exists()}
    artifacts = {f.name: {"size_bytes": P.size_bytes(f)} for f in sorted(C.out_dir(key).iterdir())
                 if f.suffix in (".onnx", ".mlpackage")}
    artifacts[f"checkpoint/{C.SPECS[key]['ckpt'].name}"] = {"size_bytes": C.SPECS[key]["ckpt"].stat().st_size,
                                                            "sha256": P.sha256(C.SPECS[key]["ckpt"])}
    report = {
        "reference": {"runtime": "PyTorch CPU fp32", "model": f"MSST BSRoformer, {C.SPECS[key]['config'].name}",
                      "pipeline": "MSST utils.model_utils.demix (chunk_size and num_overlap from the config)",
                      "chunk_samples": C.chunk_size(config)},
        "graph_boundary": "STFT and complex mask + iSTFT on the host; the core is band split, transformers, "
                          "mask estimators",
        "metric": f"stem SDR vs PyTorch stem; note F1 (50 ms onsets) of SwiftF0 and Basic Pitch on converted vs "
                  f"PyTorch {', '.join(TRANSCRIBE[key])} stems; gate on both note F1s",
        "clips": [f"{c.name} [{c.start}s +{c.duration}s]" for c in clips],
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "coreml_compute_plan": plans,
        "blocked": BLOCKED[key],
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("torch", "onnxruntime", "onnx", "coremltools", "swift-f0", "mir_eval"),
        "command": f"cd convert/roformer && uv run python convert.py {key} && uv run python parity.py {key}",
    }
    print("wrote", P.write_report(name, report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 30.0)))
    else:
        key = sys.argv[1]
        main(key, sys.argv[2:] or BACKENDS[key])
