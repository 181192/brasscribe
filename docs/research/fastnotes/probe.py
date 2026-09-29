"""Synthetic probe of fast runs, trills and their false-note traps through today's solo path.

Stages measured, in the order the solo path applies them:
  1. SwiftF0 contour + segment_notes(pitch_hold_ms)        (ml/adapters/swift-f0/transcribe.py; Swift/Kotlin ports)
  2. line(): notes < MIN_DUR (60 ms) dropped, onsets < 50 ms apart merged (core lines.rs)
  3. quantize(): per-beat grid from {1,2,4,3,6}, monophonize drops notes sharing a start (core quantize.rs)

Audio is additive synthesis with a brass-like spectrum and a continuous phase, so a legato
change has no re-attack (the hard case: lip slur / lip trill). "tongued" dips the amplitude
for 25 ms at each change. Optional room (exponential-noise IR, RT60) and band (sustained
triads 12 dB under the solo).

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/probe.py [--holds 80,40,20]
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
from swift_f0 import SwiftF0, segment_notes

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "music" / "src"))
from brasscribe_music.quantize import quantize  # noqa: E402

SR = 16000
RNG = np.random.default_rng(7)
MIN_DUR, MERGE = 0.06, 0.05
SPECTRUM = "falling"  # "brass": weak fundamental, strong 2nd-4th partials (SwiftF0 then jumps octaves above C5)


def hz(m):
    return 440.0 * 2 ** ((np.asarray(m, float) - 69) / 12)


def render(pitch_track, amp, reverb=0.0, band=None, drr_db=3.0):
    """pitch_track: MIDI (fractional) per sample; amp: envelope per sample."""
    # natural pitch jitter (about 8 cents, low-passed): a perfectly periodic tone makes SwiftF0 jump octaves at C5-D5
    j = np.convolve(RNG.standard_normal(len(pitch_track)), np.ones(400) / 400, mode="same") * 1.6
    f = hz(pitch_track + j)
    ph = 2 * np.pi * np.cumsum(f) / SR
    y = np.zeros_like(ph)
    for k in range(1, 13):
        a = np.exp(-(k - 1) / 3.0) if SPECTRUM == "falling" else (k ** 0.8) * np.exp(-k / 3.5)
        y += a * np.sin(k * ph) * (k * f < SR / 2 - 200)
    y = y / np.max(np.abs(y)) * amp
    y += 0.003 * RNG.standard_normal(len(y))  # breath noise
    if band is not None:
        y = y + band[: len(y)]
    if reverb > 0:
        n = int(reverb * SR)
        ir = RNG.standard_normal(n) * np.exp(-6.9 * np.arange(n) / n)  # RT60 = reverb s
        ir[:int(0.01 * SR)] = 0.0  # direct sound, then the room from 10 ms
        ir *= 10 ** (-drr_db / 20) / np.sqrt(np.sum(ir ** 2))  # reverb energy relative to the direct sound
        ir[0] = 1.0
        L = len(y) + n
        y = np.fft.irfft(np.fft.rfft(y, 2 * L) * np.fft.rfft(ir, 2 * L), 2 * L)[: len(y)]
    return (y / np.max(np.abs(y)) * 0.8).astype(np.float32)


def band_bed(dur, root=46):
    t = np.arange(int(dur * SR)) / SR
    y = np.zeros_like(t)
    for m in (root, root + 4, root + 7, root + 12, root + 16):
        fr = hz(m)
        for k in range(1, 6):
            y += np.exp(-k / 2) * np.sin(2 * np.pi * k * fr * t + RNG.uniform(0, 6))
    return 0.25 * y / np.max(np.abs(y))  # about -12 dB under the solo


def sequence(pitches, note_s, legato=True, lead=0.3, tail=0.5, glide_s=0.012):
    """Note list -> (pitch track, amp, reference [(on, off, pitch)])."""
    n_total = int((lead + len(pitches) * note_s + tail) * SR)
    pt = np.full(n_total, float(pitches[0]))
    amp = np.zeros(n_total)
    ref = []
    for i, p in enumerate(pitches):
        a = int((lead + i * note_s) * SR)
        b = int((lead + (i + 1) * note_s) * SR)
        pt[a:b] = p
        amp[a:b] = 1.0
        g = int(glide_s * SR)
        if i and legato and g:
            pt[a:a + g] = np.linspace(pitches[i - 1], p, g)
        if not legato and i:
            g0, d = int(0.02 * SR), int(0.012 * SR)  # tongue stop: 20 ms near-silence, 12 ms attack
            amp[a - g0:a] = 0.02
            amp[a:a + d] = np.linspace(0.02, 1.0, d)
        ref.append((lead + i * note_s, lead + (i + 1) * note_s, p))
    pt[int((lead + len(pitches) * note_s) * SR):] = pitches[-1]
    # attack / release of the phrase
    a0, a1 = int(lead * SR), int((lead + len(pitches) * note_s) * SR)
    r = int(0.03 * SR)
    amp[a0:a0 + r] *= np.linspace(0, 1, r)
    amp[a1 - r:a1] *= np.linspace(1, 0, r)
    return pt, amp, ref


def long_note(p, dur, lead=0.3, tail=0.5, vib_cents=0.0, vib_hz=5.5, scoop_st=0.0, scoop_s=0.15, fall_st=0.0):
    n = int((lead + dur + tail) * SR)
    t = np.arange(n) / SR
    pt = np.full(n, float(p))
    on = (t >= lead) & (t < lead + dur)
    pt += (vib_cents / 100) * np.sin(2 * np.pi * vib_hz * (t - lead)) * on * np.clip((t - lead - 0.2) / 0.3, 0, 1)
    if scoop_st:
        s = on & (t < lead + scoop_s)
        pt[s] -= scoop_st * (1 - (t[s] - lead) / scoop_s)
    if fall_st:
        s = on & (t > lead + dur - 0.2)
        pt[s] -= fall_st * (t[s] - (lead + dur - 0.2)) / 0.2
    amp = on.astype(float)
    r = int(0.03 * SR)
    a0 = int(lead * SR)
    amp[a0:a0 + r] *= np.linspace(0, 1, r)
    return pt, amp, [(lead, lead + dur, p)]


def notes_of(y, det, hold):
    r = det.detect(y, SR)
    ns = segment_notes(r, pitch_hold_ms=hold)
    return [(n.start, n.end, int(round(69 + 12 * np.log2(n.pitch_hz / 440)))) for n in ns]


def line(notes):
    out = []
    for n in sorted((n for n in notes if n[1] - n[0] >= MIN_DUR), key=lambda n: n[0]):
        if out and n[0] - out[-1][0] < MERGE:
            if n[2] > out[-1][2]:
                out[-1] = n
            continue
        out.append(n)
    return out


def f1(est, ref, tol=0.05):
    used, tp = set(), 0
    for (o, _, p) in ref:
        best = None
        for j, (eo, _, ep) in enumerate(est):
            if j in used or ep != int(round(p)):
                continue
            d = abs(eo - o)
            if d <= tol and (best is None or d < best[0]):
                best = (d, j)
        if best:
            used.add(best[1])
            tp += 1
    pr = tp / len(est) if est else 0.0
    rc = tp / len(ref) if ref else 0.0
    return (2 * pr * rc / (pr + rc) if pr + rc else 0.0), tp


def quantized_count(notes, bpm, lead=0.3):
    if not notes:
        return 0
    beat = 60 / bpm
    bt = np.arange(lead - 4 * beat, lead + 60, beat)
    raw = [{"pitch": p, "onset": a, "offset": b, "confidence": 1.0} for a, b, p in notes]
    return len(quantize(raw, bt, monophonic=True, auto_level=False))


def cases():
    C = []
    # controls: slow and legato material that must not regress
    melody = [67, 69, 71, 72, 74, 72, 71, 69, 67]
    C.append(("control quarters@80 tongued", "control", 80, *sequence(melody, 0.75, legato=False)))
    C.append(("control 8ths@100 slur", "control", 100, *sequence(melody, 0.3, legato=True)))
    C.append(("control repeated 8ths@100 tongued", "control", 100, *sequence([67] * 8, 0.3, legato=False)))
    # fast runs: major scale up and down, 16ths / sextuplets / 32nds
    scale = [60, 62, 64, 65, 67, 69, 71, 72, 74, 72, 71, 69, 67, 65, 64, 62, 60]
    for bpm, div, label in [(120, 4, "16ths@120"), (144, 4, "16ths@144"), (120, 6, "sext@120"), (96, 8, "32nds@96"), (132, 6, "sext@132")]:
        ns = 60 / bpm / div
        for leg in (False, True):
            C.append((f"run {label} {'slur' if leg else 'tongued'}", "run", bpm, *sequence(scale, ns, legato=leg)))
    # trills: semitone / whole tone, 8..16 notes/s, legato (lip) and tongued
    for iv in (1, 2):
        for rate in (8, 10, 12, 14, 16):
            alt = [72, 72 + iv] * 12
            C.append((f"trill {iv}st {rate}/s slur", "trill", 120, *sequence(alt, 1 / rate, legato=True, glide_s=0.02)))
    # lip trill between partials 8-9 (C6-D6 written; concert Bb5-C6) and 6-8 (G5-C6, wide)
    for rate in (8, 12):
        C.append((f"lip trill 8-9 {rate}/s", "trill", 120, *sequence([70, 72] * 12, 1 / rate, legato=True, glide_s=0.03)))
        C.append((f"shake 3rd {rate}/s", "trill", 120, *sequence([67, 70] * 12, 1 / rate, legato=True, glide_s=0.03)))
    # traps: must stay ONE note
    C.append(("vibrato 50c 5.5Hz", "trap", 80, *long_note(67, 2.0, vib_cents=50)))
    C.append(("wide vibrato 100c 6Hz", "trap", 80, *long_note(67, 2.0, vib_cents=100, vib_hz=6)))
    C.append(("very wide vibrato 150c 7Hz", "trap", 80, *long_note(67, 2.0, vib_cents=150, vib_hz=7)))
    C.append(("scoop -3st/150ms", "trap", 80, *long_note(67, 1.5, scoop_st=3)))
    C.append(("scoop -2st/80ms", "trap", 80, *long_note(67, 1.5, scoop_st=2, scoop_s=0.08)))
    C.append(("fall -4st/200ms", "trap", 80, *long_note(67, 1.5, fall_st=4)))
    return C


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--holds", default="80,40,20")
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    holds = [float(h) for h in args.holds.split(",")]
    det = SwiftF0()
    envs = [("dry", 0.0, False), ("hall2s", 2.0, False), ("band", 0.0, True), ("hall+band", 1.5, True)]
    print("case | env | ref | " + " | ".join(f"h{int(h)}: seg/line/q/F1" for h in holds))
    for name, kind, bpm, pt, amp, ref in cases():
        if args.only and args.only not in name:
            continue
        for env, rv, withband in envs:
            if kind == "run" and env in ("band",) :
                pass
            bed = band_bed(len(pt) / SR) if withband else None
            y = render(pt, amp, reverb=rv, band=bed)
            cells = []
            for h in holds:
                seg = notes_of(y, det, h)
                ln = line(seg)
                q = quantized_count(ln, bpm)
                fs, _ = f1(ln, ref)
                cells.append(f"{len(seg)}/{len(ln)}/{q}/{fs:.2f}")
            print(f"{name} | {env} | {len(ref)} | " + " | ".join(cells), flush=True)


if __name__ == "__main__":
    main()
