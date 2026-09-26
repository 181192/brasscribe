"""Play every preset of the band SoundFont through FluidSynth and check it sounds.

    uv run --project sounds python sounds/sf2play.py [data/sounds/band/brasscribe-band.sf2]

Writes a MIDI file that selects each brass preset in turn (CC0 bank select + program change
on channel 1) and plays one mf note in the middle of the part's comfortable range, then
plays kick, snare and closed hi-hat on channel 10 (bank 128). Renders it with FluidSynth
and reports per preset the RMS level and the pYIN pitch against the note played.
Also writes the MIDI (sf2play.mid) and the plan (sf2play.tsv: bank, program, note, label) next to
the SoundFont so native players can run the same probe (sounds/tools/avsampler_probe.swift).
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

import librosa
import mido
import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "music" / "src"))
from brasscribe_music.instruments import INSTRUMENTS  # noqa: E402

SR = 44100
MSBASIC = HERE.parent / "data" / "sounds" / "raw" / "msbasic" / "MS Basic.sf3"
NOTE_S, GAP_S = 1.0, 0.5
DRUMS = [36, 38, 42]


def probe_plan(mapping: dict) -> list[dict]:
    plan = []
    for name, part in mapping["parts"].items():
        bs = part.get("band_soundfont")
        if not bs or bs["bank"] == 128:
            continue
        lo, hi = INSTRUMENTS[part["instrument"]].comfortable
        for art, bank in (("sus", bs["bank"]), ("stac", bs["staccato_bank"])):
            plan.append({"part": name, "art": art, "bank": bank, "program": bs["program"], "note": (lo + hi) // 2})
    for n in DRUMS:
        plan.append({"part": "Percussion", "art": f"drum {n}", "bank": 128, "program": 0, "note": n})
    return plan


def write_probe(plan: list[dict], path: Path) -> None:
    mid = mido.MidiFile(ticks_per_beat=480)  # 120 bpm: 960 ticks per second
    tr = mido.MidiTrack()
    mid.tracks.append(tr)
    tps = 960
    for step in plan:
        ch = 9 if step["bank"] == 128 else 0
        if ch == 0:
            tr.append(mido.Message("control_change", channel=0, control=0, value=step["bank"], time=0))
            tr.append(mido.Message("control_change", channel=0, control=32, value=0, time=0))
            tr.append(mido.Message("program_change", channel=0, program=step["program"], time=0))
        tr.append(mido.Message("note_on", channel=ch, note=step["note"], velocity=80, time=0))
        tr.append(mido.Message("note_off", channel=ch, note=step["note"], velocity=0, time=int(NOTE_S * tps)))
        tr.append(mido.Message("control_change", channel=ch, control=121, value=0, time=int(GAP_S * tps)))
    mid.save(str(path))


def main() -> None:
    sf2 = Path(sys.argv[1] if len(sys.argv) > 1 else HERE.parent / "data" / "sounds" / "band" / "brasscribe-band.sf2")
    mapping = json.loads((HERE / "mapping.json").read_text())
    plan = probe_plan(mapping)
    midi = sf2.with_name("sf2play.mid")
    write_probe(plan, midi)
    sf2.with_name("sf2play.tsv").write_text("".join(
        f"{st['bank']}\t{st['program']}\t{st['note']}\t{st['part']} {st['art']}\n" for st in plan))
    wav = Path(tempfile.mkdtemp()) / "probe.wav"
    subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-r", str(SR), "-F", str(wav), str(sf2), str(midi)],
                   check=True, capture_output=True)
    x, _ = sf.read(str(wav), dtype="float64", always_2d=True)
    x = x.mean(axis=1)
    # the drum kit is copied from MS Basic: render the same probe there and compare
    ref_wav = wav.with_name("msbasic.wav")
    subprocess.run(["fluidsynth", "-ni", "-q", "-R", "0", "-C", "0", "-r", str(SR), "-F", str(ref_wav),
                    str(MSBASIC), str(midi)], check=True, capture_output=True)
    ref, _ = sf.read(str(ref_wav), dtype="float64", always_2d=True)
    ref = ref.mean(axis=1)
    bad = 0
    step_s = NOTE_S + GAP_S
    for i, st in enumerate(plan):
        seg = x[int(i * step_s * SR) : int((i * step_s + NOTE_S) * SR)]
        rms = float(np.sqrt(np.mean(seg ** 2))) if len(seg) else 0.0
        cents = ""
        if st["bank"] != 128 and rms > 1e-4:
            f0 = 440 * 2 ** ((st["note"] - 69) / 12)
            est, v, _ = librosa.pyin(seg[int(0.05 * SR) : int(0.35 * SR)], fmin=f0 / 2, fmax=f0 * 2, sr=SR,
                                     frame_length=4096 if f0 > 80 else 8192)
            est = est[v & ~np.isnan(est)]
            cents = f"{1200 * np.log2(np.median(est) / f0):+6.0f} c" if len(est) else "  no f0"
        if st["bank"] == 128:
            rseg = ref[int(i * step_s * SR) : int((i * step_s + NOTE_S) * SR)]
            diff = 20 * np.log10(max(rms, 1e-9) / max(float(np.sqrt(np.mean(rseg ** 2))), 1e-9))
            cents = f"{diff:+5.1f} dB vs MS Basic"
            ok = np.abs(seg).max() > 0.01 and abs(diff) < 1.0
        else:
            ok = rms > 1e-3 and bool(cents) and "no" not in cents and abs(float(cents.split()[0])) < 50
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} bank {st['bank']:3d} prog {st['program']:3d} {st['part']:15s} {st['art']:8s} "
              f"note {st['note']:3d} rms {20 * np.log10(max(rms, 1e-9)):6.1f} dBFS {cents}")
    print(f"{len(plan) - bad}/{len(plan)} presets sound (FluidSynth); probe MIDI: {midi}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
