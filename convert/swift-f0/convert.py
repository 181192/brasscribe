"""SwiftF0: upstream ONNX -> static-shape ONNX -> PyTorch (onnx2torch) -> Core ML ML Program.

The upstream ONNX model computes its spectrogram in-graph with a matmul DFT and has a dynamic
audio length. Core ML (and the Neural Engine) want static shapes, so the graph is first
simplified at a fixed length, which constant-folds every shape computation. Two lengths:

- window: one upstream `detect` window (11 + 1875 + 10 frames of 256 samples, 30.3 s);
  offline detection pads the last window with zeros.
- stream: 128 frames (2.05 s), enough for 1 s pushes plus the 11 left and 10 lookahead frames
  a streamed frame needs.

fmin/fmax stay graph inputs. The static ONNX files are kept too: they are what ONNX Runtime
Mobile and the CoreML execution provider run.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import onnx
from onnx import helper, numpy_helper

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import CONVERTED  # noqa: E402

import swift_f0  # noqa: E402
from swift_f0.core import HOP, LEFT_FRAMES, LOOKAHEAD_FRAMES, WINDOW_FRAMES  # noqa: E402

UPSTREAM = Path(swift_f0.__file__).parent / "model.onnx"
OUT = CONVERTED / "swift-f0"
LENGTHS = {
    "window": (LEFT_FRAMES + WINDOW_FRAMES + LOOKAHEAD_FRAMES) * HOP,
    "stream": 128 * HOP,
}


def static_onnx(samples: int) -> onnx.ModelProto:
    import onnxsim
    model, ok = onnxsim.simplify(onnx.load(str(UPSTREAM)), overwrite_input_shapes={"audio": [1, samples]})
    assert ok, "onnxsim could not validate the simplified model"
    return model


def opset13(model: onnx.ModelProto) -> onnx.ModelProto:
    """Rewrite the few opset-18 forms onnx2torch lacks into their opset-13 equivalents."""
    model = onnx.ModelProto.FromString(model.SerializeToString())
    init = {i.name: numpy_helper.to_array(i) for i in model.graph.initializer}
    for node in model.graph.node:
        if node.op_type in ("ReduceMax", "ReduceMean") and len(node.input) == 2:
            axes = init[node.input[1]].tolist()
            del node.input[1]
            keep = [a for a in node.attribute if a.name == "keepdims"]
            del node.attribute[:]
            node.attribute.extend(keep + [helper.make_attribute("axes", axes)])
        # Pad-18 only adds an optional axes input, unused here.
    # The pitch read-out runs a softmax in float64; Core ML has no float64, so it runs in float32.
    for node in model.graph.node:
        if node.op_type == "Cast":
            for a in node.attribute:
                if a.name == "to" and a.i == onnx.TensorProto.DOUBLE:
                    a.i = onnx.TensorProto.FLOAT
    for i, t in enumerate(model.graph.initializer):
        if t.data_type == onnx.TensorProto.DOUBLE:
            model.graph.initializer[i].CopyFrom(numpy_helper.from_array(numpy_helper.to_array(t).astype(np.float32), t.name))
    # onnx2torch clamps integer Clip inputs to float; cast the index back to int64 before Gather.
    nodes = list(model.graph.node)
    for node in nodes:
        if node.op_type == "Clip" and node.input[1] in init and init[node.input[1]].dtype == np.int64:
            out = node.output[0]
            node.output[0] = out + "_f"
            idx = list(model.graph.node).index(node)
            model.graph.node.insert(idx + 1, helper.make_node("Cast", [out + "_f"], [out], to=onnx.TensorProto.INT64))
    model.opset_import[0].version = 13
    onnx.checker.check_model(model)
    return model


def torch_model(samples: int):
    from onnx2torch import convert
    return convert(opset13(static_onnx(samples))).eval()


def main() -> None:
    import coremltools as ct
    import torch

    class Wrapped(torch.nn.Module):
        """Takes fmin/fmax as shape-(1,) tensors, which Core ML inputs need."""

        def __init__(self, inner: torch.nn.Module) -> None:
            super().__init__()
            self.inner = inner
            for p in self.parameters():
                p.requires_grad_(False)

        def forward(self, audio, fmin, fmax):
            return self.inner(audio, fmin[0], fmax[0])

    from common.coreml_ops import register_aliases
    register_aliases()
    OUT.mkdir(parents=True, exist_ok=True)
    for name, samples in LENGTHS.items():
        onnx.save(static_onnx(samples), str(OUT / f"swift-f0-{name}.onnx"))
        model = Wrapped(torch_model(samples)).eval()
        audio = torch.zeros(1, samples)
        with torch.no_grad():
            traced = torch.jit.trace(model, (audio, torch.ones(1), torch.ones(1)), check_trace=False)
        inputs = [ct.TensorType("audio", shape=(1, samples), dtype=np.float32),
                  ct.TensorType("fmin", shape=(1,), dtype=np.float32),
                  ct.TensorType("fmax", shape=(1,), dtype=np.float32)]
        for precision in ("fp32", "fp16"):
            ml = ct.convert(traced, inputs=inputs, outputs=[ct.TensorType("pitch"), ct.TensorType("confidence")],
                            convert_to="mlprogram", minimum_deployment_target=ct.target.macOS14,
                            compute_precision=ct.precision.FLOAT32 if precision == "fp32" else ct.precision.FLOAT16)
            ml.short_description = f"SwiftF0 pitch detector, {samples} samples at 16 kHz (from the upstream ONNX)"
            path = OUT / f"swift-f0-{name}-{precision}.mlpackage"
            ml.save(str(path))
            print("wrote", path)


if __name__ == "__main__":
    main()
