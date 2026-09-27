"""Build one SoundFont for the whole band: brasscribe-band.sf2.

    uv run --project sounds python sounds/band.py [--bits 16|24] [-o PATH]

Reads the built targets (data/sounds/built/<target>/regions.json + samples, from build.py)
and the program map in sounds/mapping.json (`parts[].band_soundfont`, `band_soundfont`):
  * every brass part gets a sustain preset at (bank, program) and a staccato preset at
    (bank + 64, program); program = the part's General MIDI program, bank 0 = section principal;
  * parts whose players use several targets layer them, detuned +-3 cents;
  * part balance is not in the SoundFont (engines disagree on preset attenuation): it is written
    to mapping.json as parts[].band_soundfont.channel_gain_db for the apps' channel volume;
  * bank 128 program 0 is the General MIDI Standard drum kit taken from MS Basic (MIT),
    decoded from its Ogg Vorbis samples, with its zones, envelopes and modulators unchanged
    (stereo halves stored as mono samples, each with its zone's pan).
Every target instrument and sample is stored once, however many presets use it.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sf2  # noqa: E402
from build import BUILT, SR, VEL_SPAN_DB  # noqa: E402
from sf3 import SoundFontReader  # noqa: E402

RAW = HERE.parent / "data" / "sounds" / "raw"
MSBASIC = RAW / "msbasic" / "MS Basic.sf3"
G_FINE_TUNE = 52
LAYER_DETUNE_CENTS = 3


class Bank:
    def __init__(self) -> None:
        self.samples: list[sf2.Sample] = []
        self.instruments: list[sf2.RawInstrument] = []
        self.presets: list[sf2.RawPreset] = []
        self._sample_index: dict[str, int] = {}
        self._inst_index: dict[str, int] = {}

    def target(self, tid: str, art: str) -> int:
        """Instrument index of a built target's articulation (loaded once)."""
        key = f"{tid}/{art}"
        if key in self._inst_index:
            return self._inst_index[key]
        table = json.loads((BUILT / tid / "regions.json").read_text())
        a = table["articulations"][art]
        ins = sf2.Instrument(name=f"{tid}-{art}", release_s=a["release_s"], vel_span_db=VEL_SPAN_DB)
        for r in a["regions"]:
            file = r["variants"][0]
            skey = f"{tid}/{file}"
            if skey not in self._sample_index:
                s = next(s for s in a["samples"] if s["file"] == file)
                data, sr = sf.read(str(BUILT / tid / "samples" / file), dtype="float64")
                assert sr == SR
                self._sample_index[skey] = len(self.samples)
                self.samples.append(sf2.Sample(file[:-4][-19:], data, SR, s["midi"], int(round(-s["cents"])),
                                               tuple(s["loop"]) if s["loop"] else None))
            ins.zones.append(sf2.Zone(self._sample_index[skey], r["lokey"], r["hikey"], r["lovel"], r["hivel"],
                                      int(round(-r["volume_db"] * 10)), bool(r["loop"])))
        self._inst_index[key] = len(self.instruments)
        self.instruments.append(sf2.target_instrument(ins))
        return self._inst_index[key]

    def _copy_sample(self, src: SoundFontReader, index: int, samp_map: dict[int, int]) -> int:
        """Copy one sample and return its new index.

        Stereo halves are stored as mono samples: MS Basic's kit has stereo links that do not
        point back at each other, which strict loaders reject; each half keeps its zone's pan.
        Loops that do not leave 8 frames at either end are dropped (the kit never loops).
        """
        if index not in samp_map:
            s = src.sample(index)
            loop = s.loop if s.loop and 8 <= s.loop[0] < s.loop[1] <= len(s.data) - 8 else None
            samp_map[index] = len(self.samples)
            self.samples.append(sf2.Sample(s.name[:19], s.data, s.rate, s.root, s.cents, loop))
        return samp_map[index]

    def drum_kit(self, path: Path, program: int = 0) -> None:
        """Copy the bank-128 preset `program` (instruments, zones, samples) from an SF2/SF3."""
        src = SoundFontReader(str(path))
        preset = next(p for p in src.presets() if p.bank == 128 and p.program == program)
        inst_map: dict[int, int] = {}
        samp_map: dict[int, int] = {}
        zones = []
        for pz in preset.zones:
            ref = None
            if pz.ref is not None:
                if pz.ref not in inst_map:
                    ri = src.instrument(pz.ref)
                    izones = []
                    for iz in ri.zones:
                        sref = None
                        if iz.ref is not None:
                            sref = self._copy_sample(src, iz.ref, samp_map)
                        izones.append(sf2.RawZone(iz.gens, iz.mods, sref))
                    inst_map[pz.ref] = len(self.instruments)
                    self.instruments.append(sf2.RawInstrument(ri.name, izones))
                ref = inst_map[pz.ref]
            zones.append(sf2.RawZone(pz.gens, pz.mods, ref))
        self.presets.append(sf2.RawPreset(f"{preset.name} kit", program, 128, zones))


def layers(players: list[dict]) -> list[str]:
    seen: list[str] = []
    for pl in players:
        if pl["target"] not in seen:
            seen.append(pl["target"])
    return seen


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bits", type=int, choices=[16, 24], default=24)
    ap.add_argument("-o", "--out", default=str(BUILT.parent / "band" / "brasscribe-band.sf2"))
    args = ap.parse_args()
    mapping = json.loads((HERE / "mapping.json").read_text())
    brass = {name: p for name, p in mapping["parts"].items()
             if p["players"][0]["target"] != "msbasic-drums" and "preset_of" not in p}
    loudest = max(p.get("gain_db", 0.0) for p in brass.values())
    bank = Bank()
    table = []
    for name, part in brass.items():
        bs = part["band_soundfont"]
        targets = layers(part["players"])
        # Balance is NOT baked into the SoundFont: AVAudioUnitSampler applies almost none of a
        # preset-level attenuation and FluidSynth applies 0.4 of it, so the apps set it as channel
        # volume instead (parts[].band_soundfont.channel_gain_db, written back to mapping.json).
        channel_gain = round(part.get("gain_db", 0.0) - loudest - (3.0 if len(targets) > 1 else 0.0), 1)
        bs["channel_gain_db"] = channel_gain
        for art, b in (("sus", bs["bank"]), ("stac", bs["staccato_bank"])):
            zones = []
            for li, tid in enumerate(targets):
                gens = []
                if len(targets) > 1:
                    gens.append((G_FINE_TUNE, LAYER_DETUNE_CENTS if li % 2 == 0 else -LAYER_DETUNE_CENTS))
                zones.append(sf2.RawZone(gens, [], bank.target(tid, art)))
            short = name.replace("♭", "b").replace("Cornet", "Cnt").replace("Trombone", "Tbn").replace("Baritone", "Bar")
            bank.presets.append(sf2.RawPreset(f"{short} {art}"[:19], bs["program"], b, zones))
        table.append((name, bs["program"], bs["bank"], bs["staccato_bank"], "+".join(targets), channel_gain))
    for part in mapping["parts"].values():  # one-player parts that play a section principal's preset
        if "preset_of" in part:
            part["band_soundfont"] = dict(mapping["parts"][part["preset_of"]]["band_soundfont"])
    drum = mapping["parts"]["Percussion"]["band_soundfont"]
    drum["channel_gain_db"] = round(mapping["parts"]["Percussion"].get("gain_db", 0.0) - loudest, 1)
    bank.drum_kit(MSBASIC, drum["program"])
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sf2.write_raw(args.out, "brasscribe band", bank.samples, bank.instruments, bank.presets, bits=args.bits,
                  comment="brasscribe brass band: VSCO 2 CE (CC0) and Univ. of Iowa MIS samples adapted per part; "
                          "drum kit from MuseScore MS Basic (MIT). See sounds/manifest.json and sounds/mapping.json.")
    (HERE / "mapping.json").write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n")
    size = Path(args.out).stat().st_size
    print(f"{args.out}: {size / 1e6:.1f} MB, {args.bits}-bit, {len(bank.samples)} samples, "
          f"{len(bank.instruments)} instruments, {len(bank.presets)} presets")
    for row in sorted(table, key=lambda r: (r[1], r[2])):
        print(f"  program {row[1]:3d} bank {row[2]:3d} (stac {row[3]:3d})  {row[0]:15s} {row[4]:20s} channel {row[5]:+.1f} dB")
    print(f"  program {drum['program']:3d} bank 128              Percussion      MS Basic Standard kit")


if __name__ == "__main__":
    main()
