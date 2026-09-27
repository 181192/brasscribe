#!/usr/bin/env python3
"""Build the screenshot and UI-test fixture: "Old Hundredth" (Louis Bourgeois, 1551, public domain).

No recording is involved. The hymn is written out here as the engine's layer MIDI files (three
solo transcriptions, bass, inner voices) and arranged by the Rust core's `arrange-layers`, the
same path a real recording takes after separation. A few solo notes are given to only one or two
of the three solo transcribers, with little pitch-contour support, so the arrangement carries
low-confidence notes and review items for the Review screens. A silent drum stem, made here and
thrown away, tells the core the solo was separated from a mix, as it is for a band recording.

    python3 apps/fixtures/make-old-hundredth.py [--cli core/target/release/brasscribe-core]

Writes apps/fixtures/old-hundredth/ (composition.json, brass-band.musicxml, parts/, talking-score.*).
Only tests, UI tests and screenshot scripts read this folder; no app build bundles it.
"""
import argparse
import io
import math
import shutil
import struct
import subprocess
import sys
import tempfile
import wave
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
OUT = HERE / "old-hundredth"
TITLE = "Old Hundredth"
BPM = 72
PPQ = 480
LEAD_IN = 0.5  # seconds before the first beat

N = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def pc(name):
    return (N[name[0]] + name.count("#") - name.count("b")) % 12


def p(name):
    """"F#4" -> 66."""
    return 12 * (int(name[-1]) + 1) + N[name[0]] + name.count("#") - name.count("b")


# Melody and chord per note: four lines of eight notes (long, six short, long, then a half rest).
LINES = [
    ("G4 G4 F#4 E4 D4 G4 A4 B4", "G G D C G C D G"),
    ("B4 B4 B4 A4 G4 C5 B4 A4", "G Em G D Em C G D"),
    ("G4 A4 B4 A4 G4 E4 F#4 G4", "G D G D C Am D G"),
    ("D5 B4 G4 A4 C5 B4 A4 G4", "G Em C D Am G D G"),
]
CHORDS = {"G": ("G", "B", "D"), "C": ("C", "E", "G"), "D": ("D", "F#", "A"), "Em": ("E", "G", "B"), "Am": ("A", "C", "E")}
RHYTHM = [2, 1, 1, 1, 1, 1, 1, 2]  # beats; each line is followed by a two-beat rest

# (line, note index) -> the solo transcribers that heard the note; every other note is heard by all
# three. Heard by SwiftF0 alone the note is marked for review; with Basic Pitch too it is not.
DOUBT = {(0, 3): ("sw",), (0, 4): ("sw", "bp"), (1, 5): ("sw",), (1, 6): ("sw",), (2, 5): ("sw",), (3, 0): ("sw",)}


def voicing(mel, chord):
    """Alto and tenor: chord tones below the melody (alto at least a third down), tenor at or above C3."""
    tones = {pc(t) for t in CHORDS[chord]}
    below = [x for x in range(mel - 1, 47, -1) if x % 12 in tones]
    alto = below[0] if mel - below[0] >= 3 else below[1]
    tenor = next(x for x in below if x < alto - 2)
    return alto, tenor


def bass_of(chord):
    """The chord root between G2 and F#3."""
    return 43 + (pc(CHORDS[chord][0]) - 7) % 12


def events():
    """(beat, beats, pitch, layer) for every note, and the length in beats."""
    beat = 0.0
    out = []
    for li, (mel, chords) in enumerate(LINES):
        for ni, (m, c, d) in enumerate(zip(mel.split(), chords.split(), RHYTHM)):
            mp = p(m)
            alto, tenor = voicing(mp, c)
            for who in DOUBT.get((li, ni), ("sw", "mus", "bp")):
                out.append((beat, d, mp, who))
            out += [(beat, d, bass_of(c), "bass"), (beat, d, alto, "orch"), (beat, d, tenor, "orch")]
            beat += d
        beat += 2
    return out, beat


def vlq(n):
    b = [n & 0x7F]
    n >>= 7
    while n:
        b.insert(0, (n & 0x7F) | 0x80)
        n >>= 7
    return bytes(b)


def midi(notes, channel=0):
    """Format-0 MIDI of (beat, beats, pitch) at the fixture tempo, after the lead-in."""
    lead = round(LEAD_IN * BPM / 60 * PPQ)
    evs = []
    for b, d, pitch in notes:
        on = lead + round(b * PPQ)
        evs.append((on + round(d * PPQ) - 12, 0, bytes([0x80 | channel, pitch, 0])))
        evs.append((on, 1, bytes([0x90 | channel, pitch, 80])))
    evs.sort(key=lambda e: (e[0], e[1]))
    trk = b"\x00\xff\x51\x03" + struct.pack(">I", round(60_000_000 / BPM))[1:]
    t = 0
    for at, _, data in evs:
        trk += vlq(at - t) + data
        t = at
    trk += b"\x00\xff\x2f\x00"
    return b"MThd" + struct.pack(">IHHH", 6, 0, 1, PPQ) + b"MTrk" + struct.pack(">I", len(trk)) + trk


def npy(values):
    """A little-endian float64 .npy array."""
    header = "{'descr': '<f8', 'fortran_order': False, 'shape': (%d,), }" % len(values)
    header += " " * (63 - (len(header) + 10) % 64) + "\n"
    return b"\x93NUMPY\x01\x00" + struct.pack("<H", len(header)) + header.encode() + struct.pack(f"<{len(values)}d", *values)


def seconds(beat):
    return LEAD_IN + beat * 60 / BPM


def contour(solo, doubtful, total):
    """SwiftF0-style contour of the solo: 10 ms frames, confident except on the doubtful notes."""
    t = [i / 100 for i in range(int(seconds(total) * 100) + 1)]
    hz = [0.0] * len(t)
    conf = [0.0] * len(t)
    for b, d, pitch in solo:
        for i in range(round(seconds(b) * 100), min(len(t), round(seconds(b + d) * 100) - 2)):
            hz[i] = 440 * 2 ** ((pitch - 69) / 12)
            conf[i] = 0.1 if (b, pitch) in doubtful else 0.95
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        for name, v in [("t", t), ("pitch_hz", hz), ("loudness_db", [-20.0 if h else -80.0 for h in hz]), ("confidence", conf)]:
            z.writestr(f"{name}.npy", npy(v))
    return buf.getvalue()


def sine_stem(notes, total, rate=16000):
    """Mono 16-bit sine tones of (beat, beats, pitch)."""
    x = [0.0] * (int(seconds(total + 2) * rate))
    for b, d, pitch in notes:
        f = 440 * 2 ** ((pitch - 69) / 12)
        a, e = int(seconds(b) * rate), int(seconds(b + d) * rate) - rate // 50
        for i in range(a, e):
            x[i] += 0.3 * math.sin(2 * math.pi * f * (i - a) / rate)
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(struct.pack(f"<{len(x)}h", *(int(max(-1, min(1, v)) * 32767) for v in x)))
    return buf.getvalue()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cli", default=str(ROOT / "core/target/release/brasscribe-core"))
    a = ap.parse_args()
    if not Path(a.cli).exists():
        sys.exit(f"{a.cli} missing: build it with `cargo build --release -p brasscribe-cli` in core/")
    evs, total = events()
    with tempfile.TemporaryDirectory() as tmp:
        layers = Path(tmp) / "layers"
        layers.mkdir()
        for name, layer in [("solo-sw", "sw"), ("solo-mus", "mus"), ("solo-bp", "bp"), ("bass-mus", "bass"), ("orchestra-mus", "orch")]:
            (layers / f"{name}.mid").write_bytes(midi([(b, d, x) for b, d, x, w in evs if w == layer]))
        (layers / "drums-mus.mid").write_bytes(midi([], channel=9))
        solo = [(b, d, x) for b, d, x, w in evs if w == "sw"]
        doubtful = {(b, x) for b, d, x, w in evs if w == "sw"} - {(b, x) for b, d, x, w in evs if w == "mus"}
        (layers / "solo-sw.contour.npz").write_bytes(contour(solo, doubtful, total))
        (layers / "drums.wav").write_bytes(sine_stem([], total))
        beats = Path(tmp) / "beats.txt"
        beats.write_text("".join(f"{LEAD_IN + i * 60 / BPM:.4f}\t{i % 4 + 1}\n" for i in range(int(total) + 4)))
        if OUT.exists():
            shutil.rmtree(OUT)
        OUT.mkdir()

        def run(*args):
            subprocess.run([a.cli, *args], check=True)

        run("arrange-layers", "--layers", str(layers), "--beats", str(beats), "--out", str(OUT), "--title", TITLE, "--no-free-time", "--single-key")
        run("talking-score", "--musicxml", str(OUT / "brass-band.musicxml"), "--composition", str(OUT / "composition.json"),
            "--json", str(OUT / "talking-score.json"), "--text", str(OUT / "talking-score.txt"), "--html", str(OUT / "talking-score.html"))
    print(f"wrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
