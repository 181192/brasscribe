"""MuScriptor with a fixed-size KV cache: Core ML (stateful) and static-shape ONNX.

The dynamic prefill/decode graphs in convert.py cannot be compiled by Core ML or the CoreML
execution provider (unbounded sequence axes). Here the cache has a fixed maximum length
LMAX = 2560 positions (the 502-position conditioning prefix plus upstream's max_gen_len of
2000 tokens, rounded up), and attention uses an additive length mask.

Both graphs take embeddings, not token ids: the host looks up the token embedding (or passes
the conditioning prefix) and the graph adds the sinusoidal position embedding.

Core ML (`muscriptor-<size>-kv-{fp16,fp32}.mlpackage`, macOS 15+):
  inputs  x (1, Q, D) with Q in 1..1024, mask (1, 1, Q, E) additive, E = positions so far + Q
  state   k_cache, v_cache (L, 1, LMAX, H, Dh) fp16, updated in place at [E-Q, E)
  output  logits (1, card) at the last query
  Q and E are flexible, so one model does prefill (Q = prefix length) and decode (Q = 1).
  Core ML states must be fp16, so the fp32 build still stores the cache in fp16.

ONNX (`muscriptor-<size>-q{1,64}.onnx`), fully static for ONNX Runtime and its CoreML EP:
  inputs  x (1, Q, D), pos (1,), mask (1, 1, Q, LMAX + Q), k_cache, v_cache (L, 1, LMAX, H, Dh)
  outputs logits (1, Q, card), k_new, v_new (L, 1, Q, H, Dh); the host writes the new rows
  into its cache. Q = 1 for decode, Q = 64 for prefill blocks.

  uv run python convert_static.py [small|medium] [coreml|onnx ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch
from torch import nn
from torch.nn import functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import convert as C  # noqa: E402
from muscriptor.modules.transformer import create_sin_embedding  # noqa: E402

LMAX = 2560
QMAX = 1024
PREFILL_BLOCK = 64


def dims(lm):
    attn = lm.transformer.layers[0].self_attn
    return len(lm.transformer.layers), attn.num_heads, attn.dim_per_head, lm.dim


def _qkv(layer, x):
    attn = layer.self_attn
    b, t, _ = x.shape
    p = F.linear(layer.norm1(x), attn.in_proj_weight).view(b, t, 3, attn.num_heads, attn.dim_per_head)
    return p[:, :, 0], p[:, :, 1], p[:, :, 2]  # (b, t, h, d)


def _attend(q, k, v, mask):
    """q (1,Q,H,Dh), k/v (1,E,H,Dh), mask (1,1,Q,E) additive -> (1,Q,H*Dh)."""
    q, k, v = q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2)
    scores = torch.matmul(q, k.transpose(-1, -2)) * (q.shape[-1] ** -0.5) + mask
    out = torch.matmul(torch.softmax(scores, dim=-1), v)
    return out.transpose(1, 2).reshape(q.shape[0], q.shape[2], -1)


def _block(layer, x, attn_out):
    x = x + layer.self_attn.out_proj(attn_out)
    return x + layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))


class StatefulStep(nn.Module):
    def __init__(self, lm) -> None:
        super().__init__()
        self.lm = lm
        L, H, Dh, _ = dims(lm)
        self.register_buffer("k_cache", torch.zeros(L, 1, LMAX, H, Dh, dtype=torch.float16))
        self.register_buffer("v_cache", torch.zeros(L, 1, LMAX, H, Dh, dtype=torch.float16))

    def forward(self, x, mask):
        lm = self.lm
        q_len, end = x.shape[1], mask.shape[-1]
        begin = end - q_len
        pos = torch.arange(begin, end).view(1, -1, 1)
        x = x + create_sin_embedding(pos, x.shape[-1], max_period=lm.transformer.max_period)
        for i, layer in enumerate(lm.transformer.layers):
            q, k, v = _qkv(layer, x)
            self.k_cache[i:i + 1, :, begin:end] = k.half().unsqueeze(0)
            self.v_cache[i:i + 1, :, begin:end] = v.half().unsqueeze(0)
            keys = self.k_cache[i, :, :end].to(x.dtype)
            values = self.v_cache[i, :, :end].to(x.dtype)
            x = _block(layer, x, _attend(q, keys, values, mask))
        return lm.linear(lm.out_norm(x[:, -1]))


class StaticStep(nn.Module):
    def __init__(self, lm) -> None:
        super().__init__()
        self.lm = lm

    def forward(self, x, pos, mask, k_cache, v_cache):
        lm = self.lm
        q_len = x.shape[1]
        positions = (pos.view(1, 1) + torch.arange(q_len).view(1, -1)).view(1, -1, 1)
        x = x + create_sin_embedding(positions, x.shape[-1], max_period=lm.transformer.max_period)
        ks, vs = [], []
        for i, layer in enumerate(lm.transformer.layers):
            q, k, v = _qkv(layer, x)
            ks.append(k)
            vs.append(v)
            keys = torch.cat([k_cache[i], k], dim=1)
            values = torch.cat([v_cache[i], v], dim=1)
            x = _block(layer, x, _attend(q, keys, values, mask))
        return lm.linear(lm.out_norm(x)), torch.stack(ks), torch.stack(vs)


def export_coreml(size: str) -> None:
    import coremltools as ct
    from common.coreml_ops import register_aliases
    register_aliases()
    lm = C.load(size)._model.eval()
    L, H, Dh, D = dims(lm)
    step = StatefulStep(lm).eval()
    with torch.no_grad():
        traced = torch.jit.trace(step, (torch.randn(1, 8, D), torch.zeros(1, 1, 8, 8)), check_trace=False)
    q = ct.RangeDim(1, QMAX, default=1)
    e = ct.RangeDim(1, LMAX, default=LMAX)
    for precision in ("fp16", "fp32"):
        ml = ct.convert(
            traced,
            inputs=[ct.TensorType("x", shape=(1, q, D), dtype=np.float32),
                    ct.TensorType("mask", shape=(1, 1, q, e), dtype=np.float32)],
            states=[ct.StateType(wrapped_type=ct.TensorType(shape=(L, 1, LMAX, H, Dh), dtype=np.float16), name=n)
                    for n in ("k_cache", "v_cache")],
            outputs=[ct.TensorType("logits", dtype=np.float32)],
            convert_to="mlprogram", minimum_deployment_target=ct.target.macOS15,
            compute_precision=ct.precision.FLOAT16 if precision == "fp16" else ct.precision.FLOAT32)
        path = C.OUT / f"muscriptor-{size}-kv-{precision}.mlpackage"
        ml.save(str(path))
        print("wrote", path)


def export_onnx(size: str) -> None:
    import onnx
    lm = C.load(size)._model.eval()
    L, H, Dh, D = dims(lm)
    step = StaticStep(lm).eval()
    for q in (1, PREFILL_BLOCK):
        args = (torch.randn(1, q, D), torch.tensor([10]), torch.zeros(1, 1, q, LMAX + q),
                torch.zeros(L, 1, LMAX, H, Dh), torch.zeros(L, 1, LMAX, H, Dh))
        path = C.OUT / f"muscriptor-{size}-q{q}.onnx"
        with torch.no_grad():
            torch.onnx.export(step, args, str(path), input_names=["x", "pos", "mask", "k_cache", "v_cache"],
                              output_names=["logits", "k_new", "v_new"], opset_version=17, dynamo=False)
        m = onnx.load(str(path))
        onnx.save(m, str(path), save_as_external_data=True, all_tensors_to_one_file=True, location=path.name + ".data")
        print("wrote", path)


if __name__ == "__main__":
    size = sys.argv[1] if len(sys.argv) > 1 else "medium"
    for what in sys.argv[2:] or ["coreml", "onnx"]:
        {"coreml": export_coreml, "onnx": export_onnx}[what](size)
