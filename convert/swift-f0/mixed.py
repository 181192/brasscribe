"""SwiftF0 mixed-precision Core ML build for the Neural Engine: three chained models.

The fp16 build fails on the Neural Engine: the in-graph matmul-DFT spectrogram and the pitch
read-out lose too much precision. Marking those ops fp32 inside one model does not help, since
Core ML still places them on the Neural Engine, which computes in fp16. So the graph is cut
into three Core ML models the host chains:

  front  audio -> spectrogram features            fp32  (CPU/GPU)
  trunk  2-D conv stack                            fp16  (Neural Engine)
  head   pitch/confidence read-out, fmin/fmax      fp32  (CPU/GPU)

The cut is made on the static ONNX graph (first to last 2-D Conv is the trunk); each piece
goes through the same onnx2torch -> coremltools path as convert.py.

  uv run python mixed.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import onnx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import convert as C  # noqa: E402

PARTS = ("front", "trunk", "head")


def _split(model: onnx.ModelProto) -> dict[str, tuple[list[str], list[str]]]:
    """Input/output tensor names of the three pieces."""
    nodes = list(model.graph.node)
    init = {i.name for i in model.graph.initializer}
    conv2d = [i for i, n in enumerate(nodes)
              if n.op_type == "Conv" and len(next(a for a in n.attribute if a.name == "kernel_shape").ints) == 2]
    ranges = {"front": (0, conv2d[0]), "trunk": (conv2d[0], conv2d[-1] + 1), "head": (conv2d[-1] + 1, len(nodes))}
    graph_in = [i.name for i in model.graph.input]
    graph_out = [o.name for o in model.graph.output]
    out = {}
    for part, (a, b) in ranges.items():
        inside = nodes[a:b]
        produced = {t for n in inside for t in n.output}
        before = {t for n in nodes[:a] for t in n.output} | set(graph_in)
        after_consumed = {t for n in nodes[b:] for t in n.input} | set(graph_out)
        inputs = sorted({t for n in inside for t in n.input if t and t not in produced and t not in init and t in before})
        outputs = sorted(t for t in produced if t in after_consumed)
        out[part] = (inputs, outputs)
    return out


def pieces(samples: int) -> tuple[dict[str, onnx.ModelProto], dict]:
    from onnx.utils import Extractor
    full = C.opset13(C.static_onnx(samples))
    full = onnx.shape_inference.infer_shapes(full)
    io = _split(full)
    ex = Extractor(full)
    return {p: ex.extract_model(*io[p]) for p in PARTS}, io


def main() -> None:
    import coremltools as ct
    import torch
    from onnx2torch import convert as to_torch
    from common.coreml_ops import register_aliases
    register_aliases()
    for name, samples in C.LENGTHS.items():
        models, io = pieces(samples)
        for part in PARTS:
            m = models[part]
            shapes = {vi.name: [d.dim_value for d in vi.type.tensor_type.shape.dim]
                      for vi in list(m.graph.input)}
            dtypes = {vi.name: vi.type.tensor_type.elem_type for vi in m.graph.input}
            tm = to_torch(m).eval()
            for p in tm.parameters():
                p.requires_grad_(False)
            names = io[part][0]
            # Scalars (fmin/fmax) become shape-(1,) inputs, as in convert.py.
            scalar = [n for n in names if not shapes[n]]

            class Piece(torch.nn.Module):
                def __init__(self, inner):
                    super().__init__()
                    self.inner = inner

                def forward(self, *args):
                    args = [a[0] if n in scalar else a for n, a in zip(names, args)]
                    return self.inner(*args)

            example = tuple(torch.zeros(shapes[n] or [1], dtype=torch.float32 if dtypes[n] == 1 else torch.int64)
                            for n in names)
            with torch.no_grad():
                traced = torch.jit.trace(Piece(tm).eval(), example, check_trace=False)
            precision = ct.precision.FLOAT16 if part == "trunk" else ct.precision.FLOAT32
            ml = ct.convert(traced, inputs=[ct.TensorType(f"in{i}", shape=tuple(e.shape),
                                                          dtype=np.float32 if e.dtype == torch.float32 else np.int32)
                                            for i, e in enumerate(example)],
                            outputs=[ct.TensorType(f"out{i}") for i in range(len(io[part][1]))],
                            convert_to="mlprogram", minimum_deployment_target=ct.target.macOS14,
                            compute_precision=precision)
            ml.user_defined_metadata["onnx_inputs"] = ",".join(names)
            ml.user_defined_metadata["onnx_outputs"] = ",".join(io[part][1])
            path = C.OUT / f"swift-f0-{name}-mixed-{part}.mlpackage"
            ml.save(str(path))
            print("wrote", path, names, "->", io[part][1])


if __name__ == "__main__":
    main()
