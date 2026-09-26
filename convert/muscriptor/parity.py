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
import convert_static as S  # noqa: E402

BACKENDS = ["onnx-ort-cpu", "static-ort-cpu", "static-ort-coreml", "coreml-fp16-ALL", "coreml-fp16-CPU_AND_GPU",
            "coreml-fp32-ALL"]
BLOCKED = {
    "onnx-ort-coreml": "the dynamic graphs: CoreML EP cannot build them ('unbounded dimension', error -7). "
                       "Superseded by the static-shape graphs (static-ort-coreml).",
    "coreml Neural Engine": "the stateful model has flexible query/cache lengths, which the Neural Engine does not "
                            "run; it runs on GPU/CPU. A Neural Engine build would need fixed Q and E per function.",
    "mlx-swift": "not attempted: no Swift port of the model, log-mel conditioner, MT3 detokeniser and "
                 "prelude-forcing loop exists; the Core ML stateful model is the Apple path instead.",
}


class DynamicOrt:
    """The dynamic prefill / decode-with-past ONNX graphs (convert.py)."""

    def __init__(self, lm, size: str, provider: str) -> None:
        self.prefill = P.ort_session(C.OUT / f"muscriptor-{size}-prefill.onnx", provider, verbose=True,
                                     static_shapes=False)
        self.decode = P.ort_session(C.OUT / f"muscriptor-{size}-decode.onnx", provider, verbose=True,
                                    static_shapes=False)

    def first(self, prefix, tokens):
        logits, self.k, self.v = self.prefill.run(None, {"cond": prefix, "tokens": tokens})
        return logits

    def next(self, token, position):
        logits, self.k, self.v = self.decode.run(None, {"token": token, "position": np.array([position], np.int64),
                                                        "past_k": self.k, "past_v": self.v})
        return logits


NEG = np.float32(-3e4)  # additive mask value, finite so fp16 stays well defined


def _embed(lm, tokens: np.ndarray) -> np.ndarray:
    with torch.inference_mode():
        return lm.emb(torch.from_numpy(tokens)).float().numpy()


class CoreMLKV:
    """Stateful Core ML model with a fixed-size fp16 KV cache (convert_static.py)."""

    def __init__(self, lm, size: str, precision: str, units: str) -> None:
        import coremltools as ct
        self.lm = lm
        self.ml = ct.models.MLModel(str(C.OUT / f"muscriptor-{size}-kv-{precision}.mlpackage"),
                                    compute_units=getattr(ct.ComputeUnit, units))

    def first(self, prefix, tokens):
        x = np.concatenate([prefix, _embed(self.lm, tokens)], axis=1).astype(np.float32)
        n = x.shape[1]
        assert n <= S.QMAX
        self.state = self.ml.make_state()
        mask = np.triu(np.full((n, n), NEG, np.float32), 1)[None, None]
        self.length = n
        return self.ml.predict({"x": x, "mask": mask}, state=self.state)["logits"]

    def next(self, token, position):
        self.length += 1
        assert self.length == position + 1 and self.length <= S.LMAX
        x = _embed(self.lm, token)
        return self.ml.predict({"x": x, "mask": np.zeros((1, 1, 1, self.length), np.float32)},
                               state=self.state)["logits"]


class StaticOrt:
    """Static-shape ONNX step graphs (Q=1 decode, Q=64 prefill blocks) with a host-side cache."""

    def __init__(self, lm, size: str, provider: str) -> None:
        import convert_static as CS
        self.lm, self.cs = lm, CS
        self.q1 = P.ort_session(C.OUT / f"muscriptor-{size}-q1.onnx", provider, verbose=True)
        self.qb = P.ort_session(C.OUT / f"muscriptor-{size}-q{CS.PREFILL_BLOCK}.onnx", provider, verbose=True)
        L, H, Dh, _ = CS.dims(lm)
        self.k = np.zeros((L, 1, CS.LMAX, H, Dh), np.float32)
        self.v = np.zeros_like(self.k)

    def _run(self, sess, x, pos, real):
        q = x.shape[1]
        L = self.cs.LMAX
        mask = np.full((1, 1, q, L + q), NEG, np.float32)
        mask[..., :pos] = 0
        mask[0, 0, :, L:] = np.triu(np.full((q, q), NEG, np.float32), 1)
        logits, kn, vn = sess.run(None, {"x": x, "pos": np.array([pos], np.int64), "mask": mask,
                                         "k_cache": self.k, "v_cache": self.v})
        self.k[:, :, pos:pos + real] = kn[:, :, :real]
        self.v[:, :, pos:pos + real] = vn[:, :, :real]
        return logits[:, real - 1]

    def first(self, prefix, tokens):
        x = np.concatenate([prefix, _embed(self.lm, tokens)], axis=1).astype(np.float32)
        n, b = x.shape[1], self.cs.PREFILL_BLOCK
        self.k[:] = 0
        self.v[:] = 0
        for start in range(0, n, b):
            real = min(b, n - start)
            block = np.zeros((1, b, x.shape[2]), np.float32)
            block[:, :real] = x[:, start:start + real]
            logits = self._run(self.qb, block, start, real)
        return logits

    def next(self, token, position):
        return self._run(self.q1, _embed(self.lm, token), position, 1)


class OrtGenerator:
    """Greedy LMModel.generate (beam 1, no CFG, no sampling) on an exported engine."""

    def __init__(self, lm, engine) -> None:
        self.lm, self.engine = lm, engine

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
        for offset in range(start, max_gen_len):
            if early_stop_on_token is not None and (gen == early_stop_on_token).any(axis=1).all():
                break
            if offset == start:
                logits = self.engine.first(prefix, gen[:, :offset + 1])
            else:
                logits = self.engine.next(gen[:, offset:offset + 1], P_len + offset)
            logits = np.array(logits, dtype=np.float32).reshape(B, -1)
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
    lm = tm._model
    if backend == "torch-cpu":
        fn = lm.generate
    elif backend.startswith("onnx-"):  # onnx-ort-<provider>: dynamic graphs
        fn = OrtGenerator(lm, DynamicOrt(lm, size, backend.rsplit("-", 1)[1]))
    elif backend.startswith("static-"):  # static-ort-<provider>
        fn = OrtGenerator(lm, StaticOrt(lm, size, backend.rsplit("-", 1)[1]))
    else:  # coreml-<fp16|fp32>-<units>
        _, precision, units = backend.split("-", 2)
        fn = OrtGenerator(lm, CoreMLKV(lm, size, precision, units))
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
        # Gate: every chunk's token sequence identical to PyTorch (note F1 is reported alongside).
        gate[backend] = all(t["identical_chunks"] == t["chunks"] for t in token_match.values())
        print(backend, json.dumps(results[backend]["note_f1"]), json.dumps(token_match), flush=True)
    benches = {b: P.run_isolated([sys.executable, "-W", "ignore", __file__, "bench", b, size, "30"])
               for b in ["torch-cpu"] + BACKENDS}
    for b, v in benches.items():
        print("bench", b, json.dumps(v), flush=True)
    artifacts = {f.name: {"size_bytes": P.size_bytes(f)} for f in sorted(C.OUT.iterdir()) if f.suffix in (".onnx", ".mlpackage")}
    report = {
        "reference": {"runtime": "PyTorch CPU fp32", "model": f"MuScriptor {size} (HF MuScriptor/muscriptor-{size})",
                      "pipeline": "TranscriptionModel.transcribe_to_midi, greedy, prelude forcing, detect_tempo=False"},
        "graph_boundary": "conditioning (log-mel + projection + class embeddings) on the host; transformer as "
                          "prefill and decode-with-past ONNX graphs; greedy loop on the host",
        "metric": "gate: exact token agreement on every 5 s chunk; also note F1 (50 ms onsets) of the MIDI vs PyTorch",
        "clips": [f"{c.name} [{c.start}s +{c.duration}s]" for c in clips],
        "artifacts": artifacts,
        "parity": results,
        "benchmarks": benches,
        "blocked": BLOCKED,
        "pass": gate,
        "pass_all": all(gate.values()),
        "versions": P.versions("muscriptor", "torch", "onnxruntime", "onnx", "mir_eval"),
        "command": f"cd convert/muscriptor && uv run python convert.py {size} && uv run python convert_static.py {size} "
                   f"&& uv run python parity.py {size}",
    }
    print("wrote", P.write_report("muscriptor", report))


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "bench":
        print(json.dumps(bench(sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "medium",
                               float(sys.argv[4]) if len(sys.argv) > 4 else 30.0)))
    else:
        main(sys.argv[1] if len(sys.argv) > 1 else "medium")
