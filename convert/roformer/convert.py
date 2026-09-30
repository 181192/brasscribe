"""BS-RoFormer separators (BS-RoFormer SW 6-stem, Mega-53): PyTorch -> ONNX (and Core ML).

Both use the MSST `BSRoformer` class (pinned MSST checkout of the Mega-53 adapter, read-only).
The exported core is BSRoformer.forward between the STFT and the complex mask:

  input  x    (1, T, F*2*2)   STFT of one stereo chunk, 'b t (f s c)' as in forward()
  output mask (1, N, F*2, T, 2) per-stem complex mask, real/imag last

The host computes the STFT, multiplies by the mask as complex numbers, zeroes DC and runs the
iSTFT; ONNX and Core ML have no complex tensors, which is the known way these models are
exported (the public SW ONNX port does the same).

Formats per model: ONNX fp32 and fp16 (external data, the graphs exceed 2 GB protobuf limits
for Mega-53) and, where it converts, Core ML ML Program fp16.

  uv run python convert.py sw|mega53 [--coreml] [--skip-onnx]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import ADAPTERS, CONVERTED, MODELS  # noqa: E402

MSST = ADAPTERS / "mega53" / "msst"
sys.path.insert(0, str(MSST))

SPECS = {
    "sw": {"config": MODELS / "separator" / "BS-Roformer-SW.yaml", "ckpt": MODELS / "separator" / "BS-Roformer-SW.ckpt",
           "name": "bs-roformer-sw"},
    "mega53": {"config": MODELS / "mega53" / "mvsep_mega_model_bs_roformer_53_stems.yaml",
               "ckpt": MODELS / "mega53" / "mvsep_mega_model_bs_roformer_53_stems_v1.ckpt", "name": "mega53"},
}


def out_dir(key: str) -> Path:
    return CONVERTED / SPECS[key]["name"]


def load(key: str):
    from utils.settings import get_model_from_config
    model, config = get_model_from_config("bs_roformer", str(SPECS[key]["config"]))
    state = torch.load(str(SPECS[key]["ckpt"]), map_location="cpu", weights_only=False)
    state = state.get("state_dict", state) if isinstance(state, dict) else state
    model.load_state_dict(state)
    return model.eval(), config


def chunk_size(config) -> int:
    return config.inference.chunk_size if "chunk_size" in config.inference else config.audio.chunk_size


def _outer_einsum(equation: str, *operands):
    if equation.replace(" ", "") == "...,f->...f":
        a, b = operands
        return a[..., None] * b
    return torch.einsum(equation, *operands)


class Core(torch.nn.Module):
    """BSRoformer.forward from the band split to the stacked masks (eval, no skip/checkpointing)."""

    def __init__(self, model) -> None:
        super().__init__()
        import rotary_embedding_torch.rotary_embedding_torch as rot
        from rotary_embedding_torch import RotaryEmbedding
        rot.einsum = _outer_einsum  # coremltools cannot lower the rotary outer-product einsum
        for mod in model.modules():
            if isinstance(mod, RotaryEmbedding):
                mod.cache_if_possible = False  # the cache would freeze a sequence length into the graph
        assert not model.skip_connection and not model.use_torch_checkpoint
        self.m = model

    def forward(self, x):
        m = self.m
        x = m.band_split(x)
        b, t, f, d = x.shape
        for block in m.layers:
            if len(block) == 3:
                linear, time_t, freq_t = block
                x = linear(x.reshape(b, t * f, d)).reshape(b, t, f, d)
            else:
                time_t, freq_t = block
            x = x.permute(0, 2, 1, 3).reshape(b * f, t, d)
            x = time_t(x)
            x = x.reshape(b, f, t, d).permute(0, 2, 1, 3).reshape(b * t, f, d)
            x = freq_t(x)
            x = x.reshape(b, t, f, d)
        x = m.final_norm(x)
        mask = torch.stack([fn(x) for fn in m.mask_estimators], dim=1)
        n = mask.shape[1]
        return mask.reshape(b, n, t, -1, 2).permute(0, 1, 3, 2, 4)


def stft_features(model, audio: torch.Tensor):
    """Host side of forward(): (1, 2, L) -> (x for the core, stft_repr as (1, F*2, T, 2))."""
    b, s, L = audio.shape
    window = model.stft_window_fn(device=audio.device)
    spec = torch.stft(audio.reshape(b * s, L), **model.stft_kwargs, window=window, return_complex=True)
    spec = torch.view_as_real(spec).reshape(b, s, spec.shape[-2], spec.shape[-1], 2)  # b s f t c
    spec = spec.permute(0, 2, 1, 3, 4).reshape(b, -1, spec.shape[3], 2)  # b (f s) t c
    x = spec.permute(0, 2, 1, 3).reshape(b, spec.shape[2], -1)  # b t (f c)
    return x, spec


def reconstruct(model, spec: torch.Tensor, mask: torch.Tensor, length: int) -> torch.Tensor:
    """Host side after the core: complex mask, DC zeroing, iSTFT -> (1, N, 2, L)."""
    b, n = mask.shape[:2]
    s = model.audio_channels
    z = torch.view_as_complex(spec[:, None].contiguous()) * torch.view_as_complex(mask.contiguous())
    z = z.reshape(b, n, -1, s, z.shape[-1]).permute(0, 1, 3, 2, 4).reshape(b * n * s, -1, z.shape[-1])
    if model.zero_dc:
        z[:, 0] = 0.0
    window = model.stft_window_fn(device=spec.device)
    audio = torch.istft(z, **model.stft_kwargs, window=window, return_complex=False, length=length)
    return audio.reshape(b, n, s, -1)


def split_forward(model, core_run, audio: torch.Tensor) -> torch.Tensor:
    x, spec = stft_features(model, audio)
    return reconstruct(model, spec, core_run(x), audio.shape[-1])


def export(key: str, coreml: bool, onnx_export: bool = True) -> None:
    out = out_dir(key)
    out.mkdir(parents=True, exist_ok=True)
    model, config = load(key)
    core = Core(model).eval()
    L = chunk_size(config)
    audio = torch.randn(1, 2, L) * 0.1
    x, _ = stft_features(model, audio)
    print(key, "chunk", L, "x", tuple(x.shape))
    fp32 = out / f"{SPECS[key]['name']}-core-fp32.onnx"
    if onnx_export:
        _export_onnx(core, x, fp32)
    if coreml:
        _export_coreml(core, x, out / f"{SPECS[key]['name']}-core-fp16.mlpackage")


def _export_onnx(core, x, fp32: Path) -> None:
    import shutil
    import onnx
    if not (fp32.exists() and fp32.with_name(fp32.name + ".data").exists()):
        # Graphs over 2 GB are written with one file per tensor; export into a scratch
        # directory, then consolidate into a single external-data file.
        tmp = fp32.parent / "export-tmp"
        tmp.mkdir(exist_ok=True)
        with torch.no_grad():
            torch.onnx.export(core, (x,), str(tmp / fp32.name), input_names=["x"], output_names=["mask"],
                              opset_version=17, dynamo=False)
        m = onnx.load(str(tmp / fp32.name))
        onnx.save(m, str(fp32), save_as_external_data=True, all_tensors_to_one_file=True, location=fp32.name + ".data")
        shutil.rmtree(tmp)
        print("wrote", fp32)
    from onnxruntime.transformers.float16 import convert_float_to_float16
    # Shape inference serialises the whole model, which fails above 2 GB; the export has shapes already.
    m16 = convert_float_to_float16(onnx.load(str(fp32)), keep_io_types=True, disable_shape_infer=True)
    fp16 = fp32.with_name(fp32.name.replace("-fp32", "-fp16"))
    onnx.save(m16, str(fp16), save_as_external_data=True, all_tensors_to_one_file=True, location=fp16.name + ".data")
    print("wrote", fp16)


def _export_coreml(core, x, path: Path) -> None:
    import coremltools as ct
    from common.coreml_ops import register_aliases
    register_aliases()
    with torch.no_grad():
        traced = torch.jit.trace(core, (x,), check_trace=False)
    ml = ct.convert(traced, inputs=[ct.TensorType("x", shape=tuple(x.shape), dtype=np.float32)],
                    outputs=[ct.TensorType("mask")], convert_to="mlprogram",
                    minimum_deployment_target=ct.target.macOS14, compute_precision=ct.precision.FLOAT16)
    ml.save(str(path))
    print("wrote", path)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("model", choices=list(SPECS))
    ap.add_argument("--coreml", action="store_true", help="also build the Core ML fp16 package")
    ap.add_argument("--skip-onnx", action="store_true")
    args = ap.parse_args()
    export(args.model, args.coreml, not args.skip_onnx)
