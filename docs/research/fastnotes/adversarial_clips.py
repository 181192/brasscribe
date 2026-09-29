"""Adversarial clips for the fast-notes bench, built independently of its own synthesis.

Writes clip directories in the fast-notes bench format (audio.wav, reference.json, oracle.beats) so that
`fast_notes.track` and `fast_notes_bench.evaluate(root)` score them stage by stage. The audio comes from
probe.py's additive synthesis (continuous phase, jitter), not from the bench's sample renderer, with a
synthetic hall, a measured hall (OpenAIR Usina) and a band bed:

  ctl-vibrato   wide centred and one-sided vibrato on a long note (must stay one note)
  ctl-scoop     a scoop of -300 c over 150 ms into a long note
  run           16th and sextuplet runs, slurred, in the halls
  alt           semitone and whole-tone trills under the band bed and in a hall
  ctl-octave    a slow tune with real octave leaps (C5 C4 C5 G4 ...), slurred and tongued: every note must survive

    ml/adapters/swift-f0/.venv/bin/python docs/research/fastnotes/adversarial_clips.py OUT_DIR
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import soundfile as sf

sys.path.insert(0, str(Path(__file__).resolve().parent))
import probe  # noqa: E402

SR = probe.SR
ROOT = Path(__file__).resolve().parents[3]
USINA = ROOT / "data" / "sounds" / "raw" / "openair" / "usina-del-arte-symphony-hall" / "stereo" / "usina_main_s2_p3.wav"


def usina():
    y, sr = sf.read(USINA, always_2d=True)
    y = y.mean(axis=1)
    n = int(len(y) * SR / sr)
    ir = np.interp(np.linspace(0, len(y) - 1, n), np.arange(len(y)), y)
    return ir[int(np.argmax(np.abs(ir))):]  # from the direct sound: the file has 100 ms of pre-delay


def room(y, ir):
    L = len(y) + len(ir)
    out = np.fft.irfft(np.fft.rfft(y, 2 * L) * np.fft.rfft(ir, 2 * L), 2 * L)[: len(y)]
    return (out / np.max(np.abs(out)) * 0.8).astype(np.float32)


def write(out: Path, cid: str, y, notes, spec, bpm, lead):
    d = out / cid
    d.mkdir(parents=True, exist_ok=True)
    sf.write(d / "audio.wav", y, SR)
    beat = 60 / bpm
    dur = len(y) / SR
    k0 = int(np.ceil(lead / beat))
    t0 = lead - k0 * beat
    times = [t0 + i * beat for i in range(int((dur - t0) / beat) + 1) if t0 + i * beat >= 0]
    (d / "oracle.beats").write_text("".join(f"{t:.6f}\t{i % 4 + 1}\n" for i, t in enumerate(times)))
    ref = {"spec": spec, "id": cid, "seconds_per_beat": beat, "t0": times[0], "beats_per_bar": 4,
           "notes": [{"pitch": int(p), "onset": float(a), "offset": float(b), "role": role} for a, b, p, role in notes]}
    (d / "reference.json").write_text(json.dumps(ref))


def with_lead(pitches, note_s, legato, lead_quarters, bpm, **kw):
    """Two lead quarters, then the figure, then a closing half note, as the bench's clips are laid out."""
    beat = 60 / bpm
    seq = [(p, beat) for p in lead_quarters] + [(p, note_s) for p in pitches] + [(pitches[-1], 2 * beat)]
    n = int((0.5 + sum(d for _, d in seq) + 0.6) * SR)
    pt = np.full(n, float(seq[0][0]))
    amp = np.zeros(n)
    t, notes = 0.5, []
    for i, (p, d) in enumerate(seq):
        a, b = int(t * SR), int((t + d) * SR)
        pt[a:b] = p
        amp[a:b] = 1.0
        g = int(kw.get("glide_s", 0.015) * SR)
        if i and (legato or i > len(lead_quarters)) and legato:
            pt[a:a + g] = np.linspace(seq[i - 1][0], p, g)
        if not legato or i <= len(lead_quarters):
            g0, att = int(0.02 * SR), int(0.012 * SR)
            if i:
                amp[a - g0:a] = 0.02
            amp[a:a + att] = np.linspace(0.02, 1.0, att)
        role = "figure" if len(lead_quarters) <= i < len(lead_quarters) + len(pitches) else "lead"
        notes.append((t, t + d, p, role))
        t += d
    pt[int(t * SR):] = seq[-1][0]
    r = int(0.03 * SR)
    amp[int(t * SR) - r:int(t * SR)] *= np.linspace(1, 0, r)
    return pt, amp, notes


def main():
    out = Path(sys.argv[1])
    ir = usina()
    bpm = 100

    # controls on one long note (figure = the note), preceded by two tongued quarters
    for name, kw in [("vib100c6", dict(vib_cents=100, vib_hz=6)), ("vib150c7", dict(vib_cents=150, vib_hz=7)),
                     ("vibdown120c6", dict(vib_cents=60, vib_hz=6, down=1.2)), ("scoop300", dict(scoop_st=3.0))]:
        down = kw.pop("down", 0.0)
        pt, amp, _ = probe.long_note(67, 2.4, lead=0.5 + 1.2, **kw)
        if down:
            pt = pt - down / 2 * (amp > 0)
        # two lead quarters (64, 65) before the long note
        for i, p in enumerate((64, 65)):
            a, b = int((0.5 + 0.6 * i) * SR), int((0.5 + 0.6 * (i + 1)) * SR) - int(0.02 * SR)
            pt[a:b], amp[a:b] = p, 1.0
        notes = [(0.5, 1.1, 64, "lead"), (1.1, 1.7, 65, "lead"), (1.7, 4.1, 67, "figure")]
        kind = "ctl-scoop" if "scoop" in name else "ctl-vibrato"
        spec = {"kind": kind, "interval": 0, "tempo": bpm, "subdiv": 1, "art": "slur", "render": "adv"}
        for env in ("dry", "hall", "usina"):
            y = probe.render(pt, amp, reverb=2.0 if env == "hall" else 0.0)
            if env == "usina":
                y = room(y, ir)
            write(out, f"{kind}-adv-{name}-{env}", y, notes, {**spec, "render": f"adv-{env}"}, bpm, 0.5)

    # runs and trills
    scale = [60, 62, 64, 65, 67, 69, 71, 72, 74, 72, 71, 69, 67, 65, 64, 62]
    for label, pitches, div, tempo, kind, iv in [("run16", scale, 4, 144, "run", 0), ("runsext", scale + [60, 62], 6, 120, "run", 0),
                                                  ("trill1", [72, 73] * 12, 6, 120, "alt", 1), ("trill2", [72, 74] * 10, 5, 120, "alt", 2)]:
        beat = 60 / tempo
        pt, amp, notes = with_lead(pitches, beat / div, True, [67, 69], tempo)
        spec = {"kind": kind, "interval": iv, "tempo": tempo, "subdiv": div, "art": "slur"}
        for env in ("dry", "hall", "usina", "band"):
            bed = probe.band_bed(len(pt) / SR) if env == "band" else None
            y = probe.render(pt, amp, reverb=2.0 if env == "hall" else 0.0, band=bed)
            if env == "usina":
                y = room(y, ir)
            write(out, f"{kind}-adv-{label}-{env}", y, notes, {**spec, "render": f"adv-{env}"}, tempo, 0.5)

    # a slow tune with octave leaps: every note must survive (no octave folding)
    tune = [72, 60, 72, 67, 79, 67, 72, 60]
    for art in ("slur", "tongue"):
        pt, amp, notes = with_lead(tune, 0.6, art == "slur", [64, 65], bpm, glide_s=0.03)
        notes = [(a, b, p, "figure" if r == "figure" else r) for a, b, p, r in notes]
        spec = {"kind": "run", "interval": 12, "tempo": bpm, "subdiv": 1, "art": art}
        for env in ("dry", "usina"):
            y = probe.render(pt, amp)
            if env == "usina":
                y = room(y, ir)
            write(out, f"run-adv-octaves-{art}-{env}", y, notes, {**spec, "render": f"adv-{env}"}, bpm, 0.5)
    print(len(list(out.iterdir())), "clips ->", out)


if __name__ == "__main__":
    main()
