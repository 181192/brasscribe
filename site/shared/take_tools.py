"""What the scripts that make a product's take share: checksums, a small MIDI reader, the loudness of a recording."""

import hashlib
import struct
import subprocess
import wave
from pathlib import Path


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def samples(path: Path) -> str:
    """The SHA-256 of a WAV file's samples: the same sound gives the same answer, whatever wrote the file's header."""
    with wave.open(str(path)) as w:
        return hashlib.sha256(w.readframes(w.getnframes())).hexdigest()


def run(*cmd: str, **more) -> None:
    subprocess.run(cmd, check=True, **more)


def midi_notes(path: Path) -> list[list[float]]:
    """The notes of a small MIDI file as [start, end, pitch] in seconds: note on and off, and the tempo."""
    data = path.read_bytes()
    division = struct.unpack(">H", data[12:14])[0]
    events, at = [], 14
    while at < len(data):
        length = struct.unpack(">I", data[at + 4:at + 8])[0]
        track, i, tick, status = data[at + 8:at + 8 + length], 0, 0, 0
        at += 8 + length
        while i < len(track):
            delta = 0
            while True:
                byte = track[i]; i += 1
                delta = (delta << 7) | (byte & 0x7F)
                if not byte & 0x80:
                    break
            tick += delta
            if track[i] & 0x80:
                status = track[i]; i += 1
            if status == 0xFF:
                kind, size = track[i], track[i + 1]
                if kind == 0x51:
                    events.append((tick, "tempo", int.from_bytes(track[i + 2:i + 5], "big"), 0))
                i += 2 + size
            elif status in (0xF0, 0xF7):
                i += 1 + track[i]
            else:
                size = 1 if status & 0xF0 in (0xC0, 0xD0) else 2
                if status & 0xF0 in (0x80, 0x90):
                    events.append((tick, "on" if status & 0xF0 == 0x90 and track[i + 1] else "off", track[i], 0))
                i += size
    events.sort(key=lambda e: (e[0], e[1] != "tempo"))
    notes, sounding, seconds, last, tempo = [], {}, 0.0, 0, 500000
    for tick, kind, value, _ in events:
        seconds += (tick - last) * tempo / division / 1e6
        last = tick
        if kind == "tempo":
            tempo = value
        elif kind == "on":
            sounding[value] = seconds
        elif value in sounding:
            notes.append([round(sounding.pop(value), 3), round(seconds, 3), value])
    return sorted(notes)


def sound(wav: Path) -> dict:
    """The mix's loudness: its peak in every fiftieth of a second, the loudest as 1."""
    import numpy as np

    with wave.open(str(wav)) as w:
        rate = w.getframerate()
        samples = np.abs(np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype(float)) / 32768
    step = rate // 50
    peaks = [float(samples[i:i + step].max()) for i in range(0, len(samples), step)]
    return {"per_second": 50, "peak": [round(p / max(peaks), 3) for p in peaks]}
