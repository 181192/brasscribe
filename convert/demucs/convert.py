"""HT-Demucs (4 stems): PyTorch -> ONNX and Core ML, with the STFT/iSTFT outside the graph.

The exported core takes one training-length segment (7.8 s at 44.1 kHz, 343980 samples):
the stereo waveform and its complex-as-channels spectrogram magnitude (1, 4, 2048, 336),
and returns the frequency-branch spectrogram (1, 4 sources, 4, 2048, 336) and the time-branch
waveform (1, 4, 2, 343980), both de-normalised. The host computes the STFT, applies the
spectrogram as a complex mask, runs the iSTFT and adds the two branches; that is
`HTDemucs.forward` split at its complex-number boundaries (`_spec`/`_magnitude` and
`_mask`/`_ispec`), which ONNX and Core ML cannot represent.

  uv run python convert.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import torch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from common.parity import CONVERTED  # noqa: E402

OUT = CONVERTED / "htdemucs"
NAME = "htdemucs"


def load():
    from demucs.pretrained import get_model
    bag = get_model(NAME)
    model = bag.models[0] if hasattr(bag, "models") else bag
    return model.eval()


def segment_length(model) -> int:
    return int(model.segment * model.samplerate)


class Core(torch.nn.Module):
    """HTDemucs.forward between the spectrogram and the complex mask (eval, full segment)."""

    def __init__(self, model) -> None:
        super().__init__()
        self.m = model

    def forward(self, mix, mag):
        m = self.m
        x = mag
        B, C, Fq, T = x.shape
        mean = x.mean(dim=(1, 2, 3), keepdim=True)
        std = x.std(dim=(1, 2, 3), keepdim=True)
        x = (x - mean) / (1e-5 + std)
        xt = mix
        meant = xt.mean(dim=(1, 2), keepdim=True)
        stdt = xt.std(dim=(1, 2), keepdim=True)
        xt = (xt - meant) / (1e-5 + stdt)

        saved, saved_t, lengths, lengths_t = [], [], [], []
        for idx, encode in enumerate(m.encoder):
            lengths.append(x.shape[-1])
            inject = None
            if idx < len(m.tencoder):
                lengths_t.append(xt.shape[-1])
                tenc = m.tencoder[idx]
                xt = tenc(xt)
                if not tenc.empty:
                    saved_t.append(xt)
                else:
                    inject = xt
            x = encode(x, inject)
            if idx == 0 and m.freq_emb is not None:
                frs = torch.arange(x.shape[-2], device=x.device)
                emb = m.freq_emb(frs).t()[None, :, :, None].expand_as(x)
                x = x + m.freq_emb_scale * emb
            saved.append(x)
        if m.crosstransformer:
            if m.bottom_channels:
                b, c, f, t = x.shape
                x = x.reshape(b, c, f * t)
                x = m.channel_upsampler(x)
                x = x.reshape(b, -1, f, t)
                xt = m.channel_upsampler_t(xt)
            x, xt = m.crosstransformer(x, xt)
            if m.bottom_channels:
                x = x.reshape(b, -1, f * t)
                x = m.channel_downsampler(x)
                x = x.reshape(b, -1, f, t)
                xt = m.channel_downsampler_t(xt)
        for idx, decode in enumerate(m.decoder):
            skip = saved.pop(-1)
            x, pre = decode(x, skip, lengths.pop(-1))
            offset = m.depth - len(m.tdecoder)
            if idx >= offset:
                tdec = m.tdecoder[idx - offset]
                length_t = lengths_t.pop(-1)
                if tdec.empty:
                    pre = pre[:, :, 0]
                    xt, _ = tdec(pre, None, length_t)
                else:
                    skip = saved_t.pop(-1)
                    xt, _ = tdec(xt, skip, length_t)
        S = len(m.sources)
        x = x.view(B, S, -1, Fq, T)
        x = x * std[:, None] + mean[:, None]
        xt = xt.view(B, S, -1, mix.shape[-1])
        xt = xt * stdt[:, None] + meant[:, None]
        return x, xt


def split_forward(model, core_run, mix: torch.Tensor) -> torch.Tensor:
    """HTDemucs.forward for one segment with the core swapped for `core_run(mix, mag)`."""
    length = mix.shape[-1]
    training_length = segment_length(model)
    pre_pad = None
    if length < training_length:
        pre_pad = length
        mix = torch.nn.functional.pad(mix, (0, training_length - length))
    z = model._spec(mix)
    mag = model._magnitude(z)
    x, xt = core_run(mix, mag)
    zout = model._mask(z, x)
    out = xt + model._ispec(zout, training_length)
    return out[..., :pre_pad] if pre_pad else out


def main() -> None:
    import coremltools as ct
    from common.coreml_ops import register_aliases
    register_aliases()
    # The fused inference path of nn.MultiheadAttention has no ONNX/Core ML lowering.
    torch.backends.mha.set_fastpath_enabled(False)
    OUT.mkdir(parents=True, exist_ok=True)
    model = load()
    core = Core(model).eval()
    L = segment_length(model)
    mix = torch.randn(1, 2, L) * 0.1
    mag = model._magnitude(model._spec(mix))
    print("segment", L, "mag", tuple(mag.shape))
    onnx_path = OUT / f"{NAME}-core.onnx"
    with torch.no_grad():
        torch.onnx.export(core, (mix, mag), str(onnx_path), input_names=["mix", "mag"], output_names=["spec", "wave"],
                          opset_version=17, dynamo=False)
    print("wrote", onnx_path)
    with torch.no_grad():
        traced = torch.jit.trace(core, (mix, mag), check_trace=False)
    for precision in ("fp32", "fp16"):
        ml = ct.convert(traced, inputs=[ct.TensorType("mix", shape=tuple(mix.shape), dtype=np.float32),
                                        ct.TensorType("mag", shape=tuple(mag.shape), dtype=np.float32)],
                        outputs=[ct.TensorType("spec"), ct.TensorType("wave")], convert_to="mlprogram",
                        minimum_deployment_target=ct.target.macOS14,
                        compute_precision=ct.precision.FLOAT32 if precision == "fp32" else ct.precision.FLOAT16)
        path = OUT / f"{NAME}-core-{precision}.mlpackage"
        ml.save(str(path))
        print("wrote", path)


if __name__ == "__main__":
    main()
