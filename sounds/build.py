"""Build brass-band instruments (SFZ + SF2) from the analysed raw samples.

    uv run --project sounds python sounds/build.py [target ...]

For every target in sounds/mapping.json this writes data/sounds/built/<target>/:
    samples/*.wav            mono 24-bit, trimmed, looped, EQ'd, level-normalised copies
    <target>-sus.sfz         sustain articulation (sfizz)
    <target>-stac.sfz        staccato articulation
    <target>.sf2             both articulations, program 0 = sus, 1 = stac (AVAudioUnitSampler, TinySoundFont)
    regions.json             the region table both formats are generated from

Both formats come from one region table, so they agree on key ranges, velocity layers,
tuning, loops and levels. Round robin exists only in the SFZ (SF2 has no round robin; the
SF2 uses the first variant of every note).
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "music" / "src"))
from brasscribe_music.instruments import INSTRUMENTS  # noqa: E402
from dsp import SR, apply_eq, envelope_db, k_weight, loudest_window_db  # noqa: E402
import sf2  # noqa: E402

RAW = ROOT / "data" / "sounds" / "raw"
BUILT = Path(os.environ.get("BRASSCRIBE_SOUNDS_BUILT", ROOT / "data" / "sounds" / "built"))  # staging builds
ANALYSIS = Path(os.environ.get("BRASSCRIBE_SOUNDS_ANALYSIS", ROOT / "data" / "sounds" / "analysis.json"))
MAPPING = HERE / "mapping.json"

# Nominal dynamic of each layer, by number of layers available (softest first).
LAYER_DYNAMICS = {1: ["mf"], 2: ["p", "f"], 3: ["pp", "mf", "ff"], 4: ["p", "mf", "f", "ff"]}
DYN_VELOCITY = {"pp": 30, "p": 48, "mf": 80, "f": 100, "ff": 116}
# Level of each baked sample, dBFS: sustain RMS over 80 ms-1.0 s (body_db), staccato loudest 80 ms. Every layer
# is baked at the same level: the layers give the tone of each dynamic, VEL_CURVE gives the level. Players that
# ignore zone attenuation and velocity modulators (AVAudioUnitSampler) then play no level jump at a layer split;
# they used to play 5-10 dB (pp -30, p -26, mf -21, f -18.5, ff -16 dBFS).
DYN_LEVEL_DB = {"pp": -21.0, "p": -21.0, "mf": -21.0, "f": -21.0, "ff": -21.0}
VEL_SPAN_DB = 6.0  # the SF2 velocity modulator: dB-linear over 0-127 (FluidSynth follows it; alphaSynth and
# AVAudioUnitSampler ignore it). The SFZ follows VEL_CURVE instead.
# VEL_CURVE: the level every player follows between the table's dynamics (sounds/playback-levels.json), dB relative
# to velocity 127: VEL_CURVE_DB_PER_MARK per 16 velocities (one dynamic mark) from VEL_CURVE_KNEE up, amplitude
# proportional to velocity below it. The SFZ declares it with amp_velcurve_N; the band SoundFont (band.py) cuts each
# layer's velocity range into attenuated steps, since alphaSynth plays amplitude proportional to velocity.
VEL_CURVE_DB_PER_MARK = 3.6
VEL_CURVE_KNEE = 31
MAX_STRETCH = 3  # semitones a sample may be transposed before a neighbouring layer's sample is borrowed
MATCH_MAX_DB = 9.0  # largest boost or cut the spectral match may apply
EXTEND_BEYOND = 2  # an extension source fills keys more than this many semitones from every primary sample
# Release after note-off. SFZ ampeg_release (sfizz) and the SF2 volume-envelope release (defined as
# the time to fall 100 dB) reach -40 dB at different fractions of the stated time; both are set so
# the tail falls 40 dB in about 250 ms (sustain) and 150 ms (staccato), measured by soundcheck.py.
RELEASE_S = {"sus": 0.45, "stac": 0.28}
SF2_RELEASE_S = {"sus": 0.60, "stac": 0.38}
# Every target's mf layer is scaled so its K-weighted body level (body_db) in the comfortable range
# is this, so all presets play equally loud at the same velocity and part balance is only the
# channel gain (mapping.json parts[].balance_lu). Peaks are kept under -1 dBFS by lowering it.
TARGET_K_DB = -24.0
MAX_PEAK = 0.89
DC_BLOCK = [{"type": "highpass", "f": 25, "q": 0.707}]


def velocity_ranges(dyns: list[str]) -> list[tuple[int, int]]:
    centres = [DYN_VELOCITY[d] for d in dyns]
    cuts = [(a + b) // 2 for a, b in zip(centres, centres[1:])]
    lows = [1] + [c + 1 for c in cuts]
    highs = cuts + [127]
    return list(zip(lows, highs))


# Where a source note really starts, seconds into its segment, when trim() cannot find it: (file, MIDI note) -> s.
# The Iowa bass trombone's pp C3 (first note of its C3-B3 run) sits in noise only 13 dB under the note, with a
# blip at 0.10 s, and speaks at 0.14 s; from the segment start it played 150 ms of noise before the note, which the
# phrase check read as a 20 dB dropout on every player.
SEGMENT_START_S = {("iowa-mis/bass-trombone/run/BassTrombone.pp.C3B3.aiff", 48): 0.14}


def load_segment(note: dict) -> np.ndarray:
    start = note["start"] + int(SEGMENT_START_S.get((note["file"], note["midi"]), 0.0) * SR)
    x, sr = sf.read(str(RAW / note["file"]), dtype="float64", always_2d=True, start=start, stop=note["end"])
    assert sr == SR
    return x.mean(axis=1)


def trim(x: np.ndarray) -> np.ndarray:
    a = np.abs(x)
    peak = a.max()
    if peak <= 0:
        return x
    on = int(np.argmax(a > peak * 10 ** (-40 / 20)))
    start = max(0, on - int(0.003 * SR))
    env = envelope_db(x)
    alive = np.nonzero(env > env.max() - 60)[0]
    end = min(len(x), (alive[-1] + 1) * int(0.01 * SR)) if len(alive) else len(x)
    y = x[start:end].copy()
    fi = min(len(y), int(0.001 * SR))
    y[:fi] *= np.linspace(0, 1, fi)
    fo = min(len(y), int(0.02 * SR))
    y[len(y) - fo :] *= np.linspace(1, 0, fo)
    return y


LOOP_MIN_S, LOOP_MAX_S = 0.6, 2.0  # loop body length; longer loops put the seam further apart
FLAT_WIN_S = 0.3  # the level curve the loop body is held to is smoothed over this (longer than a vibrato cycle)
FLAT_MAX_DB = 6.0  # the flattening gain never exceeds this either way


def _moving_rms(x: np.ndarray, n: int) -> np.ndarray:
    c = np.concatenate([[0.0], np.cumsum(x * x)])
    lo = np.clip(np.arange(len(x)) - n // 2, 0, len(x))
    hi = np.clip(np.arange(len(x)) + n // 2 + 1, 0, len(x))
    return np.sqrt((c[hi] - c[lo]) / np.maximum(hi - lo, 1) + 1e-20)


def _centroid_track(x: np.ndarray, hop: int) -> np.ndarray:
    """Spectral centroid per hop (2048-point frames), smoothed over FLAT_WIN_S."""
    n = 2048
    frames = max(1, (len(x) - n) // hop + 1)
    idx = np.arange(n)[None, :] + hop * np.arange(frames)[:, None]
    spec = np.abs(np.fft.rfft(x[np.minimum(idx, len(x) - 1)] * np.hanning(n), axis=1))
    f = np.fft.rfftfreq(n, 1 / SR)
    c = (spec * f).sum(axis=1) / (spec.sum(axis=1) + 1e-12)
    k = max(1, int(FLAT_WIN_S * SR / hop))
    return np.convolve(c, np.ones(k) / k, mode="same")


def _vibrato(x: np.ndarray, hop: int) -> tuple[np.ndarray, float] | None:
    """Pitch deviation (cents, per hop, from the median) and the vibrato period in hops, from YIN."""
    import librosa
    f0 = librosa.yin(x, fmin=80, fmax=1600, sr=SR, frame_length=2048, hop_length=hop)
    ok = np.isfinite(f0) & (f0 > 0)
    if ok.mean() < 0.8:
        return None
    cents = 1200 * np.log2(f0 / np.median(f0[ok]))
    cents = np.where(ok, cents, 0.0)
    d = cents - np.convolve(cents, np.ones(41) / 41, mode="same")  # remove slow drift (0.4 s)
    ac = np.correlate(d, d, mode="full")[len(d) - 1:]
    lo, hi = int(0.12 * SR / hop), int(0.3 * SR / hop)  # 3.3-8 Hz
    if hi >= len(ac):
        return None
    period = lo + int(np.argmax(ac[lo:hi]))
    if ac[period] < 0.3 * ac[0]:
        return None
    return d, float(period)


def make_loop(x: np.ndarray, vibrato: bool = False) -> tuple[np.ndarray, tuple[int, int] | None]:
    """Crossfade loop in the stable sustain. Returns (audio cut after the loop, (start, end)) or no loop.

    The sustain is where the level stays within `drop` dB of the peak, starting where it first
    comes within `rise` dB; a slow swell (a pp note that grows) gets a wider window. Inside it the
    loop (0.6-2 s) is placed where the level and brightness at its two ends match best, longer
    loops preferred; a vibrato sample's loop is a whole number of vibrato cycles, placed where the
    pitch deviation and its direction match at both ends. Before that the sustain is held at the level
    of its first half second (a gain curve smoothed over 300 ms, at most 6 dB), so a held note neither
    fades from its onset level nor decays or swells once per loop, and the seam has no level step."""
    for rise, drop in ((3, 9), (6, 12), (9, 15)):
        r = _loop_window(x, rise, drop)
        if r is not None:
            break
    else:
        return x, None
    a_frame, b_frame = r
    hop = int(0.01 * SR)
    a_min, b_max = a_frame * hop, b_frame * hop
    # hold the sustain at the level of its first half second: a slow gain curve (300 ms smoothing, at most
    # FLAT_MAX_DB), faded in over 200 ms from where the sustain starts, so the attack is left as recorded
    env = _moving_rms(x, int(FLAT_WIN_S * SR))
    ref = float(np.median(env[a_min: min(len(x), a_min + int(0.5 * SR))]))
    g = np.clip(ref / env, 10 ** (-FLAT_MAX_DB / 20), 10 ** (FLAT_MAX_DB / 20))
    ramp = np.clip((np.arange(len(x)) - a_min) / (0.2 * SR), 0.0, 1.0)
    x = x * (1 + ramp * (g - 1))
    lvl = 20 * np.log10(_moving_rms(x, int(FLAT_WIN_S * SR)) + 1e-12)
    lvl_hop = lvl[::hop]
    cen = _centroid_track(x, hop)
    vib = _vibrato(x, hop) if vibrato else None
    if vib is not None:
        dev, period = vib
        k_max = int((LOOP_MAX_S * SR / hop) // period)
        lengths = [int(round(k * period)) * hop for k in range(1, k_max + 1) if k * period * hop >= LOOP_MIN_S * SR]
    else:
        lengths = list(range(int(LOOP_MIN_S * SR), int(LOOP_MAX_S * SR) + 1, int(0.1 * SR)))
    best = None
    for b in range(b_max, a_min + int(LOOP_MIN_S * SR) - 1, -5 * hop):
        for n in lengths:
            a = b - n
            if a < a_min:
                continue
            ia, ib = a // hop, min(b // hop, len(cen) - 1)
            # prefer longer loops, but not later ones: the sample is cut after the loop end, so a later
            # end only makes the SoundFont bigger
            body = lvl_hop[ia: ib + 1]  # and no dip or swell the flattening could not smooth out inside the loop
            cost = (abs(lvl[b] - lvl[a]) + 20 * abs(np.log(cen[ib] / max(cen[ia], 1.0))) - 0.5 * n / SR
                    + 0.3 * (b - a_min) / SR + (float(body.max() - body.min()) if len(body) else 0.0))
            if vib is not None:
                ib = min(ib, len(dev) - 2)
                slope_a, slope_b = dev[ia + 1] - dev[ia - 1], dev[ib + 1] - dev[ib - 1]
                cost += abs(dev[ib] - dev[ia]) / 5 + (2.0 if slope_a * slope_b < 0 else 0.0)
            if best is None or cost < best[0]:
                best = (cost, a, b)
    if best is None:
        return x, None
    _, a, b = best
    # nudge the loop start to the best waveform match with the loop end
    w = 512
    ref = x[b - w : b]
    reach = 150 if vib is not None else 400
    best_c, best_a = -np.inf, a
    for cand in range(a - reach, a + reach):
        if cand - w < 0:
            continue
        seg = x[cand - w : cand]
        c = float(np.dot(ref, seg) / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-12))
        if c > best_c:
            best_c, best_a = c, cand
    a = best_a
    y = x[: b + 64].copy()
    xf = min(int(0.12 * SR), (b - a) // 2, a)
    t = np.linspace(0, 1, xf)
    y[b - xf : b] = x[b - xf : b] * (1 - t) + x[a - xf : a] * t
    return y, (a, b)


def _loop_window(x: np.ndarray, rise: float, drop: float) -> tuple[int, int] | None:
    hop = int(0.01 * SR)
    env = envelope_db(x)
    peak = env.max()
    loud = np.nonzero(env > peak - rise)[0]
    if not len(loud):
        return None
    a_frame = loud[0] + 8
    stable = np.nonzero(env > peak - drop)[0]
    # loop within the first ~3 s of sustain: long enough for natural onset movement,
    # short enough to keep the instruments small
    b_frame = min(stable[-1] - 10, a_frame + 300)
    if (b_frame - a_frame) * hop < int(0.35 * SR):
        return None
    return a_frame, b_frame


def body_db(y: np.ndarray) -> float:
    """Level of a sustain sample as a short or medium note hears it: RMS over 80 ms-1.0 s.

    The loudest-300 ms window used before let slow-speaking samples (VSCO trombone A#0, D#1)
    reach their level only after 0.5 s, so short notes on them came out 4-5 dB quiet."""
    a, b = int(0.08 * SR), min(len(y), int(1.0 * SR))
    if b - a < int(0.1 * SR):
        return loudest_window_db(y)
    return float(10 * np.log10(np.mean(y[a:b] ** 2) + 1e-20))


def pick_notes(notes: list[dict], library: str, instrument: str, art: str) -> tuple[list[dict], bool]:
    """Notes for one articulation. Returns (notes, derived) where derived means sus samples reused for stac."""
    sel = [n for n in notes if n["library"] == library and n["instrument"] == instrument
           and n.get("midi") is not None and n["art"] == art]
    derived = False
    if not sel and art == "stac":
        sel, derived = pick_notes(notes, library, instrument, "sus")[0], True
    # prefer the cleanly edited per-pitch file over a run segment for the same note/dynamic
    best = {}
    for n in sel:
        key = (n["midi"], n["dyn"], n["rr"])
        if key not in best or (n["kind"] == "pitch" and best[key]["kind"] == "run"):
            best[key] = n
    return list(best.values()), derived


DYN_RANK = {"pp": 0, "p": 1, "mp": 2, "mf": 3, "f": 4, "ff": 5}


def order_layers(notes: list[dict]) -> list[str]:
    """Raw dynamic labels, softest first: Iowa pp/mf/ff by name, VSCO v1 < v2 < ... by index.

    Levels are not used: the libraries were recorded and edited at different gains
    (the Iowa 2014 ff edits are quieter than the mf runs), so only the labels are reliable.
    """
    labels = {n["dyn"] for n in notes}
    return sorted(labels, key=lambda d: DYN_RANK[d] if d in DYN_RANK else int(d[1:]))


def ltas_db(ys: list[np.ndarray], freqs: np.ndarray) -> np.ndarray:
    """Mean log power spectrum (dB) of the first second of each sample, level-normalised."""
    from scipy import signal
    acc = []
    for y in ys:
        seg = y[: int(1.0 * SR)]
        f, pxx = signal.welch(seg, SR, nperseg=min(4096, len(seg)))
        p = 10 * np.log10(np.interp(freqs, f, pxx) + 1e-20)
        band = (freqs > 100) & (freqs < 5000)
        acc.append(p - p[band].mean())
    return np.mean(acc, axis=0)


def smooth_third_octave(freqs: np.ndarray, d: np.ndarray) -> np.ndarray:
    out = np.empty_like(d)
    for i, f in enumerate(freqs):
        m = (freqs >= f * 2 ** (-1 / 6)) & (freqs <= f * 2 ** (1 / 6))
        out[i] = d[m].mean() if m.any() else d[i]
    return out


def match_filter(primary: list[tuple[int, np.ndarray]], ext: list[tuple[int, np.ndarray]]) -> tuple[np.ndarray | None, dict]:
    """Spectral envelope match: a zero-phase FIR that gives the extension source the primary
    source's long-term spectrum, fitted on the pitches both sources have (1/3-octave smoothed,
    clipped to +-12 dB, flat outside 60 Hz-10 kHz)."""
    from scipy import signal
    common = sorted({m for m, _ in primary} & {m for m, _ in ext})
    if len(common) < 3:
        return None, {"common_pitches": common}
    freqs = np.geomspace(20, 20000, 400)
    a = ltas_db([y for m, y in primary if m in common], freqs)
    b = ltas_db([y for m, y in ext if m in common], freqs)
    d = smooth_third_octave(freqs, a - b)
    # below the lowest fundamental there is only rumble and room noise: hold the curve flat there
    f_lo = max(40.0, 0.9 * 440 * 2 ** ((min(common) - 69) / 12))
    d[freqs < f_lo] = d[np.searchsorted(freqs, f_lo)]
    d[freqs > 10000] = d[np.searchsorted(freqs, 10000)]
    d = np.clip(d - d[(freqs > 200) & (freqs < 2000)].mean(), -MATCH_MAX_DB, MATCH_MAX_DB)
    grid = np.concatenate([[0], freqs, [SR / 2]])
    gains = 10 ** (np.concatenate([[d[0]], d, [d[-1]]]) / 20)
    fir = signal.firwin2(2049, grid, gains, fs=SR)
    at = {str(int(f)): round(float(v), 1) for f, v in zip(freqs[::40], d[::40])}
    return fir, {"common_pitches": common, "correction_db": at}


def apply_fir(y: np.ndarray, fir: np.ndarray) -> np.ndarray:
    from scipy import signal
    return signal.fftconvolve(y, fir, mode="same")


PEDAL_MAX = 4  # semitones a pedal note may lie below the layer's lowest recording


def shift_down(y: np.ndarray, semitones: int) -> np.ndarray:
    """The sample `semitones` lower, by resampling (it also plays that much longer)."""
    import soxr
    return soxr.resample(y, SR, SR * 2 ** (semitones / 12), quality="VHQ")


def pedal_fill(chosen: list[dict], audio_of: list[np.ndarray], raw_layers: dict, n_dyns: int, lo: int,
               loops: bool) -> None:
    """Keys of the part's range under a layer's lowest recording (the pedal notes: Bass Trombone A0-B0, B-flat Bass
    B-flat0-B0) get a sample of their own: one of the layer's two lowest recordings shifted down (the nearest whose
    shifted copy still loops, when `loops`), with its long-term spectrum put back where the recording had it
    (match_filter, fitted on the layer's three lowest recordings against themselves shifted by the same interval).
    A player stretching the sample itself moves the whole spectrum down by up to 4 semitones, and a key with no
    sample in its own layer borrowed another layer's (a pp recording at ff)."""
    added = []
    for li in range(n_dyns):
        mine = sorted(((n, y) for n, y in zip(chosen, audio_of)
                       if n.get("rr", 1) == 1 and layer_of(n, raw_layers, n_dyns) == li), key=lambda t: t[0]["midi"])
        if not mine or mine[0][0]["midi"] <= lo:
            continue
        for k in range(max(lo, mine[0][0]["midi"] - PEDAL_MAX), mine[0][0]["midi"]):
            for src, src_y in mine[:2]:
                st = src["midi"] - k
                if st > PEDAL_MAX + 1:
                    continue
                same = [(n["midi"], y) for n, y in mine if n["_src"] == src["_src"]][:3]
                fir, _ = match_filter(same, [(m, shift_down(y, st)) for m, y in same])
                y = shift_down(src_y, st)
                y = apply_fir(y, fir) if fir is not None else y
                if loops and make_loop(y)[1] is None:
                    continue
                added.append((dict(src, midi=k, _pedal=src["file"]), y))
                break
    for n, y in added:
        chosen.append(n)
        audio_of.append(y)


def layer_of(n: dict, raw_layers: dict[str, list[str]], n_dyns: int) -> int:
    """Primary layers map 1:1; an extension source's layers are spread over the primary's by rank."""
    ls = raw_layers[n["_src"]]
    r = ls.index(n["dyn"])
    return r if len(ls) == n_dyns else int(round(r * (n_dyns - 1) / max(1, len(ls) - 1)))


def build_target(tid: str, spec: dict, notes: list[dict]) -> dict:
    inst = INSTRUMENTS[spec["instrument"]]
    lo, hi = inst.pro
    out = BUILT / tid
    (out / "samples").mkdir(parents=True, exist_ok=True)
    for old in (out / "samples").glob("*.wav"):
        old.unlink()
    eq = DC_BLOCK + spec["eq"]
    table = {"target": tid, "instrument": inst.id, "range": [lo, hi], "eq": eq, "sample_rate": SR,
             "vel_span_db": VEL_SPAN_DB, "articulations": {}}
    clo, chi = inst.comfortable
    target_gain_db = None
    for art, src in (("sus", spec["source"]), ("stac", spec["stac_source"])):
        chosen, derived = pick_notes(notes, src["library"], src["instrument"], art)
        chosen = [dict(n, _src="primary") for n in chosen]
        raw_layers = {"primary": order_layers(chosen)}
        audio_of = [apply_eq(trim(load_segment(n)), eq) for n in chosen]
        extensions = []
        for ext in spec.get("extend", []):
            cand, ext_derived = pick_notes(notes, ext["library"], ext["instrument"], art)
            if not cand:
                continue
            # "range": fill only beyond the primary's pitch span; "layers": also fill holes inside a
            # dynamic layer (the extension's layers are spread over the primary's by rank)
            ext_layers = order_layers(cand)
            prim_layers = raw_layers["primary"]
            n_dyn = len(LAYER_DYNAMICS[len(prim_layers)])

            def ext_layer(n: dict) -> int:
                r = ext_layers.index(n["dyn"])
                return int(round(r * (n_dyn - 1) / max(1, len(ext_layers) - 1)))
            if ext.get("fill", "range") == "layers":
                have_by = {li: {n["midi"] for n in chosen if prim_layers.index(n["dyn"]) == li} for li in range(n_dyn)}
                fill = [n for n in cand if lo - EXTEND_BEYOND <= n["midi"] <= hi + EXTEND_BEYOND
                        and min([abs(n["midi"] - h) for h in have_by[ext_layer(n)]] or [99]) > EXTEND_BEYOND]
            else:
                have = {n["midi"] for n in chosen}
                fill = [n for n in cand if lo - EXTEND_BEYOND <= n["midi"] <= hi + EXTEND_BEYOND
                        and min(abs(n["midi"] - h) for h in have) > EXTEND_BEYOND]
            if not fill:
                continue
            # fit the spectral match on the middle layers of both sources, at the pitches both have
            mid_p = raw_layers["primary"][len(raw_layers["primary"]) // 2]
            mid_e = ext_layers[len(ext_layers) // 2]
            prim = [(n["midi"], y) for n, y in zip(chosen, audio_of) if n["dyn"] == mid_p and n["rr"] == 1]
            pm = {m for m, _ in prim}
            ref = [(n["midi"], apply_eq(trim(load_segment(n)), eq)) for n in cand
                   if n["dyn"] == mid_e and n["rr"] == 1 and n["midi"] in pm]
            if len(ref) < 3:  # middle layers do not overlap in pitch: fit on every layer
                prim = [(n["midi"], y) for n, y in zip(chosen, audio_of) if n["rr"] == 1]
                pm = {m for m, _ in prim}
                ref = [(n["midi"], apply_eq(trim(load_segment(n)), eq)) for n in cand if n["rr"] == 1 and n["midi"] in pm]
            fir, info = match_filter(prim, ref)
            tag = f"{ext['library']}/{ext['instrument']}"
            raw_layers[tag] = ext_layers
            for n in fill:
                y = apply_eq(trim(load_segment(n)), eq)
                chosen.append(dict(n, _src=tag, _derived=ext_derived))
                audio_of.append(apply_fir(y, fir) if fir is not None else y)
            extensions.append({"source": ext, "notes": sorted({n["midi"] for n in fill}), "match": info})
        layers = raw_layers["primary"]
        dyns = (spec.get("dynamics") if art == "sus" else None) or LAYER_DYNAMICS[len(layers)]  # a target may name its sustain layers
        vels = velocity_ranges(dyns)
        pedal_fill(chosen, audio_of, raw_layers, len(dyns), lo, loops=art == "sus")
        lidx = [layer_of(n, raw_layers, len(dyns)) for n in chosen]
        scaled = [y * 10 ** ((DYN_LEVEL_DB[dyns[lidx[i]]] - (body_db(y) if art == "sus" else loudest_window_db(y, win=0.08))) / 20)
                  for i, y in enumerate(audio_of)]
        if target_gain_db is None:  # set once per target, from the sustain's middle layer
            # every primary sample in the comfortable range, referred to the middle layer's nominal level
            # (some sources have no middle-layer notes there, e.g. Iowa horn mf stops at B2)
            mid = DYN_LEVEL_DB[dyns[len(dyns) // 2]]
            ks = [body_db(k_weight(y)) - (DYN_LEVEL_DB[dyns[lidx[i]]] - mid) for i, y in enumerate(scaled)
                  if clo <= chosen[i]["midi"] <= chi and chosen[i]["_src"] == "primary"]
            target_gain_db = TARGET_K_DB - float(np.mean(ks))
        samples = []
        limited = []
        for i, n in enumerate(chosen):
            li = lidx[i]
            y = scaled[i] * 10 ** (target_gain_db / 20)
            peak = np.abs(y).max()
            if peak > MAX_PEAK:  # a few loud low ff notes peak high: limit those alone, keep 1 dB headroom
                y *= MAX_PEAK / peak
                limited.append(round(float(20 * np.log10(peak / MAX_PEAK)), 1))
            loop = None
            if art == "sus":
                y, loop = make_loop(y, vibrato=spec.get("vibrato", False))
            elif derived or n.get("_derived"):  # staccato made from a sustain: keep the first 0.6 s
                y = y[: int(0.6 * SR)].copy()
                f = int(0.05 * SR)
                y[-f:] *= np.linspace(1, 0, f)
            ext_tag = ("" if n["_src"] == "primary" else "_x") + ("_pd" if n.get("_pedal") else "")
            name = f"{tid}_{art}_{n['midi']:03d}_{dyns[li]}_rr{n['rr']}{ext_tag}.wav"
            sf.write(str(out / "samples" / name), y.astype(np.float32), SR, subtype="PCM_24")
            samples.append({"file": name, "midi": n["midi"], "cents": n["cents"], "layer": li, "rr": n["rr"],
                            "loop": [int(v) for v in loop] if loop else None, "frames": len(y),
                            "source": f"{n['file']}" + (f"@{n['start']}-{n['end']}" if n["kind"] == "run" else ""),
                            **({"extension": n["_src"]} if n["_src"] != "primary" else {}),
                            **({"pedal_from": n["_pedal"]} if n.get("_pedal") else {})})
        regions = []
        for li, dyn in enumerate(dyns):
            for k in range(lo, hi + 1):
                # same layer within MAX_STRETCH first; then any layer within MAX_STRETCH (nearest layer
                # first); a longer stretch only when no layer has a sample that close
                def cost(s, k=k, li=li):
                    d = abs(s["midi"] - k)
                    return d + (0 if s["layer"] == li else MAX_STRETCH + abs(s["layer"] - li)) + (10 if d > MAX_STRETCH else 0)
                cands = [s for s in samples if s["rr"] == 1] or samples
                best = min(cands, key=cost)
                variants = sorted([s for s in samples if s["midi"] == best["midi"] and s["layer"] == best["layer"]],
                                  key=lambda s: s["rr"])
                # a borrowed sample plays at this layer's level (the gain is baked into a copy below)
                vol = DYN_LEVEL_DB[dyn] - DYN_LEVEL_DB[dyns[best["layer"]]]
                key = (best["file"], round(vol, 2))
                if regions and regions[-1]["_key"] == key and regions[-1]["layer"] == li and regions[-1]["hikey"] == k - 1:
                    regions[-1]["hikey"] = k
                    continue
                regions.append({"_key": key, "layer": li, "dynamic": dyn, "lokey": k, "hikey": k,
                                "lovel": vels[li][0], "hivel": vels[li][1], "volume_db": round(vol, 2),
                                "variants": [s["file"] for s in variants], "pitch_keycenter": best["midi"],
                                "tune": int(round(-best["cents"])), "loop": best["loop"]})
        for r in regions:
            r.pop("_key")
        # A sample borrowed from another layer is brought to this layer's level. Engines disagree on
        # zone attenuation (FluidSynth applies 0.4 of SF2 initialAttenuation, AVAudioUnitSampler
        # almost none) and SF2 cannot boost, so the gain is baked into a copy of the sample instead.
        copies: dict[tuple[str, float], str] = {}
        for r in regions:
            if not r["volume_db"]:
                continue
            new = []
            for f in r["variants"]:
                key = (f, r["volume_db"])
                if key not in copies:
                    src_s = next(s_ for s_ in samples if s_["file"] == f)
                    name = f"{f[:-4]}_gain{int(round(r['volume_db'] * 10)):+d}.wav"
                    y, _ = sf.read(str(out / "samples" / f), dtype="float64")
                    y = y * 10 ** (r["volume_db"] / 20)
                    y = y * min(1.0, MAX_PEAK / (np.abs(y).max() + 1e-12))
                    sf.write(str(out / "samples" / name), y.astype(np.float32), SR, subtype="PCM_24")
                    samples.append({**src_s, "file": name, "gain_db": r["volume_db"], "copy_of": f})
                    copies[key] = name
                new.append(copies[key])
            r["variants"] = new
            r["volume_db"] = 0.0
        if art == "sus":
            # Calibrate on what actually plays: velocity 80 (the score default) over the comfortable
            # range, each key's region sample K-weighted, with the region's volume. The whole target
            # (sustain and staccato) moves by the difference to TARGET_K_DB.
            v80 = next(i for i, (a_, b_) in enumerate(vels) if a_ <= 80 <= b_)
            by_file = {s_["file"]: s_ for s_ in samples}
            kcache: dict[str, float] = {}
            lv = []
            for r in regions:
                if r["layer"] != v80:
                    continue
                f = r["variants"][0]
                if f not in kcache:
                    y, _ = sf.read(str(out / "samples" / f), dtype="float64")
                    kcache[f] = body_db(k_weight(y))
                lv += [kcache[f] + r["volume_db"]] * sum(1 for k in range(r["lokey"], r["hikey"] + 1) if clo <= k <= chi)
            corr = TARGET_K_DB - float(np.mean(lv))
            target_gain_db += corr
            for s_ in samples:
                path = out / "samples" / s_["file"]
                y, _ = sf.read(str(path), dtype="float64")
                y *= 10 ** (corr / 20)
                peak = np.abs(y).max()
                if peak > MAX_PEAK:
                    y *= MAX_PEAK / peak
                    limited.append(round(float(20 * np.log10(peak / MAX_PEAK)), 1))
                sf.write(str(path), y.astype(np.float32), SR, subtype="PCM_24")
            table["k_level_db_v80"] = round(float(np.mean(lv)) + corr, 2)
        table["articulations"][art] = {
            "source": src, "derived_from_sustain": derived, "layers": dyns, "raw_layers": layers,
            "velocity": vels, "release_s": RELEASE_S[art], "sf2_release_s": SF2_RELEASE_S[art],
            "samples": samples, "regions": regions, "extensions": extensions,
            "peak_limited_db": sorted(limited, reverse=True),
        }
    table["target_gain_db"] = round(float(target_gain_db), 2)
    (out / "regions.json").write_text(json.dumps(table, indent=1))
    for art in ("sus", "stac"):
        write_sfz(out / f"{tid}-{art}.sfz", tid, art, table)
    write_target_sf2(out / f"{tid}.sf2", tid, table)
    return table


def vel_curve_db(v: float) -> float:
    """VEL_CURVE at velocity v, dB relative to velocity 127."""
    if v >= VEL_CURVE_KNEE:
        return -VEL_CURVE_DB_PER_MARK * (127 - v) / 16
    return -VEL_CURVE_DB_PER_MARK * (127 - VEL_CURVE_KNEE) / 16 + 20 * float(np.log10(v / VEL_CURVE_KNEE))


def velcurve_opcodes() -> str:
    pts = [1, 8, 16, 24, VEL_CURVE_KNEE] + list(range(47, 127, 16)) + [127]
    return " ".join(f"amp_velcurve_{v}={10 ** (vel_curve_db(v) / 20):.4f}" for v in pts)


def write_sfz(path: Path, tid: str, art: str, table: dict) -> None:
    a = table["articulations"][art]
    lines = [
        f"// {tid} ({art}) for {table['instrument']}, generated by sounds/build.py from sounds/mapping.json. Do not edit.",
        f"// Sources: {a['source']['library']} {a['source']['instrument']}; licences in sounds/manifest.json.",
        "<control>", "default_path=samples/",
        "<global>", f"ampeg_attack=0.002 ampeg_release={a['release_s']} amp_veltrack=100 {velcurve_opcodes()}",
    ]
    for r in a["regions"]:
        n = len(r["variants"])
        for pos, file in enumerate(r["variants"], start=1):
            s = next(s for s in a["samples"] if s["file"] == file)
            op = [f"sample={file}", f"lokey={r['lokey']}", f"hikey={r['hikey']}", f"pitch_keycenter={r['pitch_keycenter']}",
                  f"lovel={r['lovel']}", f"hivel={r['hivel']}"]
            if r["tune"]:
                op.append(f"tune={r['tune']}")
            if r["volume_db"]:
                op.append(f"volume={r['volume_db']}")
            if n > 1:
                op.append(f"seq_length={n} seq_position={pos}")
            if s["loop"]:
                op.append(f"loop_mode=loop_continuous loop_start={s['loop'][0]} loop_end={s['loop'][1] - 1}")
            else:
                op.append("loop_mode=no_loop")
            lines.append("<region> " + " ".join(op))
    path.write_text("\n".join(lines) + "\n")


def write_target_sf2(path: Path, tid: str, table: dict) -> None:
    samples: list[sf2.Sample] = []
    index: dict[str, int] = {}
    presets = []
    for program, art in enumerate(("sus", "stac")):
        a = table["articulations"][art]
        ins = sf2.Instrument(name=f"{tid}-{art}", release_s=a["sf2_release_s"], vel_span_db=VEL_SPAN_DB)
        for r in a["regions"]:
            file = r["variants"][0]
            if file not in index:
                s = next(s for s in a["samples"] if s["file"] == file)
                data, _ = sf.read(str(path.parent / "samples" / file), dtype="float64")
                index[file] = len(samples)
                samples.append(sf2.Sample(name=file[:-4][-19:], data=data, rate=SR, root=s["midi"],
                                          cents=int(round(-s["cents"])),
                                          loop=tuple(s["loop"]) if s["loop"] else None))
            ins.zones.append(sf2.Zone(sample=index[file], lokey=r["lokey"], hikey=r["hikey"], lovel=r["lovel"],
                                      hivel=r["hivel"], attenuation_cb=int(round(-r["volume_db"] * 10)),
                                      loop=bool(r["loop"])))
        presets.append((f"{tid} {art}", program, ins))
    sf2.write_sf2(str(path), tid, samples, presets)


def main() -> None:
    mapping = json.loads(MAPPING.read_text())
    notes = json.loads(ANALYSIS.read_text())
    only = set(sys.argv[1:])
    summary = {}
    for tid, spec in mapping["targets"].items():
        if only and tid not in only:
            continue
        t = build_target(tid, spec, notes)
        for art, a in t["articulations"].items():
            ks = sorted({s["midi"] for s in a["samples"]})
            loops = sum(1 for s in a["samples"] if s["loop"])
            print(f"{tid:15s} {art:4s} {len(a['samples']):3d} samples, notes {ks[0]}-{ks[-1]}, layers {a['layers']}"
                  f" (raw {a['raw_layers']}), rr max {max(s['rr'] for s in a['samples'])}, loops {loops},"
                  f" regions {len(a['regions'])}{' [from sustain]' if a['derived_from_sustain'] else ''}")
        summary[tid] = {"range": t["range"], "sfz": [f"{tid}/{tid}-sus.sfz", f"{tid}/{tid}-stac.sfz"], "sf2": f"{tid}/{tid}.sf2"}
    index = BUILT / "targets.json"
    merged = json.loads(index.read_text()) if index.exists() else {}
    merged.update(summary)  # building a subset keeps the other targets listed
    index.write_text(json.dumps(merged, indent=1))


if __name__ == "__main__":
    main()
