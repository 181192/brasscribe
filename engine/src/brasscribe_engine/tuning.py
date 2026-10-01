"""Retune before transcribing (docs/research/11-overlaps-and-in-between-tones.md §3.2).

Bands rarely play at exactly A = 440: the eval recordings sit 1–20 cents sharp, and
Basic Pitch loses most notes of a band 30 cents off. A transcription stage estimates its
input's offset from A = 440 and, when it is large enough to matter, resamples the audio so
the band plays at A = 440, transcribes that, and scales the note times back to the
original timeline. Resampling at a rational ratio changes pitch and time together and leaves the
sound otherwise as it was, which a phase-vocoder shift does not.

The decision is a parameter of the stage, taken when the stage is keyed (`derive`): an
input that is in tune adds nothing, so its stage keeps the cache key it had before.
"""

from __future__ import annotations

import subprocess
import tempfile
import threading
from fractions import Fraction
from pathlib import Path

import numpy as np

from .hashing import source_fingerprint

THIS = Path(__file__).resolve()
# Retune only beyond this many cents: the estimate of a perfectly tuned brass tone can be a few
# cents off (the 5th and 7th partials sit 14 and 31 cents flat of the tempered grid).
THRESHOLD_CENTS = 5.0
# Below this concentration of the peak deviations (0: spread evenly, 1: all agree) there is no
# tuning to measure: noise, drums, silence.
MIN_CONCENTRATION = 0.3
FFT_SIZE = 16384
MAX_FRAMES = 2000  # frames spread evenly over a long recording; enough for a stable mean
BAND_HZ = (80.0, 2000.0)

_memo: dict[tuple[str, int, int], tuple[float, float]] = {}
_memo_lock = threading.Lock()


def _starts(length: int) -> np.ndarray:
    """Where the analysis windows start: every quarter window, thinned evenly to MAX_FRAMES."""
    starts = np.arange(0, max(length - FFT_SIZE, 0) + 1, FFT_SIZE // 4)
    if len(starts) > MAX_FRAMES:
        starts = starts[np.linspace(0, len(starts) - 1, MAX_FRAMES).astype(int)]
    return starts


def _estimate(windows, sr: int) -> tuple[float, float]:
    """The circular mean over mono windows of FFT_SIZE samples (see estimate)."""
    n = FFT_SIZE
    win = np.hanning(n)
    freqs = np.fft.rfftfreq(n, 1 / sr)
    band = ((freqs > BAND_HZ[0]) & (freqs < BAND_HZ[1]))[1:-1]
    z, total = 0j, 0.0
    for w in windows:
        mag = np.abs(np.fft.rfft(np.pad(w, (0, n - len(w))) * win))
        top = mag.max()
        if top <= 0:
            continue
        mid = mag[1:-1]
        k = np.flatnonzero(band & (mid > mag[:-2]) & (mid >= mag[2:]) & (mid > 0.05 * top)) + 1
        if not len(k):
            continue
        lm = np.log(mag + 1e-12)
        a, b, c = lm[k - 1], lm[k], lm[k + 1]
        f = (k + 0.5 * (a - c) / (a - 2 * b + c - 1e-12)) * sr / n
        cents = 1200 * np.log2(f / 440.0)
        z += np.sum(mag[k] * np.exp(2j * np.pi * cents / 100))
        total += float(np.sum(mag[k]))
    if total <= 0:
        return 0.0, 0.0
    return float(np.angle(z) / (2 * np.pi) * 100), float(abs(z) / total)


def estimate(x: np.ndarray, sr: int) -> tuple[float, float]:
    """Offset of the music from A = 440 in cents (-50..50), and how concentrated the evidence is (0..1).

    The weighted circular mean of the spectral peaks' deviations from the tempered grid: each peak
    between 80 Hz and 2 kHz, located to a fraction of a bin by a parabola through its log magnitude,
    votes for its cents modulo 100 with its magnitude."""
    x = np.asarray(x, dtype=np.float64)
    if x.ndim > 1:
        x = x.mean(axis=1)
    return _estimate((x[i:i + FFT_SIZE] for i in _starts(len(x))), sr)


def _decoded(path: Path, tmp: str, mono: bool = False) -> Path:
    """path itself if libsndfile reads it, else a float WAV decoded by ffmpeg (mono if asked)."""
    import soundfile as sf

    try:
        sf.info(str(path))
        return path
    except (RuntimeError, sf.LibsndfileError):
        wav = Path(tmp) / "decoded.wav"
        subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(path), "-vn", "-c:a", "pcm_f32le",
                        *(["-ac", "1"] if mono else []), str(wav)], check=True)
        return wav


def read_audio(path: Path) -> tuple[np.ndarray, int]:
    """Samples (frames x channels, float32) and rate; formats libsndfile cannot read are decoded by ffmpeg."""
    import soundfile as sf

    with tempfile.TemporaryDirectory() as tmp:
        return sf.read(str(_decoded(path, tmp)), dtype="float32", always_2d=True)


def estimate_file(path: Path) -> tuple[float, float]:
    """estimate() of an audio file, reading only the analysis windows (a long recording is never held
    whole), remembered for the file as it is (path, size and time)."""
    import soundfile as sf

    st = path.stat()
    memo_key = (str(path.resolve()), st.st_size, st.st_mtime_ns)
    with _memo_lock:
        if memo_key in _memo:
            return _memo[memo_key]
    with tempfile.TemporaryDirectory() as tmp, sf.SoundFile(str(_decoded(path, tmp, mono=True))) as f:
        def windows():
            for i in _starts(f.frames):
                f.seek(int(i))
                yield f.read(FFT_SIZE, dtype="float64", always_2d=True).mean(axis=1)

        result = _estimate(windows(), f.samplerate)
    with _memo_lock:
        _memo[memo_key] = result
    return result


def decide(cents: float, concentration: float) -> int:
    """The shift to apply, in whole cents (0: leave the audio as it is). Whole cents keep the cache key
    stable across hosts whose estimates differ in the last digits."""
    if concentration < MIN_CONCENTRATION or abs(cents) < THRESHOLD_CENTS:
        return 0
    return -round(cents)


def derive(inputs: dict[str, Path]) -> tuple[dict, dict]:
    """Stage.derive for a transcription stage: the retune parameters for its cache key (empty when the
    input is in tune) and the measured offset for the manifest."""
    try:
        cents, concentration = estimate_file(inputs["audio"])
    except Exception as e:  # noqa: BLE001 - an input it cannot measure is transcribed as it is
        return {}, {"tuning_error": f"{type(e).__name__}: {e}"}
    shift = decide(cents, concentration)
    facts = {"tuning_cents": round(cents, 1), "concentration": round(concentration, 2), "retuned": bool(shift)}
    if not shift:
        return {}, facts
    return {"retune": {"shift_cents": shift, "code": source_fingerprint(THIS)}}, {**facts, "shift_cents": shift}


def ratio(shift_cents: int) -> Fraction:
    """The pitch ratio 2^(shift/1200) as a fraction with a small denominator, so it can drive a
    polyphase resampler; its error is far below a hundredth of a cent."""
    return Fraction(2 ** (shift_cents / 1200)).limit_denominator(2000)


def shift_audio(src: Path, dst: Path, shift_cents: int) -> Fraction:
    """Write src to dst (WAV, float, same rate) played `shift_cents` higher; returns the pitch ratio q.
    The result is 1/q times as long, so a time t in it is t * q in src."""
    import soundfile as sf
    from scipy.signal import resample_poly

    x, sr = read_audio(src)
    q = ratio(shift_cents)
    # Stretching by 1/q = den/num and playing at the same rate raises the pitch by q.
    y = resample_poly(x, q.denominator, q.numerator, axis=0)
    sf.write(str(dst), y.astype(np.float32), sr, subtype="FLOAT")
    return q


def rescale_midi(path: Path, factor: float) -> None:
    """Multiply every event time of a MIDI file by `factor`, in place."""
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(str(path))
    for inst in pm.instruments:
        for n in inst.notes:
            n.start *= factor
            n.end *= factor
        for b in inst.pitch_bends:
            b.time *= factor
        for c in inst.control_changes:
            c.time *= factor
    pm.write(str(path))


def transcribe(ctx) -> None:
    """A transcription stage: the adapter on the input, or on the input retuned to A = 440 with the
    note times scaled back when the stage was keyed with a retune."""
    dst = ctx.out / ctx.params["output"]
    retune = ctx.params.get("retune")
    if not retune:
        ctx.adapter(ctx.stage.adapter, ctx.inputs["audio"], dst, env=ctx.params.get("env"))
        return
    shift = retune["shift_cents"]
    with tempfile.TemporaryDirectory(dir=ctx.out.parent) as tmp:
        audio = Path(tmp) / "retuned.wav"
        q = shift_audio(ctx.inputs["audio"], audio, shift)
        ctx.log(f"retuned {shift:+d} cents to A = 440 before {ctx.stage.adapter}")
        part = Path(tmp) / dst.name
        ctx.adapter(ctx.stage.adapter, audio, part, env=ctx.params.get("env"))
        rescale_midi(part, float(q))
        part.replace(dst)
