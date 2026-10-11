"""Basic Pitch: batch-1 copies of the upstream exports for GPU/Neural Engine use.

The upstream nmp.onnx and nmp.mlpackage have a dynamic batch dimension. The CoreML execution
provider cannot compile that ONNX (ML Program conv ops lose their 'pad' parameter), and Core ML
refuses the unbounded dimension on GPU/Neural Engine (E5RT), falling back to CPU. `predict()`
feeds one window at a time anyway, so:

- nmp-b1.onnx: the upstream ONNX with batch fixed to 1, explicit zero Conv padding and all
  shapes inferred.
- nmp-b1-{fp32,fp16}.mlpackage: the TensorFlow SavedModel converted with coremltools at
  input shape (1, 43844, 1), keeping the upstream input/output names.
"""

from __future__ import annotations

import sys
from pathlib import Path

import onnx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import CONVERTED  # noqa: E402

import basic_pitch  # noqa: E402

UPSTREAM = Path(basic_pitch.__file__).parent / "saved_models" / "icassp_2022" / "nmp.onnx"
OUT = CONVERTED / "basic-pitch"
STATIC = OUT / "nmp-b1.onnx"


def main() -> None:
    from onnxruntime.tools.onnx_model_utils import make_dim_param_fixed, make_input_shape_fixed
    from onnxruntime.tools.symbolic_shape_infer import SymbolicShapeInference
    OUT.mkdir(parents=True, exist_ok=True)
    model = onnx.load(str(UPSTREAM))
    inp = model.graph.input[0]
    dims = inp.type.tensor_type.shape.dim
    shape = [1] + [d.dim_value for d in dims[1:]]
    for d in dims:
        if d.dim_param:
            make_dim_param_fixed(model.graph, d.dim_param, 1)
    make_input_shape_fixed(model.graph, inp.name, shape)
    for o in model.graph.output:
        for d in o.type.tensor_type.shape.dim:
            if d.dim_param or d.dim_value == 0:
                d.Clear()
    # The CoreML EP's ML Program builder drops Conv nodes that rely on the default (zero)
    # padding without a 'pads' attribute; spell the default out.
    for node in model.graph.node:
        if node.op_type == "Conv" and not any(a.name in ("pads", "auto_pad") for a in node.attribute):
            kernel = next(a for a in node.attribute if a.name == "kernel_shape").ints
            node.attribute.append(onnx.helper.make_attribute("pads", [0] * (2 * len(kernel))))
    model = SymbolicShapeInference.infer_shapes(model, auto_merge=True)
    onnx.checker.check_model(model)
    onnx.save(model, str(STATIC))
    print("wrote", STATIC, shape)

    import coremltools as ct
    saved = UPSTREAM.parent / "nmp"
    for precision in ("fp32", "fp16"):
        ml = ct.convert(str(saved), source="tensorflow", inputs=[ct.TensorType(name="input_2", shape=tuple(shape))],
                        convert_to="mlprogram", minimum_deployment_target=ct.target.macOS14,
                        compute_precision=ct.precision.FLOAT32 if precision == "fp32" else ct.precision.FLOAT16)
        path = OUT / f"nmp-b1-{precision}.mlpackage"
        ml.save(str(path))
        print("wrote", path)


if __name__ == "__main__":
    main()
