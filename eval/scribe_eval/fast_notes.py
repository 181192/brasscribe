"""Fast notes and two-note alternations on cornet/trumpet: a synthetic eval set with exact ground truth.

Every clip is four bars of 4/4: a bar of tongued quarters (so the beat tracker has a pulse), two
bars of the figure under test, and a closing half note. Figures:

  alt      two-note alternation (trill, lip trill, shake): lower/upper at an interval of
           1 (m2), 2 (M2), 3 (m3), 5 (P4) or 12 (octave lip slur) semitones
  run      diatonic scale up and down
  arp      broken chord
  repeat   one pitch re-tongued (double/triple tonguing)
  ctl-*    must-stay-one-note traps and slow material: vibrato, scoop, fall, slow two-note slurs

at 4 (16ths), 6 (sextuplets) or 8 (32nds) notes per beat and 90/120/150 BPM, slurred (no
re-articulation: the pitch change is the only onset) or tongued.

Renderers:
  samples  real trumpet recordings: University of Iowa MIS sustains (slurs, long notes) and VSCO 2 CE
           staccato (tongued short notes), re-pitched to the note, slurs as a 12 ms crossfade with a
           small level dip at each change
  room     `samples` convolved with a measured church impulse response (OpenAIR, St Margaret's, York)
  sf2      the band SoundFont's Solo Cornet (sus/stac presets) through FluidSynth, re-attacking every note

    python -m brasscribe_eval.fast_notes build          # audio + reference.json + oracle.beats per clip
    python -m brasscribe_eval.fast_notes track          # SwiftF0 notes + contour, Basic Pitch, Beat This! small0
    python -m brasscribe_eval.fast_notes freeze         # tracker outputs + references -> eval/fixtures/fast-notes

Clips go to data/fast-notes/fast-notes/<id>/. Tracking runs the adapters' own environments in batches
(the main checkout's ml/adapters when this checkout has none).
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
import zlib
from dataclasses import asdict, dataclass
from functools import lru_cache
from pathlib import Path

import numpy as np
import soundfile as sf

from .paths import ADAPTERS, DATA, ROOT

OUT = DATA / "fast-notes" / "fast-notes"
FIXTURES = ROOT / "eval" / "fixtures" / "fast-notes"
RAW = DATA / "sounds" / "raw"
BAND_SF2 = DATA / "sounds" / "band" / "brasscribe-band.sf2"
IR = RAW / "openair" / "st-margarets-church-ncem-5-piece-band-spatial-measurements" / "stereo" / "4_c414_l.wav"
SR = 44100
T0 = 0.5  # seconds of silence before beat 0

INTERVALS = (1, 2, 3, 5, 12)
TEMPI = (90, 120, 150)
SUBDIVS = (4, 6, 8)


@dataclass(frozen=True)
class Spec:
    kind: str  # alt, run, arp, repeat, ctl-vibrato, ctl-scoop, ctl-fall, ctl-slowslur
    interval: int
    tempo: int
    subdiv: int
    art: str  # slur | tongue
    render: str  # samples | room | sf2

    @property
    def id(self) -> str:
        return f"{self.kind}-i{self.interval}-t{self.tempo}-s{self.subdiv}-{self.art}-{self.render}"


def specs() -> list[Spec]:
    out = []
    for render in ("samples", "sf2"):
        for art in ("slur", "tongue"):
            for tempo in TEMPI:
                for sub in SUBDIVS:
                    out += [Spec("alt", i, tempo, sub, art, render) for i in INTERVALS]
                    out += [Spec("run", 0, tempo, sub, art, render), Spec("arp", 0, tempo, sub, art, render)]
        for tempo in TEMPI:
            for sub in SUBDIVS:
                out.append(Spec("repeat", 0, tempo, sub, "tongue", render))
        for tempo in (70, 100):
            out += [Spec("ctl-vibrato", 0, tempo, 1, "slur", render), Spec("ctl-scoop", 0, tempo, 1, "tongue", render),
                    Spec("ctl-fall", 0, tempo, 1, "tongue", render)]
        for i in (1, 2, 12):
            out.append(Spec("ctl-slowslur", i, 80, 1, "slur", render))
    # Must-stay-one-note traps, dry and in the hall (and separated: SEP_CLIPS).
    for render in ("samples", "room"):
        for tempo in (70, 100):
            out += [Spec(k, 0, tempo, 1, "tongue", render) for k in CONTROLS if k not in ("ctl-vibrato", "ctl-scoop", "ctl-fall")]
        if render == "room":
            for tempo in (70, 100):
                out += [Spec("ctl-vibrato", 0, tempo, 1, "slur", render), Spec("ctl-scoop", 0, tempo, 1, "tongue", render),
                        Spec("ctl-fall", 0, tempo, 1, "tongue", render)]
            for i in (1, 2, 12):
                out.append(Spec("ctl-slowslur", i, 80, 1, "slur", render))
            out.append(Spec("ctl-leap", 12, 80, 1, "slur", render))
    # A reverberant hall on the alternations and runs at the middle tempo.
    for art in ("slur", "tongue"):
        for sub in SUBDIVS:
            out += [Spec("alt", i, 120, sub, art, "room") for i in INTERVALS]
            out.append(Spec("run", 0, 120, sub, art, "room"))
    return out


# ------------------------------------------------------------------ the score

LOW = 67  # G4 concert: the lower note of the alternations
OCT_LOW = 60  # C4 concert: octave lip slur C4-C5
MAJOR = (0, 2, 4, 5, 7, 9, 11, 12)


def score(s: Spec) -> list[dict]:
    """Notes in beats: pitch, beat, dur (beats), role (lead/figure/tail), mod (pitch modulation name)."""
    notes = [{"pitch": p, "beat": float(b), "dur": 1.0, "role": "lead", "mod": None, "slur": False}
             for b, p in enumerate((65, 67, 69, 70))]
    if s.kind.startswith("ctl-"):
        return notes + _control(s)
    n = 8 * s.subdiv
    step = 1.0 / s.subdiv
    if s.kind == "alt":
        lo = OCT_LOW if s.interval == 12 else LOW
        pitches = [lo if k % 2 == 0 else lo + s.interval for k in range(n)]
    elif s.kind == "run":
        up = [62 + d for d in MAJOR] + [62 + 12 + d for d in MAJOR[1:5]]
        cyc = up + up[-2:0:-1]
        pitches = [cyc[k % len(cyc)] for k in range(n)]
    elif s.kind == "arp":
        cyc = [62, 66, 69, 74, 78, 74, 69, 66]
        pitches = [cyc[k % len(cyc)] for k in range(n)]
    elif s.kind == "repeat":
        pitches = [70] * n
    else:
        raise ValueError(s.kind)
    notes += [{"pitch": p, "beat": 4 + k * step, "dur": step, "role": "figure", "mod": None,
               "slur": s.art == "slur" and k < n - 1} for k, p in enumerate(pitches)]
    notes.append({"pitch": pitches[0] if s.kind != "alt" else pitches[0], "beat": 12.0, "dur": 2.0, "role": "tail",
                  "mod": None, "slur": False})
    return notes


# Control kind -> the pitch (or level) modulation of its long notes: name:depth:rate (see cents_curve).
CONTROLS = {
    "ctl-vibrato": "vibrato",  # +-60 c, 5.5 Hz
    "ctl-vib100": "vib:100:6",
    "ctl-vib150": "vib:150:7",
    "ctl-vibdown100": "vibdown:100:5.5",  # lip vibrato: one-sided, down from the note
    "ctl-vibdown120": "vibdown:120:7",
    "ctl-ampvib": "amp:3:5.5",  # +-3 dB level vibrato, steady pitch
    "ctl-scoop": "scoop",
    "ctl-scoop300": "scoop:300:0.15",
    "ctl-fall": "fall",
    "ctl-doit": "doit:500:0.2",  # up 500 c over the last 200 ms
    "ctl-rip": "rip:700:0.15",  # a rip up into the note from 700 c below over 150 ms
}


def _control(s: Spec) -> list[dict]:
    """Bars 2-4 of a control clip: every note here must come out as exactly one note."""
    if s.kind == "ctl-leap":  # slurred octave leaps: the hall's tail of each note under the next
        return [{"pitch": 67 if k % 2 == 0 else 79, "beat": 4.0 + 2 * k, "dur": 2.0, "role": "figure", "mod": None,
                 "slur": k < 3} for k in range(4)]
    if s.kind == "ctl-slowslur":
        lo = OCT_LOW if s.interval == 12 else LOW
        return [{"pitch": lo if k % 2 == 0 else lo + s.interval, "beat": 4.0 + 2 * k, "dur": 2.0, "role": "figure",
                 "mod": None, "slur": k < 3} for k in range(4)]
    mod = CONTROLS[s.kind]
    pitches = (72, 70, 69, 67)
    return [{"pitch": p, "beat": 4.0 + 2 * k, "dur": 2.0, "role": "figure", "mod": mod, "slur": False}
            for k, p in enumerate(pitches)]


def amp_curve(mod: str | None, t: np.ndarray) -> np.ndarray:
    """Level factor over a note's own time axis (amplitude vibrato)."""
    if mod and mod.startswith("amp:"):
        _, db, rate = mod.split(":")
        return 10 ** (float(db) * np.sin(2 * np.pi * float(rate) * np.maximum(t - 0.15, 0)) / 20)
    return np.ones_like(t)


def cents_curve(mod: str | None, t: np.ndarray, dur: float) -> np.ndarray:
    """Pitch deviation in cents over a note's own time axis."""
    if mod and ":" in mod:
        name, a, b = mod.split(":")
        a, b = float(a), float(b)
        ramp = np.clip((t - 0.15) / 0.2, 0, 1)
        if name == "vib":
            return a * np.sin(2 * np.pi * b * np.maximum(t - 0.15, 0)) * ramp
        if name == "vibdown":
            return -a * 0.5 * (1 - np.cos(2 * np.pi * b * np.maximum(t - 0.15, 0))) * ramp
        if name == "scoop":
            return -a * np.clip(1 - t / b, 0, 1) ** 1.5
        if name == "rip":
            return -a * np.clip(1 - t / b, 0, 1)
        if name == "doit":
            return a * np.clip((t - (dur - b)) / b, 0, 1) ** 2
        return np.zeros_like(t)
    if mod == "vibrato":  # +-60 cents at 5.5 Hz after a 150 ms straight start (a wide cornet vibrato)
        return 60 * np.sin(2 * np.pi * 5.5 * np.maximum(t - 0.15, 0)) * np.clip((t - 0.15) / 0.2, 0, 1)
    if mod == "scoop":  # up from 200 cents flat over 120 ms
        return -200 * np.clip(1 - t / 0.12, 0, 1) ** 1.5
    if mod == "fall":  # the last 250 ms drop 400 cents
        return -400 * np.clip((t - (dur - 0.25)) / 0.25, 0, 1) ** 2
    return np.zeros_like(t)


def perform(s: Spec) -> tuple[list[dict], float]:
    """Performed notes in seconds (the ground truth) and the seconds per beat."""
    rng = np.random.default_rng(zlib.crc32(s.id.encode()))
    spb = 60.0 / s.tempo
    out = []
    sc = score(s)
    for k, n in enumerate(sc):
        jitter = rng.normal(0, 0.004 if n["slur"] or (k and sc[k - 1]["slur"]) else 0.006)
        on = T0 + n["beat"] * spb + (jitter if k else 0.0)
        out.append({**n, "onset": float(on)})
    for k, n in enumerate(out):
        ioi = n["dur"] * spb
        nxt = out[k + 1]["onset"] if k + 1 < len(out) else None
        if n["slur"] and nxt is not None:
            off = nxt
        elif n["role"] == "figure" and s.art == "tongue":
            off = n["onset"] + 0.8 * ioi
        else:
            off = n["onset"] + 0.92 * ioi
        if nxt is not None:
            off = min(off, nxt)
        n["offset"] = float(off)
    return out, spb


# ------------------------------------------------------------------ real-sample renderer

def _mono(path: Path) -> np.ndarray:
    y, sr = sf.read(path, dtype="float32", always_2d=True)
    y = y.mean(axis=1)
    if sr != SR:
        from scipy.signal import resample_poly

        y = resample_poly(y, SR, sr).astype(np.float32)
    return y


def _f0_midi(y: np.ndarray) -> float:
    """Fundamental of a steady brass tone (autocorrelation over 150-1100 Hz), as fractional MIDI."""
    seg = y[: 8192] - y[: 8192].mean()
    ac = np.correlate(seg, seg, "full")[len(seg) - 1:]
    lo, hi = int(SR / 1100), int(SR / 150)
    lag = lo + int(np.argmax(ac[lo:hi]))
    # parabolic refinement
    a, b, c = ac[lag - 1], ac[lag], ac[lag + 1]
    lag = lag + 0.5 * (a - c) / (a - 2 * b + c) if (a - 2 * b + c) != 0 else lag
    return 69 + 12 * np.log2(SR / lag / 440)


@dataclass
class Sample:
    y: np.ndarray
    start: int  # attack start
    steady: int  # start of the steady part
    midi: float


NAMES = {"C": 0, "Db": 1, "C#": 1, "D": 2, "Eb": 3, "D#": 3, "E": 4, "F": 5, "Gb": 6, "F#": 6, "G": 7, "Ab": 8, "G#": 8,
         "A": 9, "Bb": 10, "A#": 10, "B": 11}


def _nominal(name: str, octave_shift: int = 0) -> int:
    import re

    m = re.fullmatch(r"([A-G][b#]?)(-?\d)", name)
    return 12 * (int(m.group(2)) + 1 + octave_shift) + NAMES[m.group(1)]


def _tuned(nominal: int, measured: float) -> float:
    """The nominal pitch plus the measured tuning (octave errors of the estimate folded away)."""
    return nominal + ((measured - nominal + 6) % 12 - 6)


def _trim(y: np.ndarray) -> tuple[int, int]:
    env = np.sqrt(np.convolve(y ** 2, np.ones(441) / 441, "same"))
    peak = env.max()
    start = int(np.argmax(env > peak * 0.05))
    return max(0, start - 64), start + int(0.25 * SR)


@lru_cache(maxsize=1)
def sample_bank() -> dict[str, list[Sample]]:
    bank: dict[str, list[Sample]] = {"sus": [], "stac": []}
    for f in sorted((RAW / "iowa-mis" / "trumpet" / "pitch").glob("Trumpet.novib.ff.*.aif")):
        y = _mono(f)
        a, st = _trim(y)
        y = y / (np.sqrt(np.mean(y[st: st + SR // 2] ** 2)) + 1e-9) * 0.1
        bank["sus"].append(Sample(y, a, st, _tuned(_nominal(f.name.split(".")[3]), _f0_midi(y[st:]))))
    for f in sorted((RAW / "vsco2ce" / "Brass" / "Trumpet" / "stac").glob("*_v2_rr*.wav")):
        y = _mono(f)
        a, _ = _trim(y)
        body = a + int(0.03 * SR)
        y = y / (np.sqrt(np.mean(y[a: a + int(0.08 * SR)] ** 2)) + 1e-9) * 0.1
        # VSCO names middle C "C3"
        name = f.name.split("_")[3]
        bank["stac"].append(Sample(y, a, body, _tuned(_nominal(name, 1), _f0_midi(y[body: body + 8192]))))
    return bank


def _nearest(kind: str, pitch: int, rng) -> Sample:
    cands = sorted(sample_bank()[kind], key=lambda s: abs(s.midi - pitch))
    best = [c for c in cands if abs(c.midi - cands[0].midi) < 0.5]
    return best[int(rng.integers(len(best)))]


def _voice(smp: Sample, pos: int, n: int, pitch: int, cents: np.ndarray | None) -> np.ndarray:
    """n output samples of `smp` from sample index `pos`, re-pitched to `pitch` (+ cents per output sample)."""
    ratio = 2 ** ((pitch - smp.midi) / 12) * (2 ** (cents / 1200) if cents is not None else np.ones(n))
    idx = pos + np.concatenate([[0.0], np.cumsum(ratio[:-1])])
    if idx[-1] >= len(smp.y) - 1:  # loop the steady part when the sample runs out
        span = len(smp.y) - 1 - smp.steady - SR // 10
        idx = np.where(idx >= len(smp.y) - 1, smp.steady + (idx - smp.steady) % max(span, SR // 10), idx)
    return np.interp(idx, np.arange(len(smp.y)), smp.y).astype(np.float32)


def render_samples(notes: list[dict], seconds: float, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    out = np.zeros(int(seconds * SR), np.float32)
    k = 0
    xf = int(0.012 * SR)
    while k < len(notes):
        # a slurred chain: notes k..j joined without re-attack
        j = k
        while notes[j]["slur"] and j + 1 < len(notes):
            j += 1
        chain = notes[k: j + 1]
        buf_start = int(chain[0]["onset"] * SR)
        pieces = []
        for m, n in enumerate(chain):
            a, b = int(n["onset"] * SR), int(n["offset"] * SR)
            ln = b - a + (xf if m < len(chain) - 1 else 0)
            short = n["offset"] - n["onset"] < 0.3 and len(chain) == 1
            smp = _nearest("stac" if short else "sus", n["pitch"], rng)
            t = np.arange(ln) / SR
            cents = cents_curve(n["mod"], t, n["offset"] - n["onset"]) + rng.normal(0, 3)
            pos = smp.start if m == 0 else smp.steady + int(rng.uniform(0, 0.3) * SR)
            pieces.append((a - buf_start, _voice(smp, pos, ln, n["pitch"], cents) * amp_curve(n["mod"], t).astype(np.float32)))
        total = int(chain[-1]["offset"] * SR) - buf_start + xf
        buf = np.zeros(total, np.float32)
        for m, (off, y) in enumerate(pieces):
            y = y.copy()
            if m > 0:  # fade in over the crossfade, and a level dip at the change (lip slur)
                y[:xf] *= np.sin(np.linspace(0, np.pi / 2, xf)) ** 2
            if m < len(pieces) - 1:
                y[-xf:] *= np.cos(np.linspace(0, np.pi / 2, xf)) ** 2
            buf[off: off + len(y)] += y[: total - off]
        for m in range(1, len(pieces)):
            c = pieces[m][0]
            w = np.arange(total) - c
            buf *= (1 - 0.3 * np.exp(-0.5 * (w / (0.006 * SR)) ** 2)).astype(np.float32)
        rel = int(0.02 * SR)
        end_note = total - xf
        buf[end_note - rel: end_note] *= np.linspace(1, 0, rel)
        buf[end_note:] = 0
        seg = out[buf_start: buf_start + total]
        seg += buf[: len(seg)]
        k = j + 1
    return out


def room(y: np.ndarray) -> np.ndarray:
    ir = _mono(IR)
    ir = ir[int(np.argmax(np.abs(ir))):]
    ir = ir / np.sqrt(np.sum(ir ** 2))
    from scipy.signal import fftconvolve

    wet = fftconvolve(y, ir)[: len(y)]
    wet *= np.sqrt(np.sum(y ** 2) / (np.sum(wet ** 2) + 1e-12))
    return (y + 0.7 * wet).astype(np.float32)  # reverb about 3 dB under the direct sound


# ------------------------------------------------------------------ SoundFont renderer

SUS, STAC = (0, 56), (64, 56)  # (bank, program) of the band SoundFont's Solo Cornet


def render_sf2(notes: list[dict], seconds: float) -> np.ndarray:
    import mido

    mid = mido.MidiFile(ticks_per_beat=960)  # 120 BPM default tempo: 1920 ticks per second
    tps = 1920
    ev = []
    for ch, (bank, prog) in ((0, SUS), (1, STAC)):
        ev += [(0, 0, mido.Message("control_change", channel=ch, control=0, value=bank)),
               (0, 1, mido.Message("program_change", channel=ch, program=prog))]
    for n in notes:
        ch = 1 if n["role"] == "figure" and not n["slur"] and n["offset"] - n["onset"] < 0.3 else 0
        a = int(n["onset"] * tps)
        b = int((n["offset"] + (0.015 if n["slur"] else 0.0)) * tps)
        ev.append((a, 3, mido.Message("note_on", channel=ch, note=n["pitch"], velocity=96)))
        ev.append((b, 2, mido.Message("note_off", channel=ch, note=n["pitch"], velocity=0)))
        if n["mod"]:
            for tt in np.arange(0, n["offset"] - n["onset"], 0.005):
                c = float(cents_curve(n["mod"], np.array([tt]), n["offset"] - n["onset"])[0])
                val = int(np.clip(round(c / 200 * 8192), -8192, 8191))
                ev.append((a + int(tt * tps), 1, mido.Message("pitchwheel", channel=ch, pitch=val)))
            # back to centre once the release has died away, not at the note-off (a bend back up in the tail)
            nxt = min((m["onset"] for m in notes if m["onset"] > n["onset"]), default=n["offset"] + 0.6)
            ev.append((int((nxt - 0.02) * tps), 1, mido.Message("pitchwheel", channel=ch, pitch=0)))
    ev.sort(key=lambda e: (e[0], e[1]))
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    last = 0
    for t, _, m in ev:
        tr.append(m.copy(time=t - last))
        last = t
    with tempfile.TemporaryDirectory() as tmp:
        mp, wp = Path(tmp) / "x.mid", Path(tmp) / "x.wav"
        mid.save(mp)
        subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-g", "0.6", "-r", str(SR), "-F", str(wp),
                        str(BAND_SF2), str(mp)], check=True, capture_output=True)
        y = _mono(wp)
    out = np.zeros(int(seconds * SR), np.float32)
    out[: min(len(y), len(out))] = y[: len(out)]
    return out


# ------------------------------------------------------------------ build / track / freeze

def build_clip(s: Spec, dst: Path) -> None:
    notes, spb = perform(s)
    seconds = notes[-1]["offset"] + 1.0
    if s.render == "sf2":
        y = render_sf2(notes, seconds)
    else:
        y = render_samples(notes, seconds, zlib.crc32(s.id.encode()))
        if s.render == "room":
            y = room(y)
    y = y / (np.abs(y).max() + 1e-9) * 0.5
    y += np.random.default_rng(1).normal(0, 1e-4, len(y)).astype(np.float32)  # a noise floor, not digital silence
    dst.mkdir(parents=True, exist_ok=True)
    sf.write(dst / "audio.wav", y, SR, subtype="PCM_16")
    n_beats = int(np.ceil((seconds - T0) / spb)) + 1
    beats = [(T0 + k * spb, k % 4 + 1) for k in range(n_beats)]
    (dst / "oracle.beats").write_text("".join(f"{t:.6f}\t{p}\n" for t, p in beats))
    ref = {"spec": asdict(s), "id": s.id, "seconds_per_beat": spb, "t0": T0, "beats_per_bar": 4,
           "notes": [{k: n[k] for k in ("pitch", "onset", "offset", "beat", "dur", "role", "mod", "slur")} for n in notes]}
    (dst / "reference.json").write_text(json.dumps(ref, indent=1))


def adapter_dir(name: str) -> Path:
    """This checkout's adapter project, or the main checkout's when this one has no environment yet."""
    here = ADAPTERS / name
    if (here / ".venv").exists():
        return here
    main = subprocess.run(["git", "-C", str(ROOT), "worktree", "list", "--porcelain"], capture_output=True,
                          text=True).stdout.splitlines()[0].removeprefix("worktree ")
    return Path(main) / "ml" / "adapters" / name


SWIFT_BATCH = """
import sys, numpy as np
from swift_f0 import SwiftF0, export_to_midi, segment_notes
det = SwiftF0()
for src in sys.argv[1:]:
    r = det.detect_file(src)
    d = src.rsplit('/', 1)[0]
    np.savez_compressed(d + '/sw.contour.npz', t=r.timestamps, pitch_hz=r.pitch_hz, confidence=r.confidence,
                        loudness_db=r.loudness_db)
    notes = segment_notes(r, pitch_hold_ms=80.0)
    if notes:
        export_to_midi(notes, d + '/sw.mid')
"""


def track(clips: list[Path], only: set[str]) -> None:
    wavs = [c / "audio.wav" for c in clips]
    if "sw" in only:
        subprocess.run(["uv", "run", "--project", str(adapter_dir("swift-f0")), "python", "-c", SWIFT_BATCH,
                        *map(str, wavs)], check=True)
    if "bp" in only:
        with tempfile.TemporaryDirectory() as tmp:
            # Basic Pitch names its output after the input: give every clip a unique name.
            links = []
            for c in clips:
                link = Path(tmp) / f"{c.name}.wav"
                link.symlink_to(c / "audio.wav")
                links.append(link)
            outd = Path(tmp) / "out"
            outd.mkdir()
            for k in range(0, len(links), 40):
                subprocess.run(["uv", "run", "--project", str(adapter_dir("basic-pitch")), "basic-pitch", str(outd),
                                *map(str, links[k: k + 40])], check=True, capture_output=True)
            for c in clips:
                m = outd / f"{c.name}_basic_pitch.mid"
                if m.exists():
                    shutil.move(str(m), c / "bp.mid")
    if "beats" in only:
        with tempfile.TemporaryDirectory() as tmp:
            stereo = []
            for c in clips:  # the adapter's input: 44.1 kHz stereo
                p = Path(tmp) / f"{c.name}.wav"
                y, sr = sf.read(c / "audio.wav", dtype="float32")
                sf.write(p, np.stack([y, y], axis=1), sr)
                stereo.append(p)
            subprocess.run(["uv", "run", "--project", str(adapter_dir("beat-this")), "beat_this", *map(str, stereo),
                            "--model", "small0", "-o", tmp, "--suffix", ".beats"], check=True, capture_output=True)
            for c in clips:
                b = Path(tmp) / f"{c.name}.beats"
                if b.exists():
                    shutil.move(str(b), c / "small0.beats")


FROZEN = ("reference.json", "oracle.beats", "small0.beats", "sw.mid", "bp.mid", "sw.contour.npz")


FROZEN_RENDERS = ("samples", "room")  # the real-sample clips (and their separated controls); the SoundFont clips stay local


def freeze(clips: list[Path], prefix: str = "", render: str | None = None) -> None:
    """Tracker outputs and references of the real-sample clips -> eval/fixtures/fast-notes (the CI suite).
    `prefix`/`render`: the separated clips, frozen as sep-<id> with render "sep"."""
    for c in clips:
        if not c.name.endswith(FROZEN_RENDERS) or not (c / "reference.json").exists():
            continue
        d = FIXTURES / f"{prefix}{c.name}"
        d.mkdir(parents=True, exist_ok=True)
        for f in FROZEN:
            if not (c / f).exists():
                continue
            if f == "reference.json":  # compact: the fixtures are committed
                ref = json.loads((c / f).read_text())
                if render:
                    ref["spec"]["render"] = render
                (d / f).write_text(json.dumps(ref, separators=(",", ":")))
            else:
                shutil.copy(c / f, d / f)


SEP_OUT = DATA / "fast-notes" / "fast-notes-sep"
SEP_CLIPS = ("alt-i1-t120-s4-slur-samples", "alt-i2-t120-s6-slur-samples", "alt-i12-t120-s4-slur-samples",
             "alt-i3-t120-s6-tongue-samples", "run-i0-t120-s4-slur-samples", "run-i0-t120-s6-tongue-samples",
             "arp-i0-t120-s4-tongue-samples", "repeat-i0-t120-s4-tongue-samples",
             # slurred alternation: every interval, two rates
             *(f"alt-i{i}-t{t}-s4-slur-samples" for i in (1, 2, 3, 5, 12) for t in (90, 150)
               if (i, t) not in ((1, 120), (12, 120))),
             # every control
             "ctl-vibrato-i0-t70-s1-slur-samples", "ctl-scoop-i0-t100-s1-tongue-samples", "ctl-fall-i0-t100-s1-tongue-samples",
             *(f"{k}-i0-t100-s1-tongue-samples" for k in CONTROLS if k not in ("ctl-vibrato", "ctl-scoop", "ctl-fall")),
             "ctl-slowslur-i1-t80-s1-slur-samples", "ctl-slowslur-i12-t80-s1-slur-samples")
BED = [(43, 55, 59, 62), (48, 55, 60, 64), (50, 57, 62, 66), (43, 55, 59, 62)]  # G C D G, one chord per bar


def band_bed(seconds: float, spb: float) -> np.ndarray:
    """Sustained band chords (Tenor Horn, Baritone, Trombone presets of the band SoundFont), one per bar."""
    notes = []
    for bar, chord in enumerate(BED):
        for p in chord:
            notes.append({"pitch": p, "onset": T0 + 4 * bar * spb, "offset": T0 + 4 * (bar + 1) * spb - 0.05,
                          "role": "lead", "slur": False, "mod": None})
    return render_sf2(notes, seconds)


def separated(src: Path = OUT, dst: Path = SEP_OUT) -> list[Path]:
    """Chosen clips mixed with a band bed 12 dB under the solo, then separated by Mega-53 (the solo stem the
    orchestra-with-soloist profile transcribes): what separation does to fast notes."""
    from .gpulock import gpu_lock

    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for cid in SEP_CLIPS:
            c = src / cid
            if (dst / cid / "audio.wav").exists():
                out.append(dst / cid)
                continue
            ref = json.loads((c / "reference.json").read_text())
            y, _ = sf.read(c / "audio.wav", dtype="float32")
            bed = band_bed(len(y) / SR, ref["seconds_per_beat"])[: len(y)]
            bed *= np.sqrt(np.mean(y ** 2) / (np.mean(bed ** 2) + 1e-12)) * 10 ** (-12 / 20)
            mix = y + bed
            mix = mix / np.abs(mix).max() * 0.7
            d = dst / cid
            d.mkdir(parents=True, exist_ok=True)
            sf.write(d / "mix.wav", mix, SR, subtype="PCM_16")
            stems = Path(tmp) / cid
            with gpu_lock():
                subprocess.run(["python3", str(adapter_dir("mega53").parent / "run_adapter.py"), "mega53", str(d / "mix.wav"),
                                str(stems)], check=True, capture_output=True)
            t, _ = sf.read(stems / "trumpet.flac", dtype="float32", always_2d=True)
            sf.write(d / "audio.wav", t.mean(axis=1), SR, subtype="PCM_16")
            for f in ("reference.json", "oracle.beats"):
                shutil.copy(c / f, d / f)
            out.append(d)
    return out


URMP = DATA / "urmp" / "Dataset"
URMP_TRACKED = DATA / "runs" / "music-core" / "solo-beats" / "urmp"
URMP_OUT = DATA / "fast-notes" / "fast-notes-urmp"
FAST_IOI = 0.16  # seconds: a URMP note this close to a neighbour is a "fast" note (the figure)


def urmp(dst: Path = URMP_OUT) -> list[Path]:
    """Every URMP trumpet part (real recordings, local only: the URMP licence is not checked for redistribution)
    as a clip, with the part's own SwiftF0/Basic Pitch/Beat This! small0 outputs. Notes with a neighbour
    closer than FAST_IOI are the figure; there are no oracle beats."""
    out = []
    for piece in sorted(URMP.glob("*_*")):
        for notes_txt in sorted(piece.glob("Notes_*_tpt_*.txt")):
            k = notes_txt.name.split("_")[1]
            tracked = URMP_TRACKED / piece.name
            if not (tracked / f"{k}-tpt-sw.mid").exists():
                continue
            rows = [list(map(float, ln.split())) for ln in notes_txt.read_text().splitlines() if ln.strip()]
            on = np.array([r[0] for r in rows])
            ioi = np.diff(on)
            near = np.minimum(np.r_[np.inf, ioi], np.r_[ioi, np.inf])
            notes = [{"pitch": int(round(69 + 12 * np.log2(r[1] / 440))), "onset": r[0], "offset": r[0] + r[2],
                      "role": "figure" if g < FAST_IOI else "lead", "mod": None, "slur": False}
                     for r, g in zip(rows, near)]
            c = dst / f"{piece.name}-{k}-tpt"
            c.mkdir(parents=True, exist_ok=True)
            for src, name in ((f"{k}-tpt-sw.mid", "sw.mid"), (f"{k}-tpt-bp.mid", "bp.mid"),
                              (f"{k}-tpt-sw.contour.npz", "sw.contour.npz"), (f"{k}-tpt.beats", "small0.beats")):
                link = c / name
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(tracked / src)
            spec = {"kind": "urmp", "interval": 0, "tempo": 0, "subdiv": 0, "art": "real", "render": "urmp"}
            (c / "reference.json").write_text(json.dumps({"spec": spec, "id": c.name, "notes": notes}, indent=1))
            out.append(c)
    return out


VIBRATO_IN = DATA / "eval" / "fast-notes-vibrato"  # vib-<midi>-{dry,hall}.wav: Iowa MIS trumpet vibrato sustains
VIBRATO_OUT = DATA / "fast-notes" / "fast-notes-realvib"


def real_vibrato(src: Path = VIBRATO_IN, dst: Path = VIBRATO_OUT) -> list[Path]:
    """Real trumpet vibrato (35 University of Iowa MIS "Trumpet.vib.ff" sustains, dry and convolved with the
    OpenAIR Usina hall response), one sustained note each: a clip per file, its one note spanning the voiced
    part, on oracle 120 BPM beats. Track with `track --root`."""
    out = []
    for w in sorted(src.glob("vib-*-*.wav")):
        _, midi, env = w.stem.split("-")
        c = dst / f"ctl-realvib-i0-t120-s1-{env}-{midi}"
        c.mkdir(parents=True, exist_ok=True)
        y, sr = sf.read(w, dtype="float32")
        env_db = 20 * np.log10(np.sqrt(np.convolve(y ** 2, np.ones(sr // 50) / (sr // 50), "same")) + 1e-9)
        on = np.nonzero(env_db > env_db.max() - 30)[0]
        a, b = on[0] / sr, on[-1] / sr
        sf.write(c / "audio.wav", y, sr, subtype="PCM_16")
        beats = [(k * 0.5, k % 4 + 1) for k in range(int(len(y) / sr / 0.5) + 2)]
        (c / "oracle.beats").write_text("".join(f"{t:.6f}\t{p}\n" for t, p in beats))
        spec = {"kind": "ctl-realvib", "interval": 0, "tempo": 120, "subdiv": 1, "art": env, "render": env}
        note = {"pitch": int(midi), "onset": float(a), "offset": float(b), "beat": 0.0, "dur": 0.0, "role": "figure",
                "mod": "real", "slur": False}
        (c / "reference.json").write_text(json.dumps({"spec": spec, "id": c.name, "notes": [note]}, indent=1))
        out.append(c)
    return out


URMP_SEP_OUT = DATA / "fast-notes" / "fast-notes-urmpsep"
URMP_SOLO_TRUMPET = ("09_Jesus_tpt_vn", "10_March_tpt_sax", "18_Nocturne_vn_fl_tpt", "20_Pavane_tpt_vn_vc")


def urmp_separated(dst: Path = URMP_SEP_OUT) -> list[Path]:
    """Real brass with a band behind it and real separation: the URMP pieces with one trumpet, their mix
    (AuMix) through Mega-53, the trumpet stem scored against the trumpet's URMP notes. Local only (URMP)."""
    from .gpulock import gpu_lock

    out = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in URMP_SOLO_TRUMPET:
            piece = URMP / name
            c = dst / name
            c.mkdir(parents=True, exist_ok=True)
            if not (c / "audio.wav").exists():
                stems = Path(tmp) / name
                with gpu_lock():
                    subprocess.run(["python3", str(adapter_dir("mega53").parent / "run_adapter.py"), "mega53",
                                    str(next(piece.glob("AuMix_*.wav"))), str(stems)], check=True, capture_output=True)
                t, sr = sf.read(stems / "trumpet.flac", dtype="float32", always_2d=True)
                sf.write(c / "audio.wav", t.mean(axis=1), sr, subtype="PCM_16")
            rows = [list(map(float, ln.split())) for ln in next(piece.glob("Notes_*_tpt_*.txt")).read_text().splitlines()
                    if ln.strip()]
            on = np.array([r[0] for r in rows])
            ioi = np.diff(on)
            near = np.minimum(np.r_[np.inf, ioi], np.r_[ioi, np.inf])
            notes = [{"pitch": int(round(69 + 12 * np.log2(r[1] / 440))), "onset": r[0], "offset": r[0] + r[2],
                      "role": "figure" if g < FAST_IOI else "lead", "mod": None, "slur": False}
                     for r, g in zip(rows, near)]
            spec = {"kind": "urmp", "interval": 0, "tempo": 0, "subdiv": 0, "art": "sep", "render": "urmp-sep"}
            (c / "reference.json").write_text(json.dumps({"spec": spec, "id": c.name, "notes": notes}, indent=1))
            out.append(c)
    return out


CHORALES_SOLO = ROOT / "eval" / "fixtures" / "choralebricks-solo"
CHORALES_OUT = DATA / "fast-notes" / "fast-notes-chorales"


def chorales(dst: Path = CHORALES_OUT) -> list[Path]:
    """The frozen ChoraleBricks solo stems (slow legato brass: the must-not-regress set) as clips."""
    import csv

    out = []
    for song in sorted(p for p in CHORALES_SOLO.iterdir() if p.is_dir()):
        for sw in sorted(song.glob("*.sw.mid")):
            stem = sw.name[: -len(".sw.mid")]
            if not all((song / f"{stem}{x}").exists() for x in (".bp.mid", ".beats", ".notes.csv", ".contour.npz")):
                continue
            rows = list(csv.DictReader((song / f"{stem}.notes.csv").open(), delimiter=";"))
            notes = [{"pitch": int(r["pitch"]), "onset": float(r["start_sec"]), "offset": float(r["end_sec"]),
                      "role": "lead", "mod": None, "slur": False} for r in rows]
            c = dst / f"{song.name}-{stem}"
            c.mkdir(parents=True, exist_ok=True)
            for src, name in ((".sw.mid", "sw.mid"), (".bp.mid", "bp.mid"), (".contour.npz", "sw.contour.npz"),
                              (".beats", "small0.beats")):
                link = c / name
                if link.is_symlink() or link.exists():
                    link.unlink()
                link.symlink_to(song / f"{stem}{src}")
            spec = {"kind": "chorale", "interval": 0, "tempo": 0, "subdiv": 0, "art": stem.split("_", 1)[1],
                    "render": "chorale"}
            (c / "reference.json").write_text(json.dumps({"spec": spec, "id": c.name, "notes": notes}, indent=1))
            out.append(c)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("cmd", choices=("build", "track", "freeze", "list", "urmp", "chorales", "separate", "realvib", "urmpsep"))
    ap.add_argument("--only", help="substring of the clip ids to process")
    ap.add_argument("--tools", default="sw,bp,beats", help="track: which trackers (sw, bp, beats)")
    ap.add_argument("--root", type=Path, default=OUT)
    args = ap.parse_args()
    ss = [s for s in specs() if not args.only or args.only in s.id]
    if args.cmd == "urmp":
        made = urmp()
        print(len(made), "URMP trumpet parts ->", URMP_OUT)
        return
    if args.cmd == "urmpsep":
        made = urmp_separated()
        track(made, {"sw", "bp", "beats"})
        print(len(made), "separated URMP trumpet parts ->", URMP_SEP_OUT)
        return
    if args.cmd == "realvib":
        made = real_vibrato()
        track(made, {"sw", "bp"})
        print(len(made), "real vibrato clips ->", VIBRATO_OUT)
        return
    if args.cmd == "separate":
        print(len(separated()), "separated clips ->", SEP_OUT)
        return
    if args.cmd == "chorales":
        print(len(chorales()), "ChoraleBricks solo stems ->", CHORALES_OUT)
        return
    if args.cmd == "list":
        for s in ss:
            print(s.id)
        print(len(ss), "clips")
    elif args.cmd == "build":
        for k, s in enumerate(ss):
            build_clip(s, args.root / s.id)
            if k % 25 == 0:
                print(f"{k + 1}/{len(ss)} {s.id}", flush=True)
    elif args.cmd == "track":
        track([args.root / s.id for s in ss if (args.root / s.id / "audio.wav").exists()], set(args.tools.split(",")))
    else:
        freeze([args.root / s.id for s in ss])
        if args.root == OUT and SEP_OUT.exists():
            freeze([SEP_OUT / s.id for s in ss if (SEP_OUT / s.id).exists()], prefix="sep-", render="sep")


if __name__ == "__main__":
    main()
