"""Beat This! parity: converted ONNX / Core ML vs the PyTorch checkpoint on CPU (fp32).

Each backend replaces only the network inside the upstream `File2Beats` pipeline, so audio
loading, the log-mel frontend, 1500-frame chunking, aggregation and the minimal peak-picking
postprocessor stay upstream code. The output is beat and downbeat times, so parity is
event F1 at a 50 ms window (mir_eval.util.match_events), reported for beats and downbeats.

  uv run python parity.py                    # -> convert/reports/beat-this.json
  uv run python parity.py bench <checkpoint> <backend> [seconds]
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

from beat_this.inference import Audio2Beats, File2Beats  # noqa: E402

import convert as C  # noqa: E402

UNITS = ["CPU_ONLY", "CPU_AND_GPU", "CPU_AND_NE", "ALL"]
BACKENDS = {
    "small0": ["onnx-ort-cpu", "onnx1500-ort-coreml"] + [f"coreml-{p}-{u}" for p in ("fp32", "fp16") for u in UNITS],
    "final0": ["onnx-ort-cpu", "onnx1500-ort-coreml", "coreml-fp32-ALL", "coreml-fp16-ALL", "coreml-fp16-CPU_AND_NE"],
}


def _pad_crop(run):
    """Fixed 1500-frame models: pad a short chunk with zeros, crop the logits back.

    Pieces under 30 s are one short chunk upstream; zero padding changes the attention
    context, so these clips do not match PyTorch exactly (see the report).
    """
    def wrapped(x):
        n = x.shape[1]
        if n < C.CHUNK:
            x = np.concatenate([x, np.zeros((1, C.CHUNK - n, x.shape[2]), np.float32)], axis=1)
        beat, downbeat = run(x)
        return beat[:, :n], downbeat[:, :n]
    return wrapped


class Runtime(torch.nn.Module):
    """Stands in for BeatThis inside the upstream pipeline: (1, T, 128) -> {beat, downbeat}."""

    def __init__(self, run):
        super().__init__()
        self._run = run

    def forward(self, spect):
        beat, downbeat = self._run(spect.float().numpy())
        return {"beat": torch.from_numpy(np.asarray(beat, np.float32)),
                "downbeat": torch.from_numpy(np.asarray(downbeat, np.float32))}


def make_tracker(ckpt: str, backend: str) -> File2Beats:
    tracker = File2Beats(checkpoint_path=ckpt, device="cpu", float16=False, dbn=False)
    if backend == "torch-cpu":
        return tracker
    if backend.startswith("onnx"):
        static = backend.startswith("onnx1500-")
        sess = P.ort_session(C.OUT / f"beat-this-{ckpt}{'-1500' if static else ''}.onnx", backend.rsplit("-", 1)[1],
                             verbose=True)

        def run(x):
            return sess.run(["beat", "downbeat"], {"spect": x})
        if static:
            run = _pad_crop(run)
    else:
        import coremltools as ct
        _, precision, units = backend.split("-", 2)
        ml = ct.models.MLModel(str(C.OUT / f"beat-this-{ckpt}-{precision}.mlpackage"),
                               compute_units=getattr(ct.ComputeUnit, units))

        def run(x):
            out = ml.predict({"spect": x})
            return out["beat"], out["downbeat"]
        run = _pad_crop(run)
    tracker.model = Runtime(run)
    return tracker


def clips() -> list[P.Clip]:
    return P.eval_mixes() + [P.Clip("mikkel/full", P.DATA / "mikkel" / "mikkel.wav", "mix")]


def track(tracker: File2Beats, clip: P.Clip) -> tuple[np.ndarray, np.ndarray]:
    audio, sr = P.load_audio(clip)
    beats, downbeats = Audio2Beats.__call__(tracker, audio.astype(np.float64), sr)
    return np.asarray(beats), np.asarray(downbeats)


def bench(ckpt: str, backend: str, seconds: float) -> dict:
    if backend.startswith("coreml"):
        import coremltools  # noqa: F401
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    tracker = make_tracker(ckpt, backend)
    load = time.perf_counter() - t
    audio, sr = P.load_audio(P.Clip("bench", P.DATA / "mikkel" / "mikkel.wav", "mix", 0.0, seconds))
    call = Audio2Beats.__call__
    timing = P.time_runs(lambda: call(tracker, audio.astype(np.float64), sr), n=3)
    return {"checkpoint": ckpt, "backend": backend, "audio_s": seconds, "load_s": load, **timing,
            "rtf": timing["median_s"] / seconds, "peak_rss_mb": P.peak_rss_bytes() / 2**20,
            "baseline_rss_mb": base / 2**20, "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20,
            "note": "latency includes resampling and the log-mel frontend (torch), as upstream runs it"}


def main() -> None:
    cl = clips()
    report_parity, benches, plans, gate = {}, {}, {}, {}
    for ckpt, backends in BACKENDS.items():
        ref_tracker = make_tracker(ckpt, "torch-cpu")
        ref = {c.name: track(ref_tracker, c) for c in cl}
        for backend in backends:
            tracker = make_tracker(ckpt, backend)
            beats, downs = {}, {}
            for c in cl:
                b, d = track(tracker, c)
                beats[c.name] = P.event_match(ref[c.name][0], b)
                downs[c.name] = P.event_match(ref[c.name][1], d)
            key = f"{ckpt}/{backend}"
            report_parity[key] = {"beat_f1": P.pool(beats), "downbeat_f1": P.pool(downs),
                                  "per_clip_beat_f1": {k: round(v["f1"], 4) for k, v in beats.items()},
                                  "per_clip_downbeat_f1": {k: round(v["f1"], 4) for k, v in downs.items()}}
            gate[key] = min(report_parity[key]["beat_f1"]["f1"], report_parity[key]["downbeat_f1"]["f1"]) >= P.THRESHOLD
            print(key, round(report_parity[key]["beat_f1"]["f1"], 4), round(report_parity[key]["downbeat_f1"]["f1"], 4),
                  flush=True)
        for backend in ["torch-cpu"] + backends:
            key = f"{ckpt}/{backend}"
            benches[key] = P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", ckpt, backend, "60"])
            print("bench", key, json.dumps(benches[key]), flush=True)
        for p in ("fp32", "fp16"):
            for u in UNITS:
                plans[f"{ckpt}-{p}-{u}"] = P.coreml_compute_plan(C.OUT / f"beat-this-{ckpt}-{p}.mlpackage", u)
    artifacts = {f.name: {"size_bytes": P.size_bytes(f), "sha256": P.sha256(f)}
                 for f in sorted(C.OUT.iterdir()) if f.suffix in (".onnx", ".mlpackage")}
    for ckpt in BACKENDS:
        path = C.checkpoint_path(ckpt)
        artifacts[f"checkpoint/{path.name}"] = {"size_bytes": path.stat().st_size, "sha256": P.sha256(path)}
    report = {
        "reference": {"runtime": "PyTorch CPU fp32", "pipeline": "beat_this.inference.File2Beats (minimal postprocessor)",
                      "checkpoints": list(BACKENDS)},
        "metric": "event F1 of beat and downbeat times vs PyTorch output, 50 ms window; gate on the lower of the two",
        "clips": [c.name for c in cl],
        "artifacts": artifacts,
        "parity": report_parity,
        "benchmarks": benches,
        "coreml_compute_plan": plans,
        "pass": gate,
        "pass_all": all(gate.values()),
        "limitation": "fixed 1500-frame models (Core ML, static ONNX on the CoreML EP) zero-pad pieces under 30 s, "
                      "which upstream runs as one shorter chunk; the two such eval clips (Vulpius_*) deviate. "
                      "The dynamic ONNX is exact for any length.",
        "frontend": "log-mel (torchaudio MelSpectrogram, 22.05 kHz, n_fft 1024, hop 441, 128 slaney mels, "
                    "log1p(1000x)) runs outside the exported graph and must be ported per platform",
        "versions": P.versions("beat-this", "torch", "torchaudio", "onnxruntime", "coremltools", "mir_eval"),
        "command": "cd convert/beat-this && uv run python convert.py && uv run python parity.py",
    }
    print("wrote", P.write_report("beat-this", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], sys.argv[3], float(sys.argv[4]) if len(sys.argv) > 4 else 60.0)))
    else:
        main()
