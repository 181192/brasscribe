"""A phone-sized variant of the band SoundFont: brasscribe-band-mobile.sf2.

    uv run --project sounds python apps/android/scripts/mobile_soundfont.py [-o PATH] [--rate 22050]

alphaTab's Kotlin synth holds every sample of a SoundFont as floats on the Java heap, so the full
brasscribe-band.sf2 (149 MB at 16 bits) runs out of memory on Android (576 MB large heap). This
variant keeps the same presets at the same (bank, program) and the same drum kit, with:
  * the sustain presets only (staccato banks bank + 64 are left out; alphaTab falls back to bank 0),
  * the first target of layered parts only (the cornet desks lose their +-3 cent second layer),
  * samples resampled to --rate (loop points scaled), 16-bit.
Balance stays in mapping.json (channel_gain_db), exactly as for the full SoundFont.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import soxr

REPO = Path(__file__).resolve().parents[3]
SOUNDS = REPO / "sounds"
sys.path.insert(0, str(SOUNDS))
import band  # noqa: E402
import sf2  # noqa: E402


def resampled(s: sf2.Sample, rate: int) -> sf2.Sample:
    if s.rate <= rate:
        return s
    ratio = rate / s.rate
    data = soxr.resample(s.data, s.rate, rate, quality="HQ")
    loop = None
    if s.loop:
        a, b = int(round(s.loop[0] * ratio)), int(round(s.loop[1] * ratio))
        if 8 <= a < b <= len(data) - 8:
            loop = (a, b)
    return sf2.Sample(s.name, data, rate, s.root, s.cents, loop)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=str(REPO / "data" / "sounds" / "band" / "brasscribe-band-mobile.sf2"))
    ap.add_argument("--rate", type=int, default=22050)
    args = ap.parse_args()
    mapping = json.loads((SOUNDS / "mapping.json").read_text())
    brass = {n: p for n, p in mapping["parts"].items() if p["players"][0]["target"] != "msbasic-drums"}
    bank = band.Bank()
    for name, part in brass.items():
        bs = part["band_soundfont"]
        tid = band.layers(part["players"])[0]
        short = name.replace("♭", "b").replace("Cornet", "Cnt").replace("Trombone", "Tbn").replace("Baritone", "Bar")
        bank.presets.append(sf2.RawPreset(f"{short} sus"[:19], bs["program"], bs["bank"], [sf2.RawZone([], [], bank.target(tid, "sus"))]))
    bank.drum_kit(band.MSBASIC, mapping["parts"]["Percussion"]["band_soundfont"]["program"])
    samples = [resampled(s, args.rate) for s in bank.samples]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sf2.write_raw(args.out, "brasscribe band mobile", samples, bank.instruments, bank.presets, bits=16,
                  comment="Phone variant of brasscribe-band.sf2 (sustain presets, first layer, "
                          f"{args.rate} Hz): VSCO 2 CE (CC0), Univ. of Iowa MIS; drum kit from MuseScore MS Basic (MIT).")
    print(f"{args.out}: {Path(args.out).stat().st_size / 1e6:.1f} MB, {len(samples)} samples, {len(bank.presets)} presets")


if __name__ == "__main__":
    main()
