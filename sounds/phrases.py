"""Test phrases for every part of every lineup: the material the sound checks render.

    uv run --project sounds python sounds/phrases.py -o data/sounds/phrases

Writes, per lineup part (sounds/mapping.json `parts`, which covers every lineup in
music/src/brasscribe_music/instruments.py):
  <part>.mid       one track, the part's band SoundFont bank/program on channel 0
  phrases.json     where each test section starts and ends, and every note, in seconds
and band.mid, all parts together on their own channels (percussion on channel 10) with the
full-band chord section, for the polyphony and balance checks.

Sections (seconds at 120 bpm; pitches concert, inside each part's comfortable range):
  sustain   three 6 s notes (low, middle, high) at mf, then 8 s at ff: loop seams, sample ends
  repeat    the middle note repeated as 16ths at 132 bpm, full length: retrigger and note-off
  legato    a two-octave scale as 16ths at 132 bpm, notes overlapping by 10 ms: voice build-up
  detached  the same scale as short staccato notes with gaps: releases, staccato samples
  sweep     chromatic over the part's pro range, 0.5 s per note: stretched samples, range holes
  dynamics  the middle note at velocity 30, 48, 64, 80, 100, 116, 127, 1 s each
  chord     (band.mid and phrases.json "band") every part holds a chord tone for 4 s at mf, three
            times, while the cornets play 16ths on top. band.mid has 17 pitched parts on 15
            channels, so two pairs share a channel: use phrases.json "band" with the app's own
            channel plan (as the alphaTab harness does) for polyphony checks
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import mido

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "music" / "src"))
from brasscribe_music.instruments import BRASS_BAND, INSTRUMENTS, MINIMAL_BAND  # noqa: E402

TPS = 1920  # MIDI ticks per second at 120 bpm with 960 ticks per beat
SIXTEENTH = 60 / 132 / 4
GAP = 1.0  # silence between sections, s


def lineups(mapping: dict) -> dict[str, list[str]]:
    """Every lineup and its part names (quartet parts from mapping.json `lineups`)."""
    out = {BRASS_BAND.name: [p.name for p in BRASS_BAND.parts], MINIMAL_BAND.name: [p.name for p in MINIMAL_BAND.parts]}
    for name, parts in mapping.get("lineups", {}).items():
        out.setdefault(name, parts)
    return out


def part_phrases(part: dict) -> tuple[list[tuple[float, float, int, int]], dict[str, tuple[float, float]]]:
    inst = INSTRUMENTS[part["instrument"]]
    lo, hi = inst.comfortable
    plo, phi = inst.pro
    mid = (lo + hi) // 2
    notes: list[tuple[float, float, int, int]] = []  # (start, end, pitch, velocity)
    sections: dict[str, tuple[float, float]] = {}
    t = 0.5

    def section(name: str, body) -> None:
        nonlocal t
        start = t
        t = body(t)
        sections[name] = (start, t)
        t += GAP

    def sustain(t: float) -> float:
        for p in (lo + 2, mid, hi - 2):
            notes.append((t, t + 6.0, p, 80))
            t += 6.5
        notes.append((t, t + 8.0, mid, 116))
        return t + 8.0

    def repeat(t: float) -> float:
        for i in range(24):
            notes.append((t + i * SIXTEENTH, t + (i + 1) * SIXTEENTH, mid, 80))
        return t + 24 * SIXTEENTH

    scale_steps = [0, 2, 4, 5, 7, 9, 11]
    base = max(lo, mid - 12)
    scale = [p for p in (base + 12 * o + s for o in range(3) for s in scale_steps) if p <= min(hi, base + 24)]
    scale = scale + scale[-2::-1]

    def legato(t: float) -> float:
        for i, p in enumerate(scale):
            notes.append((t + i * SIXTEENTH, t + (i + 1) * SIXTEENTH + 0.01, p, 80))
        return t + len(scale) * SIXTEENTH + 0.01

    def detached(t: float) -> float:
        for i, p in enumerate(scale):
            notes.append((t + 2 * i * SIXTEENTH, t + 2 * i * SIXTEENTH + 0.09, p, 90))
        return t + 2 * len(scale) * SIXTEENTH

    def sweep(t: float) -> float:
        for i, p in enumerate(range(plo, phi + 1)):
            notes.append((t + i * 0.5, t + i * 0.5 + 0.45, p, 80))
        return t + (phi - plo + 1) * 0.5

    def dynamics(t: float) -> float:
        for i, v in enumerate((30, 48, 64, 80, 100, 116, 127)):
            notes.append((t + i * 1.2, t + i * 1.2 + 1.0, mid, v))
        return t + 7 * 1.2

    for name, body in (("sustain", sustain), ("repeat", repeat), ("legato", legato), ("detached", detached),
                       ("sweep", sweep), ("dynamics", dynamics)):
        section(name, body)
    return notes, sections


def write_track(tr: mido.MidiTrack, notes, channel: int, program: int, bank: int | None) -> None:
    if bank is not None and channel != 9:
        tr.append(mido.Message("control_change", channel=channel, control=0, value=bank % 128, time=0))
    tr.append(mido.Message("program_change", channel=channel, program=program, time=0))
    events = []
    for s, e, p, v in notes:
        events.append((round(e * TPS), 0, mido.Message("note_off", channel=channel, note=p, velocity=0)))
        events.append((round(s * TPS), 1, mido.Message("note_on", channel=channel, note=p, velocity=v)))
    events.sort(key=lambda x: (x[0], x[1]))
    last = 0
    for tick, _, m in events:
        m.time = tick - last
        last = tick
        tr.append(m)
    tr.append(mido.MetaMessage("end_of_track", time=TPS * 2))


def new_midi(name: str) -> tuple[mido.MidiFile, mido.MidiTrack]:
    mid = mido.MidiFile(ticks_per_beat=960)
    tr = mido.MidiTrack()
    tr.append(mido.MetaMessage("track_name", name=name, time=0))
    tr.append(mido.MetaMessage("set_tempo", tempo=500000, time=0))
    mid.tracks.append(tr)
    return mid, tr


CHORD = {  # chord tones per section, as an offset from the part's comfortable middle rounded to a B♭ major triad
    "cornets": [70, 74, 77], "horns": [62, 65, 70], "baritones": [58, 62, 65], "trombones": [53, 58, 62],
    "euphoniums": [58, 62, 58], "basses": [34, 41, 34], "percussion": [],
}


def band_phrase(mapping: dict) -> tuple[dict[str, list], tuple[float, float]]:
    """All parts at once: three 4 s chords, cornets add 16ths above, drums keep time."""
    out: dict[str, list] = {}
    t0 = 0.5
    for name, part in mapping["parts"].items():
        inst = INSTRUMENTS[part["instrument"]]
        notes = []
        if inst.id == "drum-kit":
            for i in range(int(12 / 0.5)):
                notes.append((t0 + i * 0.5, t0 + i * 0.5 + 0.1, 42, 80))
                if i % 2 == 0:
                    notes.append((t0 + i * 0.5, t0 + i * 0.5 + 0.1, 36, 90))
        else:
            lo, hi = inst.comfortable
            for c in range(3):
                p = CHORD[inst.section][c]
                while p < lo:
                    p += 12
                while p > hi:
                    p -= 12
                notes.append((t0 + 4 * c, t0 + 4 * c + 3.9, p, 80))
            if name in ("Solo Cornet", "Repiano Cornet", "Soprano Cornet", "1st Cornet"):
                for i in range(int(12 / SIXTEENTH)):
                    notes.append((t0 + i * SIXTEENTH, t0 + (i + 1) * SIXTEENTH, 77 + [0, 2, 4, 5][i % 4] - (5 if name == "Repiano Cornet" else 0), 90))
        out[name] = notes
    return out, (t0, t0 + 12.0)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=str(ROOT / "data" / "sounds" / "phrases"))
    args = ap.parse_args()
    mapping = json.loads((HERE / "mapping.json").read_text())
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    meta = {"lineups": lineups(mapping), "parts": {}}
    for name, part in mapping["parts"].items():
        if part["instrument"] == "drum-kit":
            continue
        notes, sections = part_phrases(part)
        bs = part["band_soundfont"]
        mid, tr = new_midi(slug(name))
        write_track(tr, notes, 0, bs["program"], bs["bank"])
        mid.save(str(out / f"{slug(name)}.mid"))
        meta["parts"][name] = {"file": f"{slug(name)}.mid", "sections": sections, "notes": notes}
    band, span = band_phrase(mapping)
    mid, tr0 = new_midi("band")
    tr0.append(mido.MetaMessage("end_of_track", time=0))
    ch = 0
    for name, notes in band.items():
        bs = mapping["parts"][name]["band_soundfont"]
        drum = mapping["parts"][name]["instrument"] == "drum-kit"
        channel = 9 if drum else ch
        if not drum:
            ch = ch + 1 + (ch + 1 == 9)
        tr = mido.MidiTrack()
        tr.append(mido.MetaMessage("track_name", name=slug(name), time=0))
        write_track(tr, notes, channel % 16, bs["program"], None if drum else bs["bank"])
        mid.tracks.append(tr)
        meta.setdefault("band", {})[name] = {"channel": channel % 16, "notes": notes}
    mid.save(str(out / "band.mid"))
    meta["band_span"] = span
    (out / "phrases.json").write_text(json.dumps(meta, indent=1, ensure_ascii=False))
    print(f"{out}: {len(meta['parts'])} part phrases + band.mid ({len(band)} parts)")


def slug(name: str) -> str:
    return name.replace("♭", "b").replace(" ", "-").lower()


if __name__ == "__main__":
    main()
