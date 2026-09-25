"""Loudness envelopes of layers: gate transcribed notes, and read dynamics.

A transcriber run on a separated stem or a residual also "hears" bleed and
silence: on Mikkel, 10% of the bass-stem notes start more than 44 dB under
the stem's loud level (the stem is empty there). `gate` drops notes whose
layer is that quiet at the onset.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

HOP = 0.01  # s
GATE_DB = 30.0  # notes starting more than this far under the layer's loud level are dropped
ONSET_WINDOW = 0.06  # s after the onset in which the layer must reach the level


@dataclass
class Envelope:
    """RMS level in dB per HOP seconds, and the layer's loud reference level (95th percentile)."""

    db: np.ndarray
    ref: float

    @staticmethod
    def of(y: np.ndarray, sr: int) -> Envelope:
        y = y.mean(axis=1) if y.ndim > 1 else y
        hop = max(1, int(HOP * sr))
        n = len(y) // hop
        rms = np.sqrt(np.mean(y[: n * hop].reshape(n, hop) ** 2, axis=1)) if n else np.zeros(1)
        db = 20 * np.log10(rms + 1e-9)
        return Envelope(db, float(np.percentile(db, 95)))

    def level_at(self, t: float, window: float = ONSET_WINDOW) -> float:
        """Peak level in [t, t + window), relative to the reference (dB, <= about 0)."""
        a = int(t / HOP)
        b = max(a + 1, int((t + window) / HOP))
        seg = self.db[a:b]
        return float(seg.max() - self.ref) if len(seg) else -120.0

    def mean_level(self, t0: float, t1: float) -> float:
        seg = self.db[int(t0 / HOP):max(int(t0 / HOP) + 1, int(t1 / HOP))]
        return float(10 * np.log10(np.mean(10 ** (seg / 10))) - self.ref) if len(seg) else -120.0


def gate(notes: list[dict], env: Envelope, gate_db: float = GATE_DB) -> tuple[list[dict], int]:
    """Notes (dicts with "onset") whose layer reaches the level at their onset, and how many were dropped."""
    kept = [n for n in notes if env.level_at(n["onset"]) >= -gate_db]
    return kept, len(notes) - len(kept)
