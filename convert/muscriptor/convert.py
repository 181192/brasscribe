"""MuScriptor: decoder-only transformer -> ONNX prefill + decode-with-past graphs.

MuScriptor is a causal LM whose "encoder" is its conditioning prefix: a log-mel projection of
each 5 s chunk (500 frames) plus two class embeddings (instrument group, dataset), prepended to
the token sequence. The transformer is what costs; the conditioning stays on the host.

- prefill: cond (1, P, D) + tokens (1, T0) -> logits at the last position (1, card),
  present_k / present_v (L, 1, P+T0, H, Dh). Causal attention over the whole prefix.
- decode:  token (1, 1) + position (1,) + past_k / past_v (L, 1, Tp, H, Dh) -> logits,
  present_k / present_v with Tp+1 (the new key/value is appended).

Both graphs have dynamic sequence axes and share weights (stored twice, external data).
The host runs greedy decoding exactly as LMModel.generate does (initial token, prompt
teacher forcing, logits[:, 1393:] = -inf, forbidden tokens, early stop).

  uv run python convert.py [small|medium]
"""

from __future__ import annotations

import sys
from pathlib import Path

import torch
from torch import nn
from torch.nn import functional as F

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import CONVERTED  # noqa: E402

from muscriptor.modules.transformer import create_sin_embedding  # noqa: E402

OUT = CONVERTED / "muscriptor"


def load(size: str = "medium"):
    from muscriptor.transcription_model import TranscriptionModel
    return TranscriptionModel.load_model(size, device="cpu", dtype="float32")


def _qkv(layer, x):
    attn = layer.self_attn
    projected = F.linear(layer.norm1(x), attn.in_proj_weight)
    b, t, _ = projected.shape
    packed = projected.view(b, t, 3, attn.num_heads, attn.dim_per_head)
    return packed[:, :, 0], packed[:, :, 1], packed[:, :, 2]  # (b, t, h, d)


def _finish(layer, x, attn_out):
    b, h, t, d = attn_out.shape
    out = layer.self_attn.out_proj(attn_out.transpose(1, 2).reshape(b, t, h * d))
    x = x + out
    return x + layer.linear2(F.gelu(layer.linear1(layer.norm2(x))))


def _positions(start, length: int, device):
    return (torch.arange(length, device=device).view(1, -1, 1) + start.view(-1, 1, 1))


class Prefill(nn.Module):
    def __init__(self, lm) -> None:
        super().__init__()
        self.lm = lm

    def forward(self, cond, tokens):
        lm = self.lm
        x = torch.cat([cond, lm.emb(tokens)], dim=1)
        b, t, c = x.shape
        pos = _positions(torch.zeros(1, dtype=torch.long), t, x.device)
        x = x + create_sin_embedding(pos, c, max_period=lm.transformer.max_period)
        ks, vs = [], []
        for layer in lm.transformer.layers:
            q, k, v = _qkv(layer, x)
            ks.append(k)
            vs.append(v)
            a = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2), is_causal=True)
            x = _finish(layer, x, a)
        x = lm.out_norm(x[:, -1:])
        return lm.linear(x)[:, 0], torch.stack(ks), torch.stack(vs)


class Decode(nn.Module):
    def __init__(self, lm) -> None:
        super().__init__()
        self.lm = lm

    def forward(self, token, position, past_k, past_v):
        lm = self.lm
        x = lm.emb(token)
        c = x.shape[-1]
        x = x + create_sin_embedding(_positions(position, 1, x.device), c, max_period=lm.transformer.max_period)
        ks, vs = [], []
        for i, layer in enumerate(lm.transformer.layers):
            q, k, v = _qkv(layer, x)
            k = torch.cat([past_k[i], k], dim=1)
            v = torch.cat([past_v[i], v], dim=1)
            ks.append(k)
            vs.append(v)
            a = F.scaled_dot_product_attention(q.transpose(1, 2), k.transpose(1, 2), v.transpose(1, 2))
            x = _finish(layer, x, a)
        return lm.linear(lm.out_norm(x))[:, 0], torch.stack(ks), torch.stack(vs)


def main(size: str) -> None:
    import onnx
    OUT.mkdir(parents=True, exist_ok=True)
    tm = load(size)
    lm = tm._model.eval()
    L = len(lm.transformer.layers)
    attn = lm.transformer.layers[0].self_attn
    H, Dh, D = attn.num_heads, attn.dim_per_head, lm.dim
    cond = torch.randn(1, 502, D)
    tokens = torch.tensor([[lm.initial_token_id, 5, 7]])
    past = torch.randn(L, 1, 505, H, Dh)
    with torch.no_grad():
        for name, module, args, inputs, outputs, axes in [
            ("prefill", Prefill(lm), (cond, tokens), ["cond", "tokens"], ["logits", "present_k", "present_v"],
             {"cond": {1: "prefix"}, "tokens": {1: "steps"}, "present_k": {2: "total"}, "present_v": {2: "total"}}),
            ("decode", Decode(lm), (tokens[:, :1], torch.tensor([505]), past, past),
             ["token", "position", "past_k", "past_v"], ["logits", "present_k", "present_v"],
             {"past_k": {2: "past"}, "past_v": {2: "past"}, "present_k": {2: "total"}, "present_v": {2: "total"}}),
        ]:
            path = OUT / f"muscriptor-{size}-{name}.onnx"
            torch.onnx.export(module.eval(), args, str(path), input_names=inputs, output_names=outputs,
                              dynamic_axes=axes, opset_version=17, dynamo=False)
            m = onnx.load(str(path))
            onnx.save(m, str(path), save_as_external_data=True, all_tensors_to_one_file=True,
                      location=path.name + ".data")
            print("wrote", path)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "medium")
