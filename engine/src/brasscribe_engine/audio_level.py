"""The engine's rendered MP3 at the level the Play apps play the band (sounds/playback-levels.json).

MuseScore renders brass-band.mp3 with its own sounds and its own level: about -4.6 LUFS, peaking at full
scale, so "Listen to this bar" and the Studio player jumped against the band and the recording. The engine
measures the whole file (ITU-R BS.1770 integrated loudness), gains it to the loudness the band plays that
arrangement at (recording.band_estimate: the arrangement's estimate, clamped to the recording's target range;
band.phrase_lufs without one), and runs it through the apps' soft limiter (band stage: y = x up to the
threshold, a tanh knee up to the ceiling), so it peaks under the same ceiling.

The sounds stay MuseScore's: the engine has no SoundFont synthesizer (MuseScore's command line cannot choose a
SoundFont, and FluidSynth is not part of the engine's runtime on any Bandroom platform), so the band pack is
not used here.
"""

from __future__ import annotations

import importlib.util
import json
import math
from pathlib import Path

import numpy as np

from .config import REPO_ROOT

LEVELS_NAME = "playback-levels.json"


def levels_path(band_sounds_dir: Path | None = None) -> Path | None:
    """playback-levels.json: next to the band sounds the engine serves (Bandroom stages it there), else the repo's."""
    for d in (band_sounds_dir, REPO_ROOT / "sounds"):
        if d is not None and (Path(d) / LEVELS_NAME).is_file():
            return Path(d) / LEVELS_NAME
    return None


def _biquad(b, a, x):
    from scipy.signal import lfilter
    return lfilter(b, a, x, axis=0)


def _k_weighting(rate: int):
    """The two BS.1770 K-weighting stages for any sample rate, as pyloudnorm designs them (RBJ biquads): a +4 dB
    high shelf at 1.5 kHz and a high pass at 38 Hz."""
    def rbj(kind: str, g: float, q: float, fc: float):
        a_ = 10 ** (g / 40)
        w0 = 2 * math.pi * fc / rate
        c, alpha = math.cos(w0), math.sin(w0) / (2 * q)
        if kind == "shelf":
            b = [a_ * ((a_ + 1) + (a_ - 1) * c + 2 * math.sqrt(a_) * alpha), -2 * a_ * ((a_ - 1) + (a_ + 1) * c),
                 a_ * ((a_ + 1) + (a_ - 1) * c - 2 * math.sqrt(a_) * alpha)]
            a = [(a_ + 1) - (a_ - 1) * c + 2 * math.sqrt(a_) * alpha, 2 * ((a_ - 1) - (a_ + 1) * c),
                 (a_ + 1) - (a_ - 1) * c - 2 * math.sqrt(a_) * alpha]
        else:
            b = [(1 + c) / 2, -(1 + c), (1 + c) / 2]
            a = [1 + alpha, -2 * c, 1 - alpha]
        return [v / a[0] for v in b], [v / a[0] for v in a]
    return rbj("shelf", 4.0, 1 / math.sqrt(2), 1500.0), rbj("hp", 0.0, 0.5, 38.0)


def integrated_lufs(x: np.ndarray, rate: int) -> float:
    """ITU-R BS.1770-4 integrated loudness of `x` (frames x channels, or mono): K-weighting, 400 ms blocks at
    75 % overlap, the -70 LUFS absolute and -10 LU relative gates. -inf for silence."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    shelf, hp = _k_weighting(rate)
    y = _biquad(*hp, _biquad(*shelf, x))
    n, step = int(round(0.4 * rate)), int(round(0.1 * rate))
    if len(y) < n:
        return -math.inf
    starts = range(0, len(y) - n + 1, step)
    z = np.array([np.mean(y[s:s + n] ** 2, axis=0).sum() for s in starts])
    with np.errstate(divide="ignore"):
        lk = -0.691 + 10 * np.log10(z)
    z = z[lk > -70]
    if not len(z):
        return -math.inf
    rel = -0.691 + 10 * math.log10(z.mean()) - 10
    with np.errstate(divide="ignore"):
        z = z[-0.691 + 10 * np.log10(z) > rel]
    return -0.691 + 10 * math.log10(z.mean()) if len(z) else -math.inf


def limit(x: np.ndarray, threshold: float, ceiling: float) -> np.ndarray:
    """The apps' soft limiter, sample by sample."""
    a = np.abs(x)
    knee = ceiling - threshold
    y = np.where(a <= threshold, a, threshold + knee * np.tanh((a - threshold) / knee))
    return np.sign(x) * y


def target_lufs(score: Path, levels_file: Path) -> float:
    """The loudness the band plays this arrangement at: its band estimate, clamped like a recording's target;
    band.phrase_lufs when the estimate cannot be made here (no sounds/playback_levels.py) or has no notes."""
    levels = json.loads(levels_file.read_text())
    code = levels_file.with_name("playback_levels.py")
    if code.is_file() and score.is_file():
        spec = importlib.util.spec_from_file_location("brasscribe_playback_levels", code)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        est = mod.band_estimate_lufs(mod.musicxml_notes(score, levels), levels)
        if est is not None:
            return mod.recording_target_lufs(est, levels["recording"])
    return float(levels["band"]["phrase_lufs"])


def level_mp3(mp3: Path, score: Path, levels_file: Path) -> dict:
    """Gain `mp3` in place to the arrangement's band loudness and limit it at the apps' ceiling. Returns what
    was measured, for export.json."""
    import soundfile as sf

    levels = json.loads(levels_file.read_text())
    lim = levels["limiter"]
    x, rate = sf.read(str(mp3), dtype="float64", always_2d=True)
    before = integrated_lufs(x, rate)
    target = target_lufs(score, levels_file)
    info = {"lufs_before": _round(before), "peak_dbfs_before": _round(_peak_db(x)), "target_lufs": round(target, 2)}
    if not math.isfinite(before):
        return {**info, "gain_db": 0.0}
    gain = target - before
    y = limit(x * 10 ** (gain / 20), lim["threshold"], lim["ceiling"])
    # MP3 encoding overshoots a little: re-read what was written and pull it under the ceiling if it went over
    for _ in range(3):
        sf.write(str(mp3), y.astype(np.float32), rate, format="MP3")
        z, _ = sf.read(str(mp3), dtype="float64", always_2d=True)
        over = np.abs(z).max() / lim["ceiling"]
        if over <= 1.0:
            break
        y = y / over
    return {**info, "gain_db": round(gain, 2), "lufs_after": _round(integrated_lufs(z, rate)),
            "peak_dbfs_after": _round(_peak_db(z))}


def _peak_db(x: np.ndarray) -> float:
    p = float(np.abs(x).max()) if x.size else 0.0
    return 20 * math.log10(p) if p > 0 else -math.inf


def _round(v: float) -> float | None:
    return round(v, 2) if math.isfinite(v) else None
