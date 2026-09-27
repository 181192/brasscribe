"""A phone-sized variant of the band SoundFont: brasscribe-band-mobile.sf2.

    uv run --project sounds python apps/android/scripts/mobile_soundfont.py [-o PATH] [--rate 22050]

alphaTab's Kotlin synth holds every sample of a SoundFont as floats on the Java heap, so the full
brasscribe-band.sf2 (149 MB at 16 bits) runs out of memory on Android (576 MB large heap). This
variant keeps the same presets at the same (bank, program), the same layering and the same drum kit,
with:
  * the sustain presets only (staccato banks bank + 64 are left out; alphaTab falls back to bank 0),
  * samples resampled to --rate, 16-bit, with every loop rebuilt at the new rate (below).
Layered parts keep both targets (the cornet desks' +-3 cent pair): both cornet builds are in the file
anyway as the first desk of other parts, so the layers cost no sample data, and channel_gain_db in
mapping.json (which subtracts 3 dB for a layered preset) stays right for this file too.

Loops. Scaling the loop points of a resampled sample does not give a seamless loop: the points land
between samples, and the resampler's filter sees the unfaded audio after the loop end rather than the
loop start, so the jump clicks. Each looped sample is therefore resampled *unrolled* (the audio up to
the loop end followed by two more copies of the loop body), the new loop start is placed at the scaled
start, the new loop end is searched within +-SEARCH samples of the scaled end for the best waveform
match with the audio before the loop start, and the last XFADE samples before the end are crossfaded
with the samples before the start (as sounds/build.py does at 44.1 kHz). The audio after the loop end
is the loop's own continuation, so interpolation past the end reads what the loop plays next.

Re-run this after sounds/band.py rebuilds the full SoundFont.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import soxr

REPO = Path(__file__).resolve().parents[3]
SOUNDS = REPO / "sounds"
sys.path.insert(0, str(SOUNDS))
import band  # noqa: E402
import sf2  # noqa: E402

SEARCH = 64  # samples either side of the scaled loop end
MATCH = 256  # samples compared before the loop start and the loop end
XFADE = 512  # samples crossfaded before the new loop end
TAIL = 64  # samples kept after the loop end (as build.py does)


def relooped(data: np.ndarray, loop: tuple[int, int], rate_in: int, rate_out: int) -> tuple[np.ndarray, tuple[int, int] | None]:
    a, b = loop
    ratio = rate_out / rate_in
    body = data[a:b]
    unrolled = np.concatenate([data[:b], body, body])
    y = soxr.resample(unrolled, rate_in, rate_out, quality="HQ")
    na = int(round(a * ratio))
    period = (b - a) * ratio
    guess = int(round(na + period))
    ref = y[na - MATCH: na]
    if na - MATCH < 0 or guess + SEARCH + TAIL > len(y):
        return y[: int(round(len(data) * ratio))], None
    best, nb = -np.inf, guess
    for cand in range(guess - SEARCH, guess + SEARCH + 1):
        seg = y[cand - MATCH: cand]
        c = float(np.dot(ref, seg) / (np.linalg.norm(ref) * np.linalg.norm(seg) + 1e-12))
        if c > best:
            best, nb = c, cand
    out = y[: nb + TAIL].copy()
    xf = min(XFADE, (nb - na) // 2, na)
    t = np.linspace(0.0, 1.0, xf)
    out[nb - xf: nb] = y[nb - xf: nb] * (1 - t) + y[na - xf: na] * t
    # past the end the player interpolates into what the loop plays next: the loop start
    out[nb: nb + TAIL] = y[na: na + TAIL]
    if not (8 <= na < nb <= len(out) - 8):
        return out, None
    return out, (na, nb)


def resampled(s: sf2.Sample, rate: int) -> sf2.Sample:
    if s.rate <= rate:
        return s
    if s.loop:
        data, loop = relooped(s.data, s.loop, s.rate, rate)
    else:
        data, loop = soxr.resample(s.data, s.rate, rate, quality="HQ"), None
    return sf2.Sample(s.name, data, rate, s.root, s.cents, loop, s.kind, s.link)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("-o", "--out", default=str(REPO / "data" / "sounds" / "band" / "brasscribe-band-mobile.sf2"))
    ap.add_argument("--rate", type=int, default=22050)
    args = ap.parse_args()
    mapping = json.loads((SOUNDS / "mapping.json").read_text())
    brass = {n: p for n, p in mapping["parts"].items() if p["players"][0]["target"] != "msbasic-drums" and "preset_of" not in p}
    bank = band.Bank()
    for name, part in brass.items():
        bs = part["band_soundfont"]
        targets = band.layers(part["players"])
        zones = []
        for li, tid in enumerate(targets):
            gens = []
            if len(targets) > 1:
                gens.append((band.G_FINE_TUNE, band.LAYER_DETUNE_CENTS if li % 2 == 0 else -band.LAYER_DETUNE_CENTS))
            zones.append(sf2.RawZone(gens, [], bank.target(tid, "sus")))
        short = name.replace("♭", "b").replace("Cornet", "Cnt").replace("Trombone", "Tbn").replace("Baritone", "Bar")
        bank.presets.append(sf2.RawPreset(f"{short} sus"[:19], bs["program"], bs["bank"], zones))
    bank.drum_kit(band.MSBASIC, mapping["parts"]["Percussion"]["band_soundfont"]["program"])
    samples = [resampled(s, args.rate) for s in bank.samples]
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sf2.write_raw(args.out, "brasscribe band mobile", samples, bank.instruments, bank.presets, bits=16,
                  comment="Phone variant of brasscribe-band.sf2 (sustain presets, "
                          f"{args.rate} Hz, loops rebuilt): VSCO 2 CE (CC0), Univ. of Iowa MIS; drum kit from MuseScore MS Basic (MIT).")
    print(f"{args.out}: {Path(args.out).stat().st_size / 1e6:.1f} MB, {len(samples)} samples, {len(bank.presets)} presets")


if __name__ == "__main__":
    main()
