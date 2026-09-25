"""Compare two renders of the same score stem by stem (e.g. SFZ via sfizz vs SF2 via FluidSynth).

    uv run --project sounds python sounds/parity.py RUN_A RUN_B

Per part: level difference (dB RMS), spectral-centroid ratio, and the correlation of the
50 ms RMS envelopes (timing and articulation agreement). Stems are the dry per-part files
render.py writes, so room and placement are identical by construction and excluded.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp import SR, spectral_centroid  # noqa: E402


def env(x: np.ndarray, win: int = int(0.05 * SR)) -> np.ndarray:
    n = len(x) // win
    return np.sqrt(np.mean(x[: n * win].reshape(n, win) ** 2, axis=1))


def main() -> None:
    a_dir, b_dir = Path(sys.argv[1]) / "stems", Path(sys.argv[2]) / "stems"
    print(f"{'part':16s} {'level dB':>9s} {'centroid':>9s} {'env corr':>9s}")
    rows = []
    for fa in sorted(a_dir.glob("*.wav")):
        fb = b_dir / fa.name
        if not fb.exists():
            continue
        xa, _ = sf.read(str(fa), dtype="float64")
        xb, _ = sf.read(str(fb), dtype="float64")
        n = min(len(xa), len(xb))
        xa, xb = xa[:n], xb[:n]
        ra, rb = np.sqrt(np.mean(xa ** 2)), np.sqrt(np.mean(xb ** 2))
        if ra < 1e-6 or rb < 1e-6:
            continue
        level = 20 * np.log10(rb / ra)
        cent = spectral_centroid(xb) / spectral_centroid(xa)
        corr = float(np.corrcoef(env(xa), env(xb))[0, 1])
        rows.append((level, cent, corr))
        print(f"{fa.stem:16s} {level:+9.2f} {cent:9.3f} {corr:9.3f}")
    lv, ce, co = map(np.array, zip(*rows))
    print(f"{'median':16s} {np.median(lv):+9.2f} {np.median(ce):9.3f} {np.median(co):9.3f}")
    print(f"{'spread (p90-p10)':16s} {np.percentile(lv, 90) - np.percentile(lv, 10):9.2f}")


if __name__ == "__main__":
    main()
