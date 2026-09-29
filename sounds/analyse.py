"""Catalogue the raw samples: which note, dynamic, articulation and round robin each is.

    uv run --project sounds python sounds/analyse.py      # writes data/sounds/analysis.json

Pitch comes from the file name, corrected by one octave offset per (library, instrument,
kind) chosen by majority vote against a pYIN f0 estimate, so single octave errors in f0
(common for low tuba and horn) never move a key centre. The measured f0 gives the fine
tuning in cents. Iowa chromatic runs are segmented into single notes on silence gaps;
when the segment count equals the run's range the notes are taken in chromatic order
(the runs are strictly ascending), otherwise each segment's pitch comes from f0.
"""

from __future__ import annotations

import concurrent.futures as cf
import json
import os
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
from dsp import SR, envelope_db, hz_to_midi, midi_from_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "sounds" / "raw"
# BRASSCRIBE_SOUNDS_ANALYSIS: a staging catalogue, so a rebuild in one checkout leaves the shared one alone
OUT = Path(os.environ.get("BRASSCRIBE_SOUNDS_ANALYSIS", ROOT / "data" / "sounds" / "analysis.json"))

VSCO_INST = {"Trumpet": "trumpet", "F Horn": "horn", "Tenor Trombone": "tenor-trombone", "Tuba": "tuba"}
F0_RANGE = {  # Hz, generous: sounding ranges of the source instruments
    "trumpet": (130, 1500), "trumpet-vib": (130, 1500), "horn": (50, 1000), "tenor-trombone": (60, 700),
    "bass-trombone": (30, 450), "tuba": (25, 400),
}


def load_mono(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    if sr != SR:
        raise ValueError(f"{path}: {sr} Hz")
    return x.mean(axis=1)


def estimate_f0(x: np.ndarray, inst: str) -> float | None:
    """Median voiced f0 over the loudest ~1 s of the note."""
    lo, hi = F0_RANGE[inst]
    env = envelope_db(x)
    peak = int(np.argmax(env)) * int(SR * 0.01)
    a = max(0, peak - SR // 4)
    seg = x[a : a + SR]
    if len(seg) < SR // 5:
        seg = x
    frame = 8192 if lo < 60 else 4096
    if len(seg) < frame * 2:
        seg = np.pad(seg, (0, frame * 2 - len(seg)))
    f0, voiced, _ = librosa.pyin(seg, fmin=lo, fmax=hi, sr=SR, frame_length=frame)
    f0 = f0[voiced & ~np.isnan(f0)]
    return float(np.median(f0)) if len(f0) >= 3 else None


def segment_run(x: np.ndarray) -> list[tuple[int, int]]:
    """Split a chromatic run on silence. Returns (start, end) sample indices."""
    hop = int(SR * 0.01)
    env = envelope_db(x)
    floor = np.percentile(env, 10)
    thr = max(env.max() - 45, floor + 15)
    on = env > thr
    segs, i = [], 0
    while i < len(on):
        if on[i]:
            j = i
            while j < len(on) and (on[j] or np.any(on[j : j + 10])):  # bridge gaps < 100 ms
                j += 1
            if j - i >= 20:  # at least 200 ms
                segs.append([i, j])
            i = j
        else:
            i += 1
    out = []
    for k, (a, b) in enumerate(segs):
        start = max(0, a - 3) * hop
        nxt = segs[k + 1][0] * hop if k + 1 < len(segs) else len(x)
        tail = b
        while tail < len(env) and tail * hop < nxt - hop * 5 and env[tail] > thr - 20:
            tail += 1
        out.append((start, min(len(x), tail * hop)))
    return out


def parse_range(s: str) -> tuple[int, int]:
    names = re.findall(r"[A-G][b#]?\d", s)
    lo = midi_from_name(names[0])
    hi = midi_from_name(names[1]) if len(names) > 1 else lo
    return lo, hi


def catalogue() -> list[dict]:
    items = []
    for f in sorted((RAW / "vsco2ce" / "Brass").rglob("*.wav")):
        m = re.search(r"_(sus|stac|susvib)_([A-G]#?-?\d)_v(\d)(?:_rr(\d)|_(\d))?", f.name)
        if not m:
            continue
        vib = m.group(1) == "susvib"  # the vibrato sustains are their own instrument (the solo cornet's)
        items.append({
            "file": str(f.relative_to(RAW)), "library": "vsco2ce",
            "instrument": VSCO_INST[f.parent.parent.name] + ("-vib" if vib else ""),
            "kind": "sus" if vib else m.group(1), "art": "sus" if vib else m.group(1), "dyn": f"v{m.group(3)}",
            "rr": int(m.group(4) or m.group(5) or 1),
            "name_midi": midi_from_name(m.group(2)),
        })
    for f in sorted((RAW / "iowa-mis").glob("*/pitch/*.aif*")):
        m = re.search(r"\.(pp|mf|ff)\.([A-G]b?\d)\.", f.name)
        items.append({
            "file": str(f.relative_to(RAW)), "library": "iowa-mis", "instrument": f.parent.parent.name,
            "kind": "pitch", "art": "sus", "dyn": m.group(1), "rr": 1, "name_midi": midi_from_name(m.group(2)),
        })
    for f in sorted((RAW / "iowa-mis").glob("*/run/*.aif*")):
        m = re.search(r"\.(pp|mf|ff)\.([A-Gb#0-9]+)\.aif", f.name)
        items.append({
            "file": str(f.relative_to(RAW)), "library": "iowa-mis", "instrument": f.parent.parent.name,
            "kind": "run", "art": "sus", "dyn": m.group(1), "rr": 1, "range": parse_range(m.group(2)),
        })
    return items


def analyse_item(item: dict) -> list[dict]:
    x = load_mono(RAW / item["file"])
    if item["kind"] != "run":
        f0 = estimate_f0(x, item["instrument"])
        return [dict(item, start=0, end=len(x), f0=f0)]
    lo, hi = item["range"]
    segs = segment_run(x)
    out = []
    for k, (a, b) in enumerate(segs):
        f0 = estimate_f0(x[a:b], item["instrument"])
        out.append(dict(item, start=a, end=b, f0=f0, seq_index=k, seq_count=len(segs)))
    return out


def resolve(notes: list[dict]) -> None:
    """Fix octave naming per (library, instrument, kind) by vote; assign midi and fine tune."""
    groups = defaultdict(list)
    for n in notes:
        groups[(n["library"], n["instrument"], n["kind"])].append(n)
    for key, ns in groups.items():
        if key[2] == "run":
            for n in ns:
                lo, hi = n["range"]
                expected = hi - lo + 1
                if n["seq_count"] == expected:
                    n["midi"] = lo + n["seq_index"]
                    n["midi_source"] = "sequence"
                elif n["f0"]:
                    m = round(hz_to_midi(n["f0"]))
                    while m < lo - 1:
                        m += 12
                    while m > hi + 1:
                        m -= 12
                    n["midi"] = m if lo <= m <= hi else None
                    n["midi_source"] = "f0"
                else:
                    n["midi"] = None
            continue
        votes = Counter()
        for n in ns:
            if n["f0"]:
                votes[round((hz_to_midi(n["f0"]) - n["name_midi"]) / 12) * 12] += 1
        offset = votes.most_common(1)[0][0] if votes else 0
        for n in ns:
            n["octave_offset"] = offset
            n["midi"] = n["name_midi"] + offset
            n["midi_source"] = f"name{offset:+d}"
    for n in notes:
        if n.get("midi") is not None and n["f0"]:
            cents = (hz_to_midi(n["f0"]) - n["midi"]) * 100
            n["cents"] = round(cents, 1) if abs(cents) < 60 else 0.0  # beyond that the f0 is unreliable
            n["f0_octave_error"] = abs(cents) >= 60
        else:
            n["cents"] = 0.0


def main() -> None:
    items = catalogue()
    notes = []
    with cf.ProcessPoolExecutor() as ex:
        for res in ex.map(analyse_item, items, chunksize=4):
            notes.extend(res)
    resolve(notes)
    OUT.write_text(json.dumps(notes, indent=0))
    usable = [n for n in notes if n.get("midi") is not None]
    print(f"{len(items)} files -> {len(notes)} notes, {len(usable)} with pitch -> {OUT}")
    summary = Counter((n["library"], n["instrument"], n["kind"], n["dyn"], n.get("midi_source", "").split("-")[0])
                      for n in usable)
    for k, v in sorted(summary.items()):
        print("  ", k, v)
    offsets = {(n["library"], n["instrument"], n["kind"]): n.get("octave_offset") for n in usable if "octave_offset" in n}
    print("octave offsets:", offsets)
    bad = [n for n in usable if n.get("f0_octave_error")]
    print(f"f0 disagrees with the voted pitch by >60 cents on {len(bad)} notes (kept, tuning left at 0)")


if __name__ == "__main__":
    main()
