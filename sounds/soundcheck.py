"""Render the test phrases through every engine and measure clicks, chops, dropouts, clipping and balance.

    uv run --project sounds python sounds/phrases.py                      # the MIDI material
    uv run --project sounds python sounds/soundcheck.py render ENGINE -o RUN   # per-part WAVs
    uv run --project sounds python sounds/soundcheck.py analyse RUN [RUN ...]  # table + RUN/report.json

ENGINE is one of
  sfizz           the per-target SFZ via sfizz_render (the offline reference, Android realistic tier)
  fluid-band      the band SoundFont via FluidSynth (SF2 semantics shared with alphaTab and AVAudioUnitSampler)
  fluid-mobile    the phone SoundFont via FluidSynth
  fluid-gm        MS Basic (General MIDI) via FluidSynth: what a part sounds like when it falls back to GM
  WAV:DIR         WAVs rendered elsewhere (e.g. by the AVAudioUnitSampler or alphaTab harness), one per part

What is measured, per part, from the note list in phrases.json (never guessed from the audio):
  clicks     second-difference spikes more than CLICK_RATIO times the largest one in the 60 ms
             on either side, away from note onsets (an onset is allowed its attack transient)
  chops      note-offs followed by silence where the level falls 40 dB in under CHOP_MS: a hard cut
             instead of a release
  release    median time from note-off to 40 dB below the note's level (the audible tail)
  dropouts   held notes (>= 0.5 s) whose level falls 20 dB below their own median before the
             note-off (the sample ran out, a loop failed, or the voice was stolen), and gaps: a
             1 ms frame of a held note (>= 0.3 s) 40 dB below the 40 ms around it (an underrun)
  clipping   samples at or above 0.999 full scale
  level      integrated loudness of the three sustained mf notes (LUFS), for the balance table
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
from dsp import SR  # noqa: E402

DATA = ROOT / "data" / "sounds"
PHRASES = DATA / "phrases"
SFIZZ = DATA / "tools" / "bin" / "sfizz_render"
BUILT = Path(os.environ.get("BRASSCRIBE_SOUNDS_BUILT", DATA / "built"))  # a staging build: its band/ sits next to it
BAND_SF2 = BUILT.parent / "band" / "brasscribe-band.sf2"
MOBILE_SF2 = BUILT.parent / "band" / "brasscribe-band-mobile.sf2"
MSBASIC = DATA / "raw" / "msbasic" / "MS Basic.sf3"

CLICK_RATIO = 3.0
CLICK_FLOOR = 2e-4  # ignore second-difference spikes below this absolute size (inaudible)
ONSET_GUARD_S = 0.03
CHOP_MS = 12.0
DROPOUT_DB = 20.0
GAP_DB = 40.0
MIN_RELEASE_MS = 60.0

# Balance target, LU relative to Solo Cornet, for one player of each part at mf (the mapping's
# per-part gains then add the desk size). Brass-band practice: cornets and basses carry the band,
# the flugel and solo horn sit just under the solo cornet, the middle band a little lower,
# the euphonium near the cornets as the second soloist. Tolerance is TOL_LU either way.
BALANCE_TARGET_LU = {
    "Soprano Cornet": -2.0, "Solo Cornet": 0.0, "Repiano Cornet": -2.0, "2nd Cornet": -3.0, "3rd Cornet": -3.0,
    "Flugelhorn": -2.0, "Solo Horn": -2.0, "1st Horn": -3.0, "2nd Horn": -3.0, "1st Baritone": -3.0,
    "2nd Baritone": -3.0, "1st Trombone": -2.0, "2nd Trombone": -3.0, "Bass Trombone": -3.0, "Euphonium": -1.0,
    "E♭ Bass": -2.0, "B♭ Bass": -2.0, "1st Cornet": 0.0, "Tenor Horn": -2.0,
}
TOL_LU = 3.0


def slug(name: str) -> str:
    return name.replace("♭", "b").replace(" ", "-").lower()


# ------------------------------------------------------------------ rendering

def render(engine: str, out: Path) -> None:
    meta = json.loads((PHRASES / "phrases.json").read_text())
    mapping = json.loads((HERE / "mapping.json").read_text())
    out.mkdir(parents=True, exist_ok=True)
    for name, p in meta["parts"].items():
        midi = PHRASES / p["file"]
        wav = out / f"{slug(name)}.wav"
        if engine == "sfizz":
            target = mapping["parts"][name]["players"][0]["target"]
            sfz = BUILT / target / f"{target}-sus.sfz"
            with tempfile.TemporaryDirectory() as tmp:
                # sfizz ignores program changes: strip nothing, it plays channel 0 notes on the SFZ
                subprocess.run([str(SFIZZ), "--sfz", str(sfz), "--midi", str(midi), "--wav", str(Path(tmp) / "x.wav"),
                                "-s", str(SR), "-q", "3", "--use-eot"], check=True, capture_output=True)
                x, sr = sf.read(str(Path(tmp) / "x.wav"), dtype="float32")
                sf.write(str(wav), x, sr, subtype="FLOAT")
        elif engine.startswith("fluid-"):
            sf2 = {"fluid-band": BAND_SF2, "fluid-mobile": MOBILE_SF2, "fluid-gm": MSBASIC}[engine]
            src = midi
            if engine == "fluid-gm":  # GM fallback: the part's GM program, bank 0
                src = Path(tempfile.mkdtemp()) / "gm.mid"
                strip_bank(midi, src)
            subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.5", "-r", str(SR), "-F", str(wav),
                            str(sf2), str(src)], check=True, capture_output=True)
        else:
            raise SystemExit(f"unknown engine {engine}")
        print(f"  {engine}: {wav.name}")


def strip_bank(src: Path, dst: Path) -> None:
    import mido
    mid = mido.MidiFile(str(src))
    for tr in mid.tracks:
        keep = []
        carry = 0
        for m in tr:
            if m.type == "control_change" and m.control in (0, 32):
                carry += m.time
                continue
            m.time += carry
            carry = 0
            keep.append(m)
        tr[:] = keep
    mid.save(str(dst))


# ------------------------------------------------------------------ analysis

def mono(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    if sr != SR:
        import soxr
        x = soxr.resample(x, sr, SR)
    return x


def env_db(x: np.ndarray, hop: int) -> np.ndarray:
    n = len(x) // hop
    fr = x[: n * hop].reshape(n, hop)
    return 10 * np.log10(np.mean(fr ** 2, axis=1) + 1e-14)


def clicks(x: np.ndarray, onsets: list[float]) -> list[float]:
    """Isolated discontinuities: a second-difference spike CLICK_RATIO times larger than any in
    the 60 ms on either side (2 ms excluded). Brass waveforms are pulse trains whose every period
    has a similar spike, so they never stand out against their own neighbourhood; a loop seam, a
    hard cut or a buffer glitch does."""
    from scipy.ndimage import maximum_filter1d
    d2 = np.abs(np.diff(x, n=2))
    w, g = int(0.06 * SR), int(0.002 * SR)  # 60 ms: longer than the period of the lowest pedal note (A0)
    m = maximum_filter1d(d2, size=w, origin=0)
    # max over [i-g-w, i-g) and (i+g, i+g+w]: shift a centred max filter of width w
    before = np.roll(m, g + w // 2)
    after = np.roll(m, -(g + w // 2))
    ref = np.maximum(before, after)
    idx = np.nonzero((d2 > CLICK_RATIO * (ref + 1e-12)) & (d2 > CLICK_FLOOR))[0]
    ons = np.array(sorted(onsets))
    out: list[float] = []
    for i in idx:
        t = (i + 1) / SR
        if len(ons):
            j = np.searchsorted(ons, t)
            prev = ons[j - 1] if j > 0 else -1e9
            if 0 <= t - prev < ONSET_GUARD_S or (j < len(ons) and abs(ons[j] - t) < 0.005):
                continue
        if out and t - out[-1] < 0.02:
            continue
        out.append(t)
    return out


def gaps(x: np.ndarray, notes: list) -> list[dict]:
    """Short silences inside held notes (an underrun, a stolen voice, a failed loop): a 1 ms RMS
    frame more than GAP_DB below the median of the 40 ms around it."""
    from scipy.ndimage import median_filter
    hop = int(0.001 * SR)
    e = env_db(x, hop)
    ref = median_filter(e, size=41, mode="nearest")
    out = []
    for s, en, p, _ in notes:
        if en - s < 0.3:
            continue
        a, b = int((s + 0.1) * SR / hop), int((en - 0.02) * SR / hop)
        seg, r = e[a:b], ref[a:b]
        hit = np.nonzero((seg < r - GAP_DB) & (r > -70))[0]
        if len(hit):
            out.append({"t": round((a + int(hit[0])) * hop / SR, 3), "pitch": p, "depth_db": round(float((r - seg)[hit].max()), 1)})
    return out


def analyse_part(wav: Path, part: dict) -> dict:
    x2 = mono(wav)
    peak = float(np.abs(x2).max())
    clip = int(np.sum(np.abs(x2) >= 0.999))
    x = x2.mean(axis=1)
    notes = sorted(part["notes"])
    onsets = [n[0] for n in notes]
    hop = int(0.005 * SR)
    e = env_db(x, hop)

    def lvl(t0: float, t1: float) -> np.ndarray:
        return e[int(t0 * SR / hop): max(int(t0 * SR / hop) + 1, int(t1 * SR / hop))]

    releases, chops, drops = [], [], []
    for i, (s, en, p, v) in enumerate(notes):
        nxt = min([n[0] for n in notes if n[0] > s + 1e-3] or [1e9])
        if en - s >= 0.5:  # held note: dropout check
            seg = lvl(s + 0.15, en - 0.03)
            if len(seg) > 4:
                med = float(np.median(seg))
                if med > -80 and seg.min() < med - DROPOUT_DB:
                    drops.append({"t": round(s + 0.15 + float(np.argmin(seg)) * hop / SR, 3), "pitch": p,
                                  "depth_db": round(med - float(seg.min()), 1)})
        if nxt - en >= 0.25 and en - s >= 0.08:  # isolated note-off: release tail
            ref = lvl(en - 0.04, en)
            if not len(ref):
                continue
            ref_db = float(ref.max())
            if ref_db < -70:
                continue
            tail = lvl(en, min(nxt, en + 1.5))
            below = np.nonzero(tail < ref_db - 40)[0]
            rel_ms = (below[0] * hop / SR * 1000) if len(below) else 1500.0
            releases.append(rel_ms)
            if rel_ms < CHOP_MS or rel_ms < MIN_RELEASE_MS and en - s >= 0.3:
                chops.append({"t": round(en, 3), "pitch": p, "release_ms": round(rel_ms, 1)})
    drops += gaps(x, notes)
    cl = clicks(x, onsets)
    meter = pyloudnorm.Meter(SR)
    sus = [n for n in notes if n[1] - n[0] >= 5.9 and n[3] == 80][:3]
    level = None
    if sus:
        segs = [x2[int((s + 0.3) * SR): int((en - 0.1) * SR)] for s, en, _, _ in sus]
        level = float(meter.integrated_loudness(np.concatenate(segs)))
    return {"peak_dbfs": round(20 * np.log10(peak + 1e-12), 1), "clipped_samples": clip, "clicks": [round(t, 3) for t in cl],
            "chops": chops, "dropouts": drops, "release_ms_median": round(float(np.median(releases)), 1) if releases else None,
            "level_lufs": round(level, 1) if level is not None else None}


def analyse(runs: list[str]) -> dict:
    meta = json.loads((PHRASES / "phrases.json").read_text())
    reports = {}
    for run in runs:
        rep = {}
        for name, part in meta["parts"].items():
            wav = Path(run) / f"{slug(name)}.wav"
            if wav.exists():
                rep[name] = analyse_part(wav, part)
        ref = rep.get("Solo Cornet", {}).get("level_lufs")
        for name, r in rep.items():
            if ref is not None and r["level_lufs"] is not None:
                r["balance_lu"] = round(r["level_lufs"] - ref, 1)
        (Path(run) / "report.json").write_text(json.dumps(rep, indent=1, ensure_ascii=False))
        reports[run] = rep
        print(f"\n{run}")
        print(f"{'part':16s} {'peak':>6s} {'clip':>5s} {'click':>5s} {'chop':>5s} {'drop':>5s} {'rel ms':>7s} {'LU vs solo':>10s}")
        for name, r in rep.items():
            print(f"{name:16s} {r['peak_dbfs']:6.1f} {r['clipped_samples']:5d} {len(r['clicks']):5d} {len(r['chops']):5d} "
                  f"{len(r['dropouts']):5d} {r['release_ms_median'] or 0:7.0f} {r.get('balance_lu', float('nan')):+10.1f}")
    return reports


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("render")
    r.add_argument("engine")
    r.add_argument("-o", "--out", required=True)
    a = sub.add_parser("analyse")
    a.add_argument("runs", nargs="+")
    args = ap.parse_args()
    if args.cmd == "render":
        render(args.engine, Path(args.out))
    else:
        analyse(args.runs)


if __name__ == "__main__":
    main()
