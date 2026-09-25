"""Build textural layers from Mega-53 stems and transcribe each one.

Layers for the solo-with-band arrangement:
  solo      Mega-53 trumpet stem
  bass      Mega-53 bass stem
  drums     Mega-53 drums stem
  orchestra residual: mix - solo - bass - drums (Mega-53's strings stems are
            near-silent on orchestral recordings like Mikkel, so the orchestra
            is taken as whatever the other layers do not explain)
Transcription per layer: solo with MuScriptor, Basic Pitch and SwiftF0 (they
vote, see solo_vote_bench); the other layers with MuScriptor.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ADAPTERS = Path(__file__).resolve().parents[2] / "ml" / "adapters"
STEMS = {"solo": "trumpet", "bass": "bass", "drums": "drums"}
TRANSCRIBERS = {
    "solo": [("muscriptor", "mus"), ("basic-pitch", "bp"), ("swift-f0", "sw")],
    "orchestra": [("muscriptor", "mus")],
    "bass": [("muscriptor", "mus")],
    "drums": [("muscriptor", "mus")],
}


def _resampled_mix(mix: Path, sr: int, workdir: Path) -> np.ndarray:
    tmp = workdir / "mix_resampled.wav"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(mix), "-ar", str(sr), "-ac", "2", str(tmp)], check=True)
    y, _ = sf.read(tmp, dtype="float32")
    tmp.unlink()
    return y


def build(mix: Path, stems: Path, out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths, audio, sr = {}, {}, None
    for layer, stem in STEMS.items():
        y, sr = sf.read(stems / f"{stem}.flac", dtype="float32")
        audio[layer] = y
        paths[layer] = out / f"{layer}.wav"
        sf.write(paths[layer], y, sr)
    y_mix = _resampled_mix(mix, sr, out)
    n = min(len(y_mix), *(len(a) for a in audio.values()))
    residual = y_mix[:n] - sum(a[:n] for a in audio.values())
    paths["orchestra"] = out / "orchestra.wav"
    sf.write(paths["orchestra"], residual, sr)
    return paths


def energy_report(paths: dict[str, Path], window: float = 15.0) -> None:
    rows = {}
    for layer, p in paths.items():
        y, sr = sf.read(p, dtype="float32")
        y = y.mean(axis=1) if y.ndim > 1 else y
        n = int(window * sr)
        rows[layer] = [float(np.sqrt(np.mean(y[i:i + n] ** 2))) for i in range(0, len(y), n)]
    print("window(s) " + " ".join(f"{k:>9s}" for k in rows))
    for i in range(max(len(v) for v in rows.values())):
        print(f"{i * window:8.0f}  " + " ".join(f"{v[i] if i < len(v) else 0:9.4f}" for v in rows.values()))


def transcribe(paths: dict[str, Path]) -> None:
    for layer, tools in TRANSCRIBERS.items():
        for tool, suffix in tools:
            out = paths[layer].with_name(f"{layer}-{suffix}.mid")
            if not out.exists():
                subprocess.run([str(ADAPTERS / tool / "run.sh"), str(paths[layer]), str(out)], check=True)
    # Frame-level SwiftF0 contour of the solo stem: where sustained solo notes really end.
    contour = paths["solo"].with_name("solo-sw.contour.npz")
    if not contour.exists():
        subprocess.run(["uv", "run", "--project", str(ADAPTERS / "swift-f0"), "python",
                        str(Path(__file__).with_name("swiftf0_contour.py")), str(paths["solo"]), str(contour)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("mix", type=Path, help="the full mix (any sample rate)")
    ap.add_argument("stems", type=Path, help="Mega-53 output dir for that mix")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--transcribe", action="store_true")
    args = ap.parse_args()
    paths = build(args.mix, args.stems, args.out)
    energy_report(paths)
    if args.transcribe:
        transcribe(paths)


if __name__ == "__main__":
    main()
