"""Beat This!: PyTorch checkpoint -> ONNX and Core ML ML Program.

Only the network is exported. Its input is the log-mel spectrogram (frames x 128) that
`beat_this.preprocessing.LogMelSpect` computes, and its outputs are per-frame beat and
downbeat logits; chunking, aggregation and peak picking stay in the host code, as upstream.

- ONNX: time axis dynamic (upstream runs 1500-frame chunks, and one shorter chunk for
  pieces under 30 s), plus a fixed 1500-frame copy for the CoreML execution provider.
- Core ML: fixed 1500-frame chunk, fp32 and fp16.

  uv run python convert.py [small0|final0 ...]
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import CONVERTED  # noqa: E402

from beat_this.inference import load_checkpoint, load_model  # noqa: E402

OUT = CONVERTED / "beat-this"
CHUNK = 1500
N_MELS = 128


def _outer_einsum(equation: str, *operands):
    """The rotary embedding's '..., f -> ... f' outer product as a broadcast multiply.

    coremltools' einsum lowering fails on it (rank-1 transpose); the result is identical.
    """
    if equation.replace(" ", "") == "...,f->...f":
        a, b = operands
        return a[..., None] * b
    return torch.einsum(equation, *operands)


class Logits(torch.nn.Module):
    """BeatThis as an export-friendly graph returning (beat, downbeat) logits.

    Same computation as BeatThis.forward with its SumHead, minus the autocast guard around
    the final sum (it only matters under autocast). The rotary embedding cache is turned off:
    it would freeze one sequence length into the graph.
    """

    def __init__(self, model: torch.nn.Module) -> None:
        super().__init__()
        import rotary_embedding_torch.rotary_embedding_torch as rot
        from rotary_embedding_torch import RotaryEmbedding
        rot.einsum = _outer_einsum
        self.model = model
        for mod in model.modules():
            if isinstance(mod, RotaryEmbedding):
                mod.cache_if_possible = False

    def forward(self, spect):
        x = self.model.transformer_blocks(self.model.frontend(spect))
        head = self.model.task_heads
        bd = head.beat_downbeat_lin(x)
        beat, downbeat = bd[..., 0], bd[..., 1]
        if type(head).__name__ == "SumHead":
            beat = beat + downbeat
        return beat, downbeat


def checkpoint_path(name: str) -> Path:
    load_checkpoint(name)  # downloads into the torch hub cache on first use
    return Path(torch.hub.get_dir()) / "checkpoints" / f"beat_this-{name}.ckpt"


def export(name: str) -> None:
    import coremltools as ct
    from common.coreml_ops import register_aliases
    register_aliases()
    OUT.mkdir(parents=True, exist_ok=True)
    model = Logits(load_model(name, "cpu")).eval()
    x = torch.randn(1, CHUNK, N_MELS)
    onnx_path = OUT / f"beat-this-{name}.onnx"
    with torch.no_grad():
        torch.onnx.export(model, (x,), str(onnx_path), input_names=["spect"], output_names=["beat", "downbeat"],
                          dynamic_axes={"spect": {1: "frames"}, "beat": {1: "frames"}, "downbeat": {1: "frames"}},
                          opset_version=17, dynamo=False)
    print("wrote", onnx_path)
    # A fixed 1500-frame copy: the CoreML execution provider only compiles static shapes.
    import onnx
    from onnxruntime.tools.onnx_model_utils import make_dim_param_fixed
    static = onnx.load(str(onnx_path))
    make_dim_param_fixed(static.graph, "frames", CHUNK)
    static_path = OUT / f"beat-this-{name}-{CHUNK}.onnx"
    onnx.save(static, str(static_path))
    print("wrote", static_path)
    with torch.no_grad():
        traced = torch.jit.trace(model, (x,))
    for precision in ("fp32", "fp16"):
        ml = ct.convert(traced, inputs=[ct.TensorType("spect", shape=(1, CHUNK, N_MELS), dtype=np.float32)],
                        outputs=[ct.TensorType("beat"), ct.TensorType("downbeat")], convert_to="mlprogram",
                        minimum_deployment_target=ct.target.macOS14,
                        compute_precision=ct.precision.FLOAT32 if precision == "fp32" else ct.precision.FLOAT16)
        ml.short_description = f"Beat This! {name}: log-mel (1500 x 128) -> beat/downbeat logits"
        path = OUT / f"beat-this-{name}-{precision}.mlpackage"
        ml.save(str(path))
        print("wrote", path)


if __name__ == "__main__":
    for n in sys.argv[1:] or ["small0", "final0"]:
        export(n)
