"""Build textural layers from Mega-53 stems and transcribe each one.

Mega-53 stems are hierarchical (wind ⊇ brass ⊇ trumpet ...), so layers are
picked from the stems that match a texture, and orchestral brass is taken as
brass minus the solo trumpet. Each layer is transcribed with both MuScriptor
and Basic Pitch; which one feeds the arrangement is decided per layer.
"""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf

ADAPTERS = Path(__file__).resolve().parents[2] / "ml" / "adapters"

LAYERS = {
    "solo": ["trumpet"],
    "strings": ["bowed_strings"],
    "keys": ["keys"],
    "bass": ["bass"],
    "drums": ["drums"],
}


def load(stems: Path, name: str) -> tuple[np.ndarray, int]:
    y, sr = sf.read(stems / f"{name}.flac", dtype="float32")
    return y, sr


def build(stems: Path, out: Path) -> dict[str, Path]:
    out.mkdir(parents=True, exist_ok=True)
    paths = {}
    for layer, names in LAYERS.items():
        ys = [load(stems, n) for n in names]
        y = sum(a for a, _ in ys)
        paths[layer] = out / f"{layer}.wav"
        sf.write(paths[layer], y, ys[0][1])
    brass, sr = load(stems, "brass")
    trumpet, _ = load(stems, "trumpet")
    paths["brass"] = out / "brass.wav"
    sf.write(paths["brass"], brass - trumpet, sr)
    return paths


def energy_report(paths: dict[str, Path], window: float = 15.0) -> None:
    rows = {}
    for layer, p in paths.items():
        y, sr = sf.read(p, dtype="float32")
        y = y.mean(axis=1) if y.ndim > 1 else y
        n = int(window * sr)
        rows[layer] = [float(np.sqrt(np.mean(y[i:i + n] ** 2))) for i in range(0, len(y), n)]
    print("window(s) " + " ".join(f"{k:>8s}" for k in rows))
    for i in range(max(len(v) for v in rows.values())):
        print(f"{i * window:8.0f}  " + " ".join(f"{v[i] if i < len(v) else 0:8.4f}" for v in rows.values()))


def transcribe(paths: dict[str, Path]) -> None:
    for layer, p in paths.items():
        for tool, suffix in (("muscriptor", "mus"), ("basic-pitch", "bp")):
            if layer == "drums" and tool == "basic-pitch":
                continue
            out = p.with_name(f"{layer}-{suffix}.mid")
            if not out.exists():
                subprocess.run([str(ADAPTERS / tool / "run.sh"), str(p), str(out)], check=True)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("stems", type=Path, help="Mega-53 output dir for the full mix")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--transcribe", action="store_true")
    args = ap.parse_args()
    paths = build(args.stems, args.out)
    energy_report(paths)
    if args.transcribe:
        transcribe(paths)


if __name__ == "__main__":
    main()
