"""Shared DSP: RBJ-cookbook biquads, level measurement, pitch helpers.

The EQ here is the single definition of the timbre adaptation. It is applied offline
to sample copies, so every playback engine (sfizz, AVAudioUnitSampler, TinySoundFont)
plays identical audio and none of them needs an EQ of its own.
"""

from __future__ import annotations

import math
import re

import numpy as np
from scipy import signal

SR = 44100
NOTE_NAMES = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def biquad(kind: str, f: float, sr: int = SR, gain_db: float = 0.0, q: float = 0.707) -> np.ndarray:
    """One second-order section (b0 b1 b2 a0 a1 a2), normalised, per the RBJ Audio EQ Cookbook."""
    a_lin = 10 ** (gain_db / 40)
    w0 = 2 * math.pi * f / sr
    cw, sw = math.cos(w0), math.sin(w0)
    alpha = sw / (2 * q)
    if kind == "peak":
        b = [1 + alpha * a_lin, -2 * cw, 1 - alpha * a_lin]
        a = [1 + alpha / a_lin, -2 * cw, 1 - alpha / a_lin]
    elif kind in ("lowshelf", "highshelf"):
        sq = 2 * math.sqrt(a_lin) * alpha
        if kind == "lowshelf":
            b = [a_lin * ((a_lin + 1) - (a_lin - 1) * cw + sq), 2 * a_lin * ((a_lin - 1) - (a_lin + 1) * cw),
                 a_lin * ((a_lin + 1) - (a_lin - 1) * cw - sq)]
            a = [(a_lin + 1) + (a_lin - 1) * cw + sq, -2 * ((a_lin - 1) + (a_lin + 1) * cw),
                 (a_lin + 1) + (a_lin - 1) * cw - sq]
        else:
            b = [a_lin * ((a_lin + 1) + (a_lin - 1) * cw + sq), -2 * a_lin * ((a_lin - 1) + (a_lin + 1) * cw),
                 a_lin * ((a_lin + 1) + (a_lin - 1) * cw - sq)]
            a = [(a_lin + 1) - (a_lin - 1) * cw + sq, 2 * ((a_lin - 1) - (a_lin + 1) * cw),
                 (a_lin + 1) - (a_lin - 1) * cw - sq]
    elif kind == "lowpass":
        b = [(1 - cw) / 2, 1 - cw, (1 - cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    elif kind == "highpass":
        b = [(1 + cw) / 2, -(1 + cw), (1 + cw) / 2]
        a = [1 + alpha, -2 * cw, 1 - alpha]
    else:
        raise ValueError(f"unknown biquad type {kind}")
    return np.array(b + a) / a[0]


def eq_sos(stages: list[dict], sr: int = SR) -> np.ndarray | None:
    if not stages:
        return None
    return np.vstack([biquad(s["type"], s["f"], sr, s.get("gain_db", 0.0), s.get("q", 0.707)) for s in stages])


def apply_eq(x: np.ndarray, stages: list[dict], sr: int = SR) -> np.ndarray:
    sos = eq_sos(stages, sr)
    return x if sos is None else signal.sosfilt(sos, x, axis=0)


def eq_response_db(stages: list[dict], freqs: np.ndarray, sr: int = SR) -> np.ndarray:
    sos = eq_sos(stages, sr)
    if sos is None:
        return np.zeros_like(freqs)
    _, h = signal.sosfreqz(sos, worN=freqs, fs=sr)
    return 20 * np.log10(np.abs(h) + 1e-12)


def db(x: float) -> float:
    return 20 * math.log10(max(x, 1e-12))


def envelope_db(x: np.ndarray, sr: int = SR, win: float = 0.01) -> np.ndarray:
    n = max(1, int(sr * win))
    frames = len(x) // n
    if frames == 0:
        return np.array([db(float(np.sqrt(np.mean(x ** 2))))])
    e = np.sqrt(np.mean(x[: frames * n].reshape(frames, n) ** 2, axis=1))
    return 20 * np.log10(e + 1e-9)


def loudest_window_db(x: np.ndarray, sr: int = SR, win: float = 0.3) -> float:
    n = int(sr * win)
    if len(x) <= n:
        return db(float(np.sqrt(np.mean(x ** 2))))
    c = np.cumsum(np.concatenate([[0.0], x ** 2]))
    return db(float(np.sqrt(np.max(c[n:] - c[:-n]) / n)))


def k_weight(x: np.ndarray, sr: int = SR) -> np.ndarray:
    """ITU-R BS.1770 K-weighting (pre-filter shelf + RLB high-pass), as pyloudnorm applies it."""
    import pyloudnorm
    y = x
    for f in pyloudnorm.Meter(sr)._filters.values():
        y = f.apply_filter(y)
    return y


def midi_from_name(name: str) -> int:
    """'A#1' / 'Bb1' / 'C4' -> MIDI with C4 = 60 (scientific pitch). Library offsets are applied by the caller."""
    m = re.fullmatch(r"([A-G])([#b]?)(-?\d)", name)
    if not m:
        raise ValueError(name)
    pc = NOTE_NAMES[m.group(1)] + {"#": 1, "b": -1, "": 0}[m.group(2)]
    return (int(m.group(3)) + 1) * 12 + pc


def hz_to_midi(f: float) -> float:
    return 69 + 12 * math.log2(f / 440.0)


def spectral_centroid(x: np.ndarray, sr: int = SR, n_fft: int = 4096) -> float:
    """Energy-weighted mean spectral centroid in Hz over frames above -40 dB of the loudest frame."""
    if len(x) < n_fft:
        x = np.pad(x, (0, n_fft - len(x)))
    f, _, z = signal.stft(x, sr, nperseg=n_fft, noverlap=n_fft * 3 // 4)
    p = np.abs(z) ** 2
    e = p.sum(axis=0)
    keep = e > e.max() * 1e-4
    if not keep.any():
        return float("nan")
    c = (f[:, None] * p[:, keep]).sum(axis=0) / (p[:, keep].sum(axis=0) + 1e-20)
    return float(np.sum(c * e[keep]) / np.sum(e[keep]))
