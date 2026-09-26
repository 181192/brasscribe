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
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(ROOT / "music" / "src"))
from brasscribe_music.instruments import INSTRUMENTS  # noqa: E402
from dsp import SR, apply_eq, envelope_db, loudest_window_db  # noqa: E402
import sf2  # noqa: E402

RAW = ROOT / "data" / "sounds" / "raw"
BUILT = ROOT / "data" / "sounds" / "built"
ANALYSIS = ROOT / "data" / "sounds" / "analysis.json"
MAPPING = HERE / "mapping.json"

# Nominal dynamic of each layer, by number of layers available (softest first).
LAYER_DYNAMICS = {1: ["mf"], 2: ["p", "f"], 3: ["pp", "mf", "ff"], 4: ["p", "mf", "f", "ff"]}
DYN_VELOCITY = {"pp": 30, "p": 48, "mf": 80, "f": 100, "ff": 116}
# Loudest 300 ms window RMS of each baked sample, dBFS.
DYN_LEVEL_DB = {"pp": -30.0, "p": -26.0, "mf": -21.0, "f": -18.5, "ff": -16.0}
VEL_SPAN_DB = 6.0  # extra dB-linear velocity scaling inside the layers (same in SFZ and SF2)
MAX_STRETCH = 3  # semitones a sample may be transposed before a neighbouring layer's sample is borrowed
RELEASE_S = {"sus": 0.20, "stac": 0.10}
DC_BLOCK = [{"type": "highpass", "f": 25, "q": 0.707}]


def velocity_ranges(dyns: list[str]) -> list[tuple[int, int]]:
    centres = [DYN_VELOCITY[d] for d in dyns]
    cuts = [(a + b) // 2 for a, b in zip(centres, centres[1:])]
    lows = [1] + [c + 1 for c in cuts]
    highs = cuts + [127]
    return list(zip(lows, highs))


def load_segment(note: dict) -> np.ndarray:
    x, sr = sf.read(str(RAW / note["file"]), dtype="float64", always_2d=True, start=note["start"], stop=note["end"])
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


def make_loop(x: np.ndarray) -> tuple[np.ndarray, tuple[int, int] | None]:
    """Crossfade loop in the stable sustain. Returns (audio cut after the loop, (start, end)) or no loop."""
    hop = int(0.01 * SR)
    env = envelope_db(x)
    peak = env.max()
    loud = np.nonzero(env > peak - 3)[0]
    if not len(loud):
        return x, None
    a_frame = loud[0] + 8
    stable = np.nonzero(env > peak - 9)[0]
    # loop within the first ~3 s of sustain: long enough for natural onset movement,
    # short enough to keep the instruments small
    b_frame = min(stable[-1] - 10, a_frame + 300)
    if (b_frame - a_frame) * hop < int(0.35 * SR):
        return x, None
    b = b_frame * hop
    length = min(int(1.2 * SR), int((b_frame - a_frame) * hop * 0.8))
    a = b - length
    # nudge the loop start to the best waveform match with the loop end
    w = 512
    ref = x[b - w : b]
    best, best_a = -np.inf, a
    for cand in range(a - 400, a + 400):
        if cand - w < 0:
            continue
        seg = x[cand - w : cand]
        c = float(np.dot(ref, seg) / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-12))
        if c > best:
            best, best_a = c, cand
    a = best_a
    xf = min(int(0.12 * SR), (b - a) // 2, a)
    y = x[: b + 64].copy()
    t = np.linspace(0, 1, xf)
    y[b - xf : b] = x[b - xf : b] * (1 - t) + x[a - xf : a] * t
    return y, (a, b)


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
    for art, src in (("sus", spec["source"]), ("stac", spec["stac_source"])):
        chosen, derived = pick_notes(notes, src["library"], src["instrument"], art)
        audio, levels = [], {}
        for i, n in enumerate(chosen):
            y = apply_eq(trim(load_segment(n)), eq)
            audio.append(y)
            levels[i] = loudest_window_db(y, win=0.3 if art == "sus" else 0.08)
        layers = order_layers(chosen)
        dyns = LAYER_DYNAMICS[len(layers)]
        vels = velocity_ranges(dyns)
        samples = []
        for i, n in enumerate(chosen):
            li = layers.index(n["dyn"])
            y = audio[i] * 10 ** ((DYN_LEVEL_DB[dyns[li]] - levels[i]) / 20)
            peak = np.abs(y).max()
            if peak > 0.89:  # keep 1 dB headroom
                y *= 0.89 / peak
            loop = None
            if art == "sus":
                y, loop = make_loop(y)
            elif derived:  # staccato made from a sustain: keep the first 0.6 s
                y = y[: int(0.6 * SR)].copy()
                f = int(0.05 * SR)
                y[-f:] *= np.linspace(1, 0, f)
            name = f"{tid}_{art}_{n['midi']:03d}_{dyns[li]}_rr{n['rr']}.wav"
            sf.write(str(out / "samples" / name), y.astype(np.float32), SR, subtype="PCM_24")
            samples.append({"file": name, "midi": n["midi"], "cents": n["cents"], "layer": li, "rr": n["rr"],
                            "loop": [int(v) for v in loop] if loop else None, "frames": len(y),
                            "source": f"{n['file']}" + (f"@{n['start']}-{n['end']}" if n["kind"] == "run" else "")})
        regions = []
        for li, dyn in enumerate(dyns):
            for k in range(lo, hi + 1):
                cost = lambda s: abs(s["midi"] - k) + (0 if s["layer"] == li else MAX_STRETCH + abs(s["layer"] - li))  # noqa: E731
                cands = [s for s in samples if s["rr"] == 1] or samples
                best = min(cands, key=cost)
                variants = sorted([s for s in samples if s["midi"] == best["midi"] and s["layer"] == best["layer"]],
                                  key=lambda s: s["rr"])
                # borrow louder samples attenuated; softer ones play at their own level (SF2 attenuation must be >= 0)
                vol = min(0.0, DYN_LEVEL_DB[dyn] - DYN_LEVEL_DB[dyns[best["layer"]]])
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
        table["articulations"][art] = {
            "source": src, "derived_from_sustain": derived, "layers": dyns, "raw_layers": layers,
            "velocity": vels, "release_s": RELEASE_S[art], "samples": samples, "regions": regions,
        }
    (out / "regions.json").write_text(json.dumps(table, indent=1))
    for art in ("sus", "stac"):
        write_sfz(out / f"{tid}-{art}.sfz", tid, art, table)
    write_target_sf2(out / f"{tid}.sf2", tid, table)
    return table


def velcurve_opcodes() -> str:
    pts = list(range(1, 127, 14)) + [127]
    return " ".join(f"amp_velcurve_{v}={10 ** (-VEL_SPAN_DB * (1 - v / 127) / 20):.4f}" for v in pts)


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
        ins = sf2.Instrument(name=f"{tid}-{art}", release_s=a["release_s"], vel_span_db=VEL_SPAN_DB)
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
