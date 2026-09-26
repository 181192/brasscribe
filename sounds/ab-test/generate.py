"""Cut blind A/B listening material from a baseline and a realistic render.

    uv run --project sounds python sounds/ab-test/generate.py \
        --baseline data/golden/mikkel-arranged-band/brass-band.mp3 \
        --realistic data/runs/sound/realistic/mikkel.realistic.wav \
        --midi data/runs/sound/mikkel.mid \
        -o data/runs/sound/ab-test [--listeners 5] [--excerpts 5] [--seconds 12]

Writes, under the output directory:
    listener-N/pair-K-A.wav, pair-K-B.wav   blind material per listener, pairs in random order
    listener-N/answers.csv                   answer sheet (pair, preferred A/B, confidence, comment)
    full/{baseline,realistic}.wav            whole piece, loudness-matched, for reference only
    excerpts.json                            excerpt times and loudness (not secret)
    key.json                                 which letter is which tier (SECRET: keep out of git)

Fairness: the baseline is a 128 kb/s MP3, so the realistic render is encoded to the same
MP3 settings and both are decoded; the tiers are aligned by onset-envelope cross-correlation;
every excerpt pair uses identical cut times, 50 ms fade-in and 500 ms fade-out, and is
normalised to the same integrated loudness (-20 LUFS) with a common peak ceiling.
"""

from __future__ import annotations

import argparse
import csv
import json
import secrets
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import numpy as np
import pyloudnorm
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from dsp import SR  # noqa: E402
from render import read_parts  # noqa: E402

EXCERPT_LUFS = -20.0
FULL_LUFS = -16.0
PEAK_CEILING_DB = -1.0


def decode(path: Path, work: Path, reencode_mp3: bool) -> np.ndarray:
    src = path
    if reencode_mp3:
        src = work / (path.stem + ".128k.mp3")
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(path), "-codec:a", "libmp3lame", "-b:a", "128k",
                        "-ar", str(SR), str(src)], check=True)
    out = work / (path.stem + ".decoded.wav")
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ar", str(SR), "-ac", "2", str(out)], check=True)
    x, _ = sf.read(str(out), dtype="float64", always_2d=True)
    return x


def onset_env(x: np.ndarray) -> np.ndarray:
    return librosa.onset.onset_strength(y=x.mean(axis=1).astype(np.float32), sr=SR, hop_length=512)


def align(ref: np.ndarray, other: np.ndarray, max_lag_s: float = 5.0) -> int:
    """Samples to shift `other` so it lines up with `ref` (positive = other starts later)."""
    a, b = onset_env(ref), onset_env(other)
    n = min(len(a), len(b))
    a, b = a[:n] - a[:n].mean(), b[:n] - b[:n].mean()
    max_lag = int(max_lag_s * SR / 512)
    lags = range(-max_lag, max_lag + 1)
    scores = [float(np.dot(a[max(0, -l) : n - max(0, l)], b[max(0, l) : n - max(0, -l)])) for l in lags]
    return lags[int(np.argmax(scores))] * 512


def choose_excerpts(midi: Path, count: int, seconds: float, total: float) -> list[float]:
    """One window per equal zone of the piece: the window with the most note onsets across parts."""
    parts, _ = read_parts(midi)
    onsets = np.array(sorted(n.start for p in parts if p.name != "Percussion" for n in p.notes))
    starts: list[float] = []
    zone = (total - seconds) / count
    for z in range(count):
        best, best_t = -1, z * zone
        first = max(z * zone, starts[-1] + seconds + 2.0) if starts else z * zone  # no overlapping excerpts
        for t in np.arange(first, max(first + 0.5, (z + 1) * zone - 0.5), 0.5):
            c = int(np.sum((onsets >= t) & (onsets < t + seconds)))
            if c > best:
                best, best_t = c, float(t)
        starts.append(round(best_t, 2))
    return starts


def cut(x: np.ndarray, start: float, seconds: float) -> np.ndarray:
    a = int(start * SR)
    y = x[a : a + int(seconds * SR)].copy()
    fi, fo = int(0.05 * SR), int(0.5 * SR)
    y[:fi] *= np.linspace(0, 1, fi)[:, None]
    y[-fo:] *= np.linspace(1, 0, fo)[:, None]
    return y


def match(clips: list[np.ndarray], lufs: float) -> tuple[list[np.ndarray], list[float]]:
    meter = pyloudnorm.Meter(SR)
    measured = [meter.integrated_loudness(c) for c in clips]
    out = [c * 10 ** ((lufs - m) / 20) for c, m in zip(clips, measured)]
    peak = max(np.abs(c).max() for c in out)
    ceiling = 10 ** (PEAK_CEILING_DB / 20)
    if peak > ceiling:  # same gain on every clip keeps them matched
        out = [c * ceiling / peak for c in out]
    return out, measured


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--realistic", required=True)
    ap.add_argument("--midi", required=True)
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--listeners", type=int, default=5)
    ap.add_argument("--excerpts", type=int, default=5)
    ap.add_argument("--seconds", type=float, default=12.0)
    args = ap.parse_args()
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="brasscribe-ab-"))

    base = decode(Path(args.baseline), work, reencode_mp3=False)
    real = decode(Path(args.realistic), work, reencode_mp3=Path(args.realistic).suffix.lower() != ".mp3")
    lag = align(base, real)
    if lag > 0:
        real = real[lag:]
    elif lag < 0:
        real = np.concatenate([np.zeros((-lag, 2)), real])
    total = min(len(base), len(real)) / SR
    base, real = base[: int(total * SR)], real[: int(total * SR)]
    # MIDI time is the realistic render's own time; after alignment a MIDI time t sits at t - lag
    starts_midi = choose_excerpts(Path(args.midi), args.excerpts, args.seconds, total + lag / SR)
    starts = [round(max(0.0, s - lag / SR), 3) for s in starts_midi]

    (out / "full").mkdir(exist_ok=True)
    full, full_lufs = match([base, real], FULL_LUFS)
    sf.write(str(out / "full" / "baseline.wav"), full[0].astype(np.float32), SR, subtype="PCM_16")
    sf.write(str(out / "full" / "realistic.wav"), full[1].astype(np.float32), SR, subtype="PCM_16")

    pairs = []
    for i, s in enumerate(starts, start=1):
        clips, measured = match([cut(base, s, args.seconds), cut(real, s, args.seconds)], EXCERPT_LUFS)
        cb = librosa.feature.chroma_stft(y=clips[0].mean(axis=1).astype(np.float32), sr=SR).mean(axis=1)
        cr = librosa.feature.chroma_stft(y=clips[1].mean(axis=1).astype(np.float32), sr=SR).mean(axis=1)
        chroma_cos = float(np.dot(cb, cr) / (np.linalg.norm(cb) * np.linalg.norm(cr)))
        pairs.append({"pair": i, "start_s": s, "seconds": args.seconds, "clips": clips,
                      "chroma_similarity": round(chroma_cos, 3),
                      "lufs_before": {"baseline": round(measured[0], 2), "realistic": round(measured[1], 2)}})

    rng = secrets.SystemRandom()
    # counterbalance: for each excerpt, realistic is "A" for half the listeners (odd count: one random extra)
    a_plan = {}
    for p in pairs:
        plan = [i % 2 == 0 for i in range(args.listeners)]
        rng.shuffle(plan)
        a_plan[p["pair"]] = plan
    key = {"note": "SECRET: do not commit or share with listeners until all answers are in.", "listeners": {}}
    for n in range(1, args.listeners + 1):
        d = out / f"listener-{n}"
        d.mkdir(exist_ok=True)
        order = list(range(len(pairs)))
        rng.shuffle(order)
        key["listeners"][str(n)] = {}
        for k, pi in enumerate(order, start=1):
            p = pairs[pi]
            realistic_is_a = a_plan[p["pair"]][n - 1]
            a, b = (p["clips"][1], p["clips"][0]) if realistic_is_a else (p["clips"][0], p["clips"][1])
            sf.write(str(d / f"pair-{k}-A.wav"), a.astype(np.float32), SR, subtype="PCM_16")
            sf.write(str(d / f"pair-{k}-B.wav"), b.astype(np.float32), SR, subtype="PCM_16")
            key["listeners"][str(n)][str(k)] = {"excerpt": p["pair"], "A": "realistic" if realistic_is_a else "baseline",
                                                 "B": "baseline" if realistic_is_a else "realistic"}
        with (d / "answers.csv").open("w", newline="") as f:
            w = csv.writer(f)
            w.writerow(["pair", "preferred (A or B)", "confidence (1-3)", "comment"])
            for k in range(1, len(pairs) + 1):
                w.writerow([k, "", "", ""])
    (out / "key.json").write_text(json.dumps(key, indent=1))
    meta = {"baseline": args.baseline, "realistic": args.realistic, "alignment_lag_s": round(lag / SR, 3),
            "excerpt_lufs": EXCERPT_LUFS, "full_lufs": FULL_LUFS,
            "full_lufs_before": {"baseline": round(full_lufs[0], 2), "realistic": round(full_lufs[1], 2)},
            "excerpts": [{k: v for k, v in p.items() if k != "clips"} for p in pairs]}
    (out / "excerpts.json").write_text(json.dumps(meta, indent=1))
    print(json.dumps(meta, indent=1))


if __name__ == "__main__":
    main()
