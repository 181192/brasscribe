"""MuScriptor parity: ONNX prefill/decode graphs vs PyTorch CPU fp32, greedy decoding.

The ONNX generator replaces only LMModel.generate inside the upstream TranscriptionModel,
so chunking, conditioning (log-mel + class embeddings), prelude forcing, detokenisation and
MIDI writing stay upstream code. Parity is (1) exact token-sequence agreement per chunk and
(2) note F1 of the resulting MIDI vs the PyTorch MIDI (50 ms onsets).

  uv run python parity.py [size]               # -> convert/reports/muscriptor.json
  uv run python parity.py bench <backend> [size] [seconds]
"""

from __future__ import annotations

import io
import json
import sys
import time
from contextlib import redirect_stdout
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common import parity as P  # noqa: E402

import convert as C  # noqa: E402

BACKENDS = ["onnx-ort-cpu"]
BLOCKED = {
    "onnx-ort-coreml": "CoreML EP fails to build the prefill graph (dynamic sequence axes: 'unbounded dimension', "
                       "then 'Failed to build the model execution plan', error -7). Needs static-shape graphs "
                       "(fixed prefix/past lengths with a padded, masked KV cache).",
    "coreml / mlx-swift": "not attempted. Core ML needs the same static-shape KV-cache rewrite (or coremltools "
                          "stateful models). MLX Swift has no port of this model: the transformer, the log-mel "
                          "conditioner, the MT3 detokeniser and the prelude-forcing loop would have to be "
                          "reimplemented in Swift and the safetensors weights mapped; none of that exists yet.",
}


class OrtGenerator:
    """Greedy LMModel.generate (beam 1, no CFG, no sampling) on ONNX Runtime sessions."""

    def __init__(self, lm, size: str, provider: str) -> None:
        self.lm = lm
        self.prefill = P.ort_session(C.OUT / f"muscriptor-{size}-prefill.onnx", provider, verbose=True,
                                     static_shapes=False)
        self.decode = P.ort_session(C.OUT / f"muscriptor-{size}-decode.onnx", provider, verbose=True,
                                    static_shapes=False)

    def __call__(self, prompt=None, conditions=(), num_samples=None, max_gen_len=256, use_sampling=True, temp=1.0,
                 top_k=0, top_p=0.0, cfg_coef=None, early_stop_on_token=None, beam_size=1, beam_length_score_alpha=0.75,
                 forbidden_tokens=None):
        lm = self.lm
        assert beam_size == 1 and not (use_sampling and temp > 0) and (cfg_coef in (None, 1.0))
        with torch.inference_mode():
            cond_tensors = lm.condition_provider(lm.condition_provider.tokenize(list(conditions)))
        prefix = None
        for cond, _ in cond_tensors.values():  # LMModel.forward prepends each in turn
            prefix = cond if prefix is None else torch.cat([cond, prefix], dim=1)
        prefix = prefix.float().numpy()
        B = prefix.shape[0]
        ungenerated = lm.ungenerated_token_id
        gen = np.full((B, max_gen_len + 1), ungenerated, dtype=np.int64)
        gen[:, 0] = lm.initial_token_id
        start = 0
        if prompt is not None:
            pt = prompt.shape[-1]
            gen[:, 1:1 + pt] = prompt.cpu().numpy()
            start = max(0, int(np.nonzero(gen == ungenerated)[1].min()) - 1)
        forbidden = None if forbidden_tokens is None else np.asarray(forbidden_tokens, dtype=np.int64)
        for t in range(start):
            yield torch.from_numpy(gen[:, t + 1].copy())
        P_len = prefix.shape[1]
        past_k = past_v = None
        for offset in range(start, max_gen_len):
            if early_stop_on_token is not None and (gen == early_stop_on_token).any(axis=1).all():
                break
            if offset == start:
                logits, past_k, past_v = self.prefill.run(None, {"cond": prefix, "tokens": gen[:, :offset + 1]})
            else:
                logits, past_k, past_v = self.decode.run(None, {
                    "token": gen[:, offset:offset + 1], "position": np.array([P_len + offset], dtype=np.int64),
                    "past_k": past_k, "past_v": past_v})
            logits = logits.astype(np.float32)
            logits[:, 1393:] = -np.inf
            if forbidden is not None and forbidden.size:
                logits[:, forbidden] = -np.inf
            nxt = logits.argmax(axis=-1)
            step = gen[:, offset + 1]
            gen[:, offset + 1] = np.where(step == ungenerated, nxt, step)
            yield torch.from_numpy(gen[:, offset + 1].copy())


class Recorder:
    """Wraps a generate callable and records the token stream per call (one call per chunk)."""

    def __init__(self, fn) -> None:
        self.fn, self.calls = fn, []

    def __call__(self, *args, **kwargs):
        tokens = []
        self.calls.append(tokens)
        for step in self.fn(*args, **kwargs):
            tokens.append(int(step[0]))
            yield step


def make(backend: str, size: str):
    tm = C.load(size)
    fn = tm._model.generate if backend == "torch-cpu" else OrtGenerator(tm._model, size, backend.rsplit("-", 1)[1])
    rec = Recorder(fn)
    tm._model.generate = rec
    return tm, rec


def transcribe(tm, clip: P.Clip, out: Path) -> P.Notes:
    audio, sr = P.load_audio(clip, mono=True)
    wav = torch.from_numpy(audio)[None]
    with redirect_stdout(io.StringIO()):
        midi = tm.transcribe_to_midi((wav, sr), use_sampling=False, detect_tempo=False)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(midi)
    return P.midi_notes(out)


def bench(backend: str, size: str, seconds: float) -> dict:
    base = P.peak_rss_bytes()
    t = time.perf_counter()
    tm, rec = make(backend, size)
    load = time.perf_counter() - t
    clip = P.Clip("bench", P.DATA / "mikkel" / "mikkel.wav", "mix", 60.0, seconds)
    out = C.OUT / "parity" / "bench" / f"{backend}.mid"
    t = time.perf_counter()
    transcribe(tm, clip, out)
    wall = time.perf_counter() - t
    n_tokens = sum(len(c) for c in rec.calls)
    return {"backend": backend, "size": size, "audio_s": seconds, "load_s": load, "median_s": wall, "runs": 1,
            "rtf": wall / seconds, "tokens": n_tokens, "ms_per_token": 1000 * wall / max(1, n_tokens),
            "peak_rss_mb": P.peak_rss_bytes() / 2**20, "baseline_rss_mb": base / 2**20,
            "model_rss_mb": (P.peak_rss_bytes() - base) / 2**20,
            "note": "single cold run incl. conditioning and detokenisation"}


def main(size: str) -> None:
    clips = P.separator_clips()
    work = C.OUT / "parity"
    tm, rec = make("torch-cpu", size)
    ref_notes, ref_tokens = {}, {}
    for c in clips:
        rec.calls.clear()
        ref_notes[c.name] = transcribe(tm, c, work / "torch-cpu" / f"{c.name.replace('/', '__')}.mid")
        ref_tokens[c.name] = [list(x) for x in rec.calls]
    del tm
    results, gate = {}, {}
    for backend in BACKENDS:
        tm, rec = make(backend, size)
        per_clip, token_match = {}, {}
        for c in clips:
            rec.calls.clear()
            notes = transcribe(tm, c, work / backend / f"{c.name.replace('/', '__')}.mid")
            per_clip[c.name] = P.note_match(ref_notes[c.name], notes)
            chunks = list(zip(ref_tokens[c.name], rec.calls))
            token_match[c.name] = {"chunks": len(chunks), "identical_chunks": sum(a == b for a, b in chunks),
                                   "tokens_ref": sum(len(a) for a, _ in chunks),
                                   "first_divergence": next(([i, next(j for j, (x, y) in enumerate(zip(a, b)) if x != y)
                                                              if any(x != y for x, y in zip(a, b)) else min(len(a), len(b))]
                                                             for i, (a, b) in enumerate(chunks) if a != b), None)}
        del tm
        results[backend] = {"note_f1": P.pool(per_clip), "per_clip_f1": {k: round(v["f1"], 4) for k, v in per_clip.items()},
                            "tokens": token_match}
        gate[backend] = results[backend]["note_f1"]["f1"] >= P.THRESHOLD
        print(backend, json.dumps(results[backend]["note_f1"]), json.dumps(token_match), flush=True)
    benches = {b: P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", b, size, "30"])
               for b in ["torch-cpu"] + BACKENDS}
    for b, v in benches.items():
        print("bench", b, json.dumps(v), flush=True)
    artifacts = {f.name: {"size_bytes": P.size_bytes(f)} for f in sorted(C.OUT.iterdir()) if f.suffix == ".onnx"}
    report = {
        "reference": {"runtime": "PyTorch CPU fp32", "model": f"MuScriptor {size} (HF MuScriptor/muscriptor-{size})",
                      "pipeline": "TranscriptionModel.transcribe_to_midi, greedy, prelude forcing, detect_tempo=False"},
        "graph_boundary": "conditioning (log-mel + projection + class embeddings) on the host; transformer as "
                          "prefill and decode-with-past ONNX graphs; greedy loop on the host",
        "metric": "exact token agreement per 5 s chunk and note F1 (50 ms onsets) of the MIDI vs PyTorch",
        "clips": [f"{c.name} [{c.start}s +{c.duration}s]" for c in clips],
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "blocked": BLOCKED,
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("muscriptor", "torch", "onnxruntime", "onnx", "mir_eval"),
        "command": f"cd convert/muscriptor && uv run python convert.py {size} && uv run python parity.py {size}",
    }
    print("wrote", P.write_report("muscriptor", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "medium",
                               float(sys.argv[4]) if len(sys.argv) > 4 else 30.0)))
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "medium")
