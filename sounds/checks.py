"""Sanity checks on built instruments and renders.

    uv run --project sounds python sounds/checks.py loops                  # loop seams of every built sample
    uv run --project sounds python sounds/checks.py balance RUN [RUN ...]  # integrated LUFS per dry stem
    uv run --project sounds python sounds/checks.py coverage               # lineup x part coverage matrix; fails on gaps
    uv run --project sounds python sounds/checks.py phrases RUN [RUN ...]  # soundcheck renders; fails on clicks etc.

coverage: every part of every lineup (mapping.json `lineups`) must resolve by name to its own
preset in the band SoundFont, built only from our targets (never the General MIDI kit), with
zones for every key of the instrument's professional range at every velocity, no key in the
comfortable range more than MAX_STRETCH_COMFORTABLE semitones from its sample, every sustain
sample looped, and a release of at least MIN_SF2_RELEASE_S. It prints the coverage matrix.
phrases: runs sounds/soundcheck.py analyse and fails on any click, chop, dropout or gap,
clipped sample, a median release under MIN_RELEASE_MS, a velocity response that is not
monotonic, or (band SoundFont runs) a part more than BALANCE_TOL_LU off its balance_lu.

loops: for each looped sample, the step at the jump |y[end-1] -> y[start]| relative to the
99th percentile of the sample-to-sample steps in the 40 ms before the jump (> 1 means the jump
is a bigger discontinuity than the waveform itself ever makes, i.e. a potential click), and the correlation of 10 ms before the loop end with 10 ms before the loop start
(what the crossfade makes the jump sound like). Outliers are listed.
balance: per-part loudness relative to the loudest part, side by side for each run, to catch
sections that end up far quieter or louder than in the baseline.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np
import pyloudnorm
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "music" / "src"))
from dsp import SR  # noqa: E402

BUILT = Path(os.environ.get("BRASSCRIBE_SOUNDS_BUILT", HERE.parent / "data" / "sounds" / "built"))
BAND_SF2 = BUILT.parent / "band" / "brasscribe-band.sf2"
MAX_STRETCH_COMFORTABLE = 3
MIN_SF2_RELEASE_S = 0.4
MIN_RELEASE_MS = 150.0
BALANCE_TOL_LU = 2.0


def loops() -> None:
    rows = []
    for regions in sorted(BUILT.glob("*/regions.json")):
        t = json.loads(regions.read_text())
        for s in t["articulations"]["sus"]["samples"]:
            if not s["loop"]:
                continue
            a, b = s["loop"]
            y, _ = sf.read(str(regions.parent / "samples" / s["file"]), dtype="float64")
            w = int(0.01 * SR)
            natural = np.abs(np.diff(y[b - 4 * w : b]))
            step = abs(y[a] - y[b - 1]) / (np.percentile(natural, 99) + 1e-12)
            # the audio heard across the jump is y[b-w:b] followed by y[a:a+w]; compare with the
            # natural continuation y[a-w:a] -> y[a:a+w]
            pre_end, pre_start = y[b - w : b], y[a - w : a]
            corr = float(np.dot(pre_end, pre_start) / (np.linalg.norm(pre_end) * np.linalg.norm(pre_start) + 1e-12))
            rows.append((t["target"], s["file"], step, corr))
    steps = np.array([r[2] for r in rows])
    corrs = np.array([r[3] for r in rows])
    print(f"{len(rows)} loops: step/p99-natural median {np.median(steps):.3f}, p99 {np.percentile(steps, 99):.3f}, max {steps.max():.3f}; "
          f"seam correlation median {np.median(corrs):.3f}, p1 {np.percentile(corrs, 1):.3f}, min {corrs.min():.3f}")
    bad = [r for r in rows if r[2] > 1.0 or r[3] < 0.9]
    for r in bad:
        print(f"  check {r[0]:15s} {r[1]:40s} step {r[2]:.2f} corr {r[3]:.3f}")
    print(f"{len(bad)} outliers (jump step above the largest natural step, or correlation < 0.9)")


def balance(runs: list[str]) -> None:
    meter = pyloudnorm.Meter(SR)
    table: dict[str, dict[str, float]] = {}
    for run in runs:
        for stem in sorted((Path(run) / "stems").glob("*.wav")):
            x, _ = sf.read(str(stem), dtype="float64")
            table.setdefault(stem.stem, {})[Path(run).name] = meter.integrated_loudness(x)
    names = [Path(r).name for r in runs]
    top = {n: max(v[n] for v in table.values() if n in v) for n in names}
    print(f"{'part':16s} " + " ".join(f"{n[:12]:>12s}" for n in names) + "   (LU relative to the loudest part)")
    for part, v in table.items():
        print(f"{part:16s} " + " ".join(f"{v.get(n, float('nan')) - top[n]:+12.1f}" for n in names))


def coverage() -> int:
    import partsound
    from brasscribe_music.instruments import INSTRUMENTS
    from sf3 import SoundFontReader
    mapping = json.loads((HERE / "mapping.json").read_text())
    sf = SoundFontReader(str(BAND_SF2))
    presets = {(p.bank, p.program): p for p in sf.presets()}
    problems = []
    rows = []
    for lineup, names in mapping["lineups"].items():
        if lineup == "about":
            continue
        for name in names:
            r = partsound.resolve(name, mapping)
            part = mapping["parts"][r.part]
            inst = INSTRUMENTS[part["instrument"]]
            pr = presets.get((r.bank, r.program))
            if pr is None:
                problems.append(f"{lineup}/{name}: no preset bank {r.bank} program {r.program} in {BAND_SF2.name}")
                continue
            if inst.id == "drum-kit":
                rows.append((lineup, name, f"bank 128 kit '{pr.name}'", "GM drum kit (MS Basic, MIT)", "-", "-", "-", "-"))
                continue
            inames = [sf.instrument(z.ref).name for z in pr.zones if z.ref is not None]
            targets = [n.rsplit("-", 1)[0] for n in inames]
            bad = [n for n in inames if n.rsplit("-", 1)[0] not in mapping["targets"]]
            if bad:
                problems.append(f"{lineup}/{name}: preset uses non-target instruments {bad}")
            worst_c, worst_p, unlooped, rel = 0, 0, 0, 9.0
            sources = set()
            for tid in dict.fromkeys(targets):
                t = json.loads((BUILT / tid / "regions.json").read_text())
                a = t["articulations"]["sus"]
                rel = min(rel, a.get("sf2_release_s", a["release_s"]))
                by_file = {s_["file"]: s_ for s_ in a["samples"]}
                covered = {v: set() for v in range(1, 128)}
                for reg in a["regions"]:
                    s_ = by_file[reg["variants"][0]]
                    sources.add(s_.get("extension", f"{a['source']['library']}/{a['source']['instrument']}"))
                    if not s_["loop"]:
                        unlooped += 1
                    for k in range(reg["lokey"], reg["hikey"] + 1):
                        d = abs(k - reg["pitch_keycenter"])
                        if inst.comfortable[0] <= k <= inst.comfortable[1]:
                            worst_c = max(worst_c, d)
                        if inst.pro[0] <= k <= inst.pro[1]:
                            worst_p = max(worst_p, d)
                        for v in range(reg["lovel"], reg["hivel"] + 1):
                            covered[v].add(k)
                holes = sorted({k for v in covered for k in range(inst.pro[0], inst.pro[1] + 1) if k not in covered[v]})
                if holes:
                    problems.append(f"{lineup}/{name}: {tid} has no zone for keys {holes[:8]}")
                layers = len(a["layers"])
            if worst_c > MAX_STRETCH_COMFORTABLE:
                problems.append(f"{lineup}/{name}: a comfortable-range key is {worst_c} semitones from its sample")
            if unlooped:
                problems.append(f"{lineup}/{name}: {unlooped} sustain zones play an unlooped sample")
            if rel < MIN_SF2_RELEASE_S:
                problems.append(f"{lineup}/{name}: SF2 release {rel} s")
            rows.append((lineup, name, f"bank {r.bank} program {r.program} '{pr.name}'", "+".join(dict.fromkeys(targets)),
                         ", ".join(sorted(sources)), str(layers), f"{worst_c}/{worst_p}", f"{rel:.2f}"))
    print(f"{'lineup':14s} {'part':15s} {'preset':34s} {'targets':20s} {'layers':6s} {'stretch c/p':11s} {'rel s':5s}  sources")
    for r in rows:
        print(f"{r[0]:14s} {r[1]:15s} {r[2]:34s} {r[3]:20s} {r[5]:6s} {r[6]:11s} {r[7]:5s}  {r[4]}")
    for p in problems:
        print("FAIL", p)
    print(f"{len(rows)} lineup parts, {len(problems)} problems")
    return 1 if problems else 0


def phrases(runs: list[str]) -> int:
    import soundcheck
    mapping = json.loads((HERE / "mapping.json").read_text())
    reports = soundcheck.analyse(runs)
    problems = []
    for run, rep_ in reports.items():
        band_run = "band" in Path(run).name or "avsampler" in run or "alphatab" in run or "mobile" in run
        lv = {}
        for name, r in rep_.items():
            for key in ("clicks", "chops", "dropouts"):
                if r[key]:
                    problems.append(f"{run} {name}: {len(r[key])} {key}, first {r[key][0]}")
            if r["clipped_samples"]:
                problems.append(f"{run} {name}: {r['clipped_samples']} clipped samples")
            if r["release_ms_median"] is not None and r["release_ms_median"] < MIN_RELEASE_MS:
                problems.append(f"{run} {name}: median release {r['release_ms_median']} ms")
            dyn = r.get("dynamics_db") or []
            if any(b < a - 0.5 for a, b in zip(dyn, dyn[1:])):
                problems.append(f"{run} {name}: velocity response not monotonic {dyn}")
            if r["level_lufs"] is not None:
                bs = mapping["parts"][name]["band_soundfont"]
                gain = bs["single_voice_gain_db"] if "mobile" in run else bs["channel_gain_db"]
                lv[name] = r["level_lufs"] + gain - mapping["parts"][name]["balance_lu"]
        if band_run and lv:
            ref = float(np.median(list(lv.values())))
            for name, v in lv.items():
                if abs(v - ref) > BALANCE_TOL_LU:
                    problems.append(f"{run} {name}: {v - ref:+.1f} LU off its balance_lu with channel gain applied")
    for p in problems:
        print("FAIL", p)
    print(f"{len(problems)} problems")
    return 1 if problems else 0


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "loops":
        loops()
    elif cmd == "coverage":
        sys.exit(coverage())
    elif cmd == "phrases":
        sys.exit(phrases(sys.argv[2:]))
    else:
        balance(sys.argv[2:])
