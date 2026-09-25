"""Separation-failure check: does a separated solo stem contain the soloist?

When the separator misses the soloist, the stem is left near-silent and a
transcriber still returns a few notes, so the failure is silent. Measured on
Mega-53 trumpet stems of 10 ChoraleBricks mixes and 2 Slakh songs: the two
failures (SwiftF0 F1 0.07 and 0.35 against the reference trumpet) had the stem
44 and 36 dB under the mix; every working stem was 11-17 dB under. The check
flags a stem more than `FAIL_DB` under the mix overall, and lists the windows
where the mix plays but the stem is that quiet (a soloist missing for a
passage, or a solo that rests).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

FAIL_DB = 25.0
WINDOW = 10.0  # s
ACTIVE_DB = 30.0  # a mix window within this of the mix's loud level is playing


def _rms_db(y: np.ndarray) -> float:
    return float(20 * np.log10(np.sqrt(np.mean(np.square(y, dtype=np.float64))) + 1e-9))


def _mono(y: np.ndarray) -> np.ndarray:
    return y.mean(axis=1) if y.ndim > 1 else y


@dataclass
class SeparationCheck:
    stem_minus_mix_db: float
    failed: bool
    quiet_windows: list[tuple[float, float, float]] = field(default_factory=list)  # (start_s, end_s, stem - mix dB)

    def summary(self) -> str:
        state = "FAILED: the stem does not seem to contain the soloist" if self.failed else "ok"
        return f"solo stem {self.stem_minus_mix_db:.1f} dB under the mix ({state}); quiet windows: " + \
            (", ".join(f"{a:.0f}-{b:.0f} s ({d:.0f} dB)" for a, b, d in self.quiet_windows) or "none")


def check_stem(stem: np.ndarray, mix: np.ndarray, sr: int, fail_db: float = FAIL_DB) -> SeparationCheck:
    """Compare a stem with its mix (same sample rate)."""
    s, m = _mono(stem), _mono(mix)
    n = min(len(s), len(m))
    s, m = s[:n], m[:n]
    overall = _rms_db(s) - _rms_db(m)
    w = int(WINDOW * sr)
    levels = [(i / sr, min(n, i + w) / sr, _rms_db(m[i:i + w]), _rms_db(s[i:i + w])) for i in range(0, n, w)]
    loud = max((lm for *_, lm, _ in levels), default=-120.0)
    quiet = [(a, b, ls - lm) for a, b, lm, ls in levels if lm >= loud - ACTIVE_DB and ls - lm < -fail_db]
    return SeparationCheck(round(overall, 2), overall < -fail_db, [(a, b, round(d, 1)) for a, b, d in quiet])
