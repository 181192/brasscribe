"""Objective descriptors for the rendered tiers against real brass recordings.

    uv run --project sounds python sounds/descriptors.py RUN_DIR [RUN_DIR ...] --midi SCORE.mid -o report.json

For every part and tier (dry per-part stems written by render.py):
  * pitch check: pYIN f0 in the middle of every note longer than 0.3 s against the score
    pitch (share within 50 cents), which catches key-mapping and tuning errors;
  * spectral centroid per note, in Hz and in harmonics (centroid / f0), which removes most
    of the pitch dependence of a raw centroid.
Real references, restricted to the same pitch window as the part:
  URMP (trumpet, horn, trombone, tuba separated stems) and ChoraleBricks (trumpet,
  flugelhorn, baritone, French horn, trombone, tuba solo tracks). There is no real cornet,
  tenor horn or euphonium recording in either set; the nearest family member is used and
  named in the report.
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import librosa
import numpy as np
import soundfile as sf
import soxr

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from dsp import SR, spectral_centroid  # noqa: E402
from render import read_parts  # noqa: E402

ROOT = HERE.parent
URMP = ROOT / "data" / "urmp" / "Dataset"
CB = ROOT / "data" / "choralebricks" / "01_AudioAndAnnotations"

PART_REF = {
    "Soprano Cornet": "trumpet", "Solo Cornet": "trumpet", "Repiano Cornet": "trumpet", "2nd Cornet": "trumpet",
    "3rd Cornet": "trumpet", "Flugelhorn": "flugelhorn", "Solo Horn": "horn", "1st Horn": "horn", "2nd Horn": "horn",
    "1st Baritone": "baritone", "2nd Baritone": "baritone", "Euphonium": "baritone", "1st Trombone": "trombone",
    "2nd Trombone": "trombone", "Bass Trombone": "trombone", "E♭ Bass": "tuba", "B♭ Bass": "tuba",
}
URMP_CODE = {"tpt": "trumpet", "hn": "horn", "tbn": "trombone", "tba": "tuba"}
CB_NAME = {"Trumpet": "trumpet", "Flugelhorn": "flugelhorn", "Baritone": "baritone", "French horn": "horn",
           "Trombone": "trombone", "Tuba": "tuba"}


def load(path: Path) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    x = x.mean(axis=1)
    return soxr.resample(x, sr, SR) if sr != SR else x


def note_descriptor(x: np.ndarray, start: float, end: float, midi: int) -> dict | None:
    a = int((start + 0.05) * SR)
    b = int(min(end - 0.02, start + 0.6) * SR)
    if b - a < int(0.12 * SR):
        return None
    seg = x[a:b]
    if np.sqrt(np.mean(seg ** 2)) < 1e-4:
        return None
    c = spectral_centroid(seg, n_fft=2048)
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    return {"midi": midi, "centroid_hz": c, "harmonics": c / f0}


def pitch_error_cents(x: np.ndarray, start: float, end: float, midi: int) -> float | None:
    a, b = int((start + 0.08) * SR), int((end - 0.05) * SR)
    if b - a < int(0.2 * SR):
        return None
    f0 = 440.0 * 2 ** ((midi - 69) / 12)
    seg = x[a : min(b, a + int(0.5 * SR))]
    frame = 8192 if f0 < 80 else 4096
    if len(seg) < frame:
        return None
    est, voiced, _ = librosa.pyin(seg, fmin=f0 / 2, fmax=f0 * 2, sr=SR, frame_length=frame)
    est = est[voiced & ~np.isnan(est)]
    if len(est) < 3:
        return None
    return float(1200 * np.log2(np.median(est) / f0))


def reference_notes() -> dict[str, list[dict]]:
    refs: dict[str, list[dict]] = {}
    for song in sorted(URMP.glob("*_*")):
        for stem in song.glob("AuSep_*.wav"):
            code = stem.name.split("_")[2]
            if code not in URMP_CODE:
                continue
            notes_file = song / stem.name.replace("AuSep_", "Notes_").replace(".wav", ".txt")
            x = load(stem)
            for line in notes_file.read_text().split("\n"):
                p = line.split()
                if len(p) < 3:
                    continue
                on, hz, dur = map(float, p[:3])
                d = note_descriptor(x, on, on + dur, int(round(69 + 12 * np.log2(hz / 440))))
                if d:
                    refs.setdefault(URMP_CODE[code], []).append(dict(d, corpus="URMP", source=song.name))
    with (CB / "metadata_tracks.csv").open() as f:
        for row in csv.DictReader(f, delimiter=";"):
            inst = CB_NAME.get(row["instrument"])
            if not inst:
                continue
            song = CB / row["song_id"]
            x = load(song / "tracks" / row["path_audio"])
            with (song / "annotations" / row["path_notes"]).open() as nf:
                for n in csv.DictReader(nf, delimiter=";"):
                    d = note_descriptor(x, float(n["start_sec"]), float(n["end_sec"]), int(n["pitch"]))
                    if d:
                        refs.setdefault(inst, []).append(dict(d, corpus="ChoraleBricks", source=row["performer"]))
    return refs


def summarise(ds: list[dict], lo: int, hi: int) -> dict:
    sel = [d for d in ds if lo <= d["midi"] <= hi]
    if not sel:
        return {"n": 0}
    return {"n": len(sel), "centroid_hz": round(float(np.median([d["centroid_hz"] for d in sel])), 1),
            "harmonics": round(float(np.median([d["harmonics"] for d in sel])), 2)}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("runs", nargs="+", help="render output dirs (with stems/)")
    ap.add_argument("--midi", required=True)
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()
    parts, _ = read_parts(Path(args.midi))
    refs = reference_notes()
    report = {"references": {k: len(v) for k, v in refs.items()}, "parts": {}}
    for p in parts:
        if p.name not in PART_REF:
            continue
        pitches = [n.pitch for n in p.notes]
        lo, hi = int(np.percentile(pitches, 10)), int(np.percentile(pitches, 90))
        ref = PART_REF[p.name]
        entry = {"pitch_window": [lo, hi], "reference": ref,
                 "ref": {c: summarise([d for d in refs.get(ref, []) if d["corpus"] == c], lo, hi)
                         for c in ("URMP", "ChoraleBricks")}, "tiers": {}}
        for run in args.runs:
            stem = Path(run) / "stems" / f"{p.name.replace(' ', '_').replace('♭', 'b')}.wav"
            if not stem.exists():
                continue
            x = load(stem)
            ds = [d for n in p.notes if (d := note_descriptor(x, n.start, n.end, n.pitch))]
            long_notes = [n for n in p.notes if n.end - n.start > 0.3]
            step = max(1, len(long_notes) // 40)
            errs = [e for n in long_notes[::step] if (e := pitch_error_cents(x, n.start, n.end, n.pitch)) is not None]
            entry["tiers"][Path(run).name] = dict(summarise(ds, lo, hi), pitch_checked=len(errs),
                                                 pitch_within_50c=round(float(np.mean(np.abs(errs) < 50)), 3) if errs else None,
                                                 pitch_median_abs_cents=round(float(np.median(np.abs(errs))), 1) if errs else None)
        report["parts"][p.name] = entry
    Path(args.out).write_text(json.dumps(report, indent=1, ensure_ascii=False))
    tiers = [Path(r).name for r in args.runs]
    print(f"references: {report['references']}")
    print(f"{'part':15s} {'window':8s} {'ref':10s} " + " ".join(f"{t[:10]:>16s}" for t in tiers) +
          f" {'URMP':>12s} {'ChoraleBr.':>12s}   pitch ok (tiers)")
    for name, e in report["parts"].items():
        cols = " ".join(f"{e['tiers'].get(t, {}).get('centroid_hz', '-')!s:>8} {e['tiers'].get(t, {}).get('harmonics', '-')!s:>6}h"
                        for t in tiers)
        rcols = " ".join(f"{e['ref'][c].get('centroid_hz', '-')!s:>7} {e['ref'][c].get('harmonics', '-')!s:>4}h" for c in ("URMP", "ChoraleBricks"))
        pok = " ".join(str(e["tiers"].get(t, {}).get("pitch_within_50c")) for t in tiers)
        print(f"{name:15s} {e['pitch_window'][0]}-{e['pitch_window'][1]:<5d} {e['reference']:10s} {cols} {rcols}   {pok}")


if __name__ == "__main__":
    main()
