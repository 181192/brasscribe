"""Build one SoundFont for the whole band: brasscribe-band.sf2.

    uv run --project sounds python sounds/band.py [--bits 16|24] [-o PATH]

Reads the built targets (data/sounds/built/<target>/regions.json + samples, from build.py)
and the program map in sounds/mapping.json (`parts[].band_soundfont`, `band_soundfont`):
  * every brass part gets a sustain preset at (bank, program) and a staccato preset at
    (bank + 64, program); program = the part's General MIDI program, bank 0 = section principal;
  * parts whose players use several targets layer them, detuned +-3 cents;
  * parts that share a target play different desk variants of it (players[].variant): the same
    samples, but each key sounds a different recording (the neighbouring sampled note, or another
    round robin), so two parts in unison add up like two players instead of one waveform doubled;
  * part balance is not in the SoundFont (engines disagree on preset attenuation): it is written
    to mapping.json as parts[].band_soundfont.channel_gain_db for the apps' channel volume;
  * bank 128 program 0 is the band kit: the General MIDI Standard kit from MS Basic (MIT) with its
    bass drums, snares and crash cymbals replaced by VSCO 2 CE (CC0) concert percussion; bank 128
    program 1 is the MS Basic Standard kit unchanged (a pop kit). MS Basic is decoded from its
    Ogg Vorbis samples with its zones, envelopes and modulators unchanged (stereo halves stored as
    mono samples, each with its zone's pan).
Every target instrument and sample is stored once, however many presets use it.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np
import soundfile as sf

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import sf2  # noqa: E402
from build import BUILT, DYN_LEVEL_DB, MAX_STRETCH, SR, VEL_SPAN_DB, vel_curve_db  # noqa: E402
from dsp import apply_eq, k_weight  # noqa: E402
from sf3 import SoundFontReader  # noqa: E402

RAW = HERE.parent / "data" / "sounds" / "raw"
MSBASIC = RAW / "msbasic" / "MS Basic.sf3"
VSCO_PERC = RAW / "vsco2ce" / "VSCO 1 Percussion"
G_PAN = 17
G_RELEASE_VOL_ENV = 38
G_KEY_RANGE = 43
G_VEL_RANGE = 44
G_INITIAL_ATTENUATION = 48
G_FINE_TUNE = 52
G_SAMPLE_MODES = 54
G_OVERRIDING_ROOT_KEY = 58
LAYER_DETUNE_CENTS = 3
# alphaSynth steps a voice's gain once per 64-sample block, so a release is a staircase: on the lowest notes, whose
# waveform is a train of loud pulses 30-40 ms apart, a step that lands on a pulse is a click (B-flat Bass B-flat0).
# Keys up to LOW_RELEASE_KEY release LOW_RELEASE_FACTOR times slower: smaller steps, and a pedal note rings a little.
LOW_RELEASE_KEY = 27
LOW_RELEASE_FACTOR = 2.0
# A key that has no other recording within MAX_STRETCH semitones for a desk variant plays the same
# sample as variant 0, detuned by this much, so a unison of the two beats instead of doubling.
FALLBACK_DETUNE_CENTS = 4

# The band kit's concert percussion (VSCO 1 Percussion, CC0): (keys, [(velocity high, file)], seconds kept,
# release s). Every sample is scaled so its K-weighted level over the first 400 ms matches the MS Basic drum it
# replaces (KIT_REPLACES) plus KIT_TRIM_DB; the SF2 velocity curve then plays both kits alike, and the
# layers change the tone (a harder hit is brighter), not the level.
KIT = [
    ((35, 36), [(40, "drums/bass/bdrum_muted_pp_1.wav"), (70, "drums/bass/bdrum_muted_mp_1.wav"),
                (95, "drums/bass/bdrum_muted_mf_1.wav"), (115, "drums/bass/bdrum_muted_ff_1.wav"),
                (127, "drums/bass/bdrum_muted_fff_1.wav")], 1.6, 1.2),
    ((38, 40), [(35, "drums/snare/drum1/snare1_pp_1.wav"), (55, "drums/snare/drum1/snare1_p_1.wav"),
                (75, "drums/snare/drum1/snare1_mp_1.wav"), (98, "drums/snare/drum1/snare1_f_1.wav"),
                (115, "drums/snare/drum1/snare1_ff_1.wav"), (127, "drums/snare/drum1/snare1_fff_1.wav")], 0.8, 0.6),
    ((49,), [(50, "varMetal/Cymbals/clash/crash_hit_pp_loose.wav"), (85, "varMetal/Cymbals/clash/crash_hit_mp_loose.wav"),
             (110, "varMetal/Cymbals/clash/crash_hit_ff_loose.wav"), (127, "varMetal/Cymbals/clash/crash_hit_fff_loose.wav")], 4.0, 2.0),
    ((57,), [(85, "varMetal/Cymbals/clash/crash_hit_ff_tight.wav"), (127, "varMetal/Cymbals/clash/crash_hit_fff_loose_2.wav")], 3.0, 1.5),
]
KIT_REPLACES = {35: 36, 36: 36, 38: 38, 40: 40, 49: 49, 57: 57}  # our key -> the MS Basic key whose level it takes
# The snares measured 0.6-1.0 dB over MS Basic's (K-weighted, each hit's first 400 ms, velocities 47-127), hence
# their trim. The bass drum needs none: it plays under MS Basic's kick preset zone (msbasic_levels), and is
# peak-limited (its first milliseconds peak far above its body); against MS Basic's kick at velocity 80 it measures
# +0.5 dB in FluidSynth and AVAudioUnitSampler (1 s RMS) and +0.9 LU on alphaSynth. The crashes carry no trim: MS Basic
# attenuates its crashes 13-17 dB in the instrument zone, which alphaSynth applies in full, FluidSynth at 0.4 and
# AVAudioUnitSampler hardly at all; the VSCO crashes have that attenuation baked into the sample instead.
KIT_TRIM_DB = {36: 0.0, 38: -0.6, 40: -1.0, 49: 0.0, 57: 0.0}
KIT_HIGHPASS_HZ = 35  # the concert bass drum's sub-sonic rumble below the kick's fundamental


class Bank:
    def __init__(self) -> None:
        self.samples: list[sf2.Sample] = []
        self.instruments: list[sf2.RawInstrument] = []
        self.presets: list[sf2.RawPreset] = []
        self._sample_index: dict[str, int] = {}
        self._inst_index: dict[str, int] = {}

    def _sample(self, tid: str, s: dict) -> int:
        skey = f"{tid}/{s['file']}"
        if skey not in self._sample_index:
            data, sr = sf.read(str(BUILT / tid / "samples" / s["file"]), dtype="float64")
            assert sr == SR
            self._sample_index[skey] = len(self.samples)
            self.samples.append(sf2.Sample(s["file"][:-4][-19:], data, SR, s["midi"], int(round(-s["cents"])),
                                           tuple(s["loop"]) if s["loop"] else None))
        return self._sample_index[skey]

    def target(self, tid: str, art: str, variant: int = 0) -> int:
        """Instrument index of a built target's articulation, in desk variant `variant` (loaded once)."""
        key = f"{tid}/{art}/{variant}"
        if key in self._inst_index:
            return self._inst_index[key]
        table = json.loads((BUILT / tid / "regions.json").read_text())
        a = table["articulations"][art]
        by_file = {s["file"]: s for s in a["samples"]}
        ins = sf2.Instrument(name=f"{tid}-{art}" + (f"-{variant}" if variant else ""), release_s=a["sf2_release_s"],
                             vel_span_db=VEL_SPAN_DB)
        detuned: list[int] = []
        level = {tuple(v): DYN_LEVEL_DB[d] for v, d in zip(a["velocity"], a["layers"])}
        for z in desk_variant(a, variant):
            s = by_file[z["file"]]
            for lo, hi, att_db in velocity_steps(z["lovel"], z["hivel"], level[(z["lovel"], z["hivel"])]):
                ins.zones.append(sf2.Zone(self._sample(tid, s), z["lokey"], z["hikey"], lo, hi,
                                          int(round((att_db - z["volume_db"]) * 10)), bool(s["loop"])))
                if z.get("detune"):
                    detuned.append(len(ins.zones))  # 1-based: zone 0 of the raw instrument is the global zone
        raw = sf2.target_instrument(ins)
        for zi in detuned:
            raw.zones[zi].gens.append((G_FINE_TUNE, z_detune(variant)))
        for z in raw.zones[1:]:
            lokey = dict(z.gens)[G_KEY_RANGE] & 0xFF
            if lokey <= LOW_RELEASE_KEY:
                z.gens.append((G_RELEASE_VOL_ENV, sf2.timecents(a["sf2_release_s"] * LOW_RELEASE_FACTOR)))
        self._inst_index[key] = len(self.instruments)
        self.instruments.append(raw)
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

    def _msbasic(self, path: Path, program: int) -> tuple[SoundFontReader, object, dict[int, int]]:
        """The MS Basic kit preset's instruments, copied once; returns (reader, preset, instrument map)."""
        if not hasattr(self, "_kit_cache"):
            self._kit_cache: dict[tuple[str, int], tuple] = {}
        k = (str(path), program)
        if k in self._kit_cache:
            return self._kit_cache[k]
        src = SoundFontReader(str(path))
        preset = next(p for p in src.presets() if p.bank == 128 and p.program == program)
        inst_map: dict[int, int] = {}
        samp_map: dict[int, int] = {}
        for pz in preset.zones:
            if pz.ref is not None and pz.ref not in inst_map:
                ri = src.instrument(pz.ref)
                izones = [sf2.RawZone(iz.gens, iz.mods, self._copy_sample(src, iz.ref, samp_map) if iz.ref is not None else None)
                          for iz in ri.zones]
                inst_map[pz.ref] = len(self.instruments)
                self.instruments.append(sf2.RawInstrument(ri.name, izones))
        self._kit_cache[k] = (src, preset, inst_map)
        return self._kit_cache[k]

    def drum_kit(self, path: Path, program: int = 0, as_program: int | None = None, name: str | None = None,
                 exclude: set[int] = frozenset(), extra: list[sf2.RawZone] = ()) -> None:
        """A bank-128 preset from the bank-128 preset `program` of an SF2/SF3 (instruments, zones and samples
        copied once), as program `as_program`, without the keys in `exclude`, plus the preset zones `extra`."""
        _, preset, inst_map = self._msbasic(path, program)
        zones = []
        for pz in preset.zones:
            if pz.ref is None:
                zones.append(sf2.RawZone(pz.gens, pz.mods, None))
                continue
            # Keys are left out inside the instrument, not with preset-level key ranges: AVAudioUnitSampler
            # ignores a preset zone's key range and would sound every split copy of the instrument at once.
            zones.append(sf2.RawZone(pz.gens, pz.mods, self._without_keys(inst_map[pz.ref], exclude)))
        zones.extend(extra)
        self.presets.append(sf2.RawPreset(name or f"{preset.name} kit", program if as_program is None else as_program, 128, zones))

    def _without_keys(self, index: int, exclude) -> int:
        """A copy of instrument `index` whose zones leave out the keys in `exclude` (the same samples)."""
        if not exclude:
            return index
        key = f"without/{index}/{sorted(exclude)}"
        if key in self._inst_index:
            return self._inst_index[key]
        src = self.instruments[index]
        zones = []
        for z in src.zones:
            g = dict(z.gens)
            if z.ref is None:
                zones.append(z)
                continue
            kr = g.get(G_KEY_RANGE, 127 << 8)
            lo, hi = kr & 0xFF, kr >> 8
            for a, b in _runs([k for k in range(lo, hi + 1) if k not in exclude]):
                gens = [(G_KEY_RANGE, (b << 8) | a)] + [x for x in z.gens if x[0] != G_KEY_RANGE]
                zones.append(sf2.RawZone(gens, z.mods, z.ref))
        if len(zones) == len(src.zones) and all(a is b for a, b in zip(zones, src.zones)):
            self._inst_index[key] = index  # nothing to leave out
            return index
        self._inst_index[key] = len(self.instruments)
        self.instruments.append(sf2.RawInstrument(src.name[:15] + " band", zones))
        return self._inst_index[key]

    def band_kit(self, program: int = 0) -> None:
        """The band kit: MS Basic Standard with VSCO 2 CE concert bass drum, snare and clash cymbals."""
        src, preset, inst_map = self._msbasic(MSBASIC, 0)
        ref = msbasic_levels(src, preset)
        # the global zone takes MS Basic's kick modulators, so velocity plays both kits' drums alike
        kick = next(src.instrument(pz.ref) for pz in preset.zones if pz.ref is not None and src.instrument(pz.ref).name == "Std Kick")
        mods = next(z.mods for z in kick.zones if z.ref is None)
        # one instrument per MS Basic preset zone our drums take their level from (see msbasic_levels)
        groups: dict[tuple, list[sf2.RawZone]] = {}
        for keys, layers, keep_s, release_s in KIT:
            p_gens = ref[KIT_REPLACES[keys[0]]][1]
            izones = groups.setdefault(p_gens, [sf2.RawZone([(G_RELEASE_VOL_ENV, sf2.timecents(1.0))], mods, None)])
            lovel = 1
            for hivel, rel in layers:
                data = load_drum(VSCO_PERC / rel, keep_s, highpass=KIT_HIGHPASS_HZ if keys[0] <= 36 else None)
                lvl = kit_level_db(data)
                for key in keys:
                    target = ref[KIT_REPLACES[key]][0] + KIT_TRIM_DB[KIT_REPLACES[key]]
                    y = peak_limit(data * 10 ** ((target - lvl) / 20))
                    skey = f"kit/{rel}/{key}"
                    if skey not in self._sample_index:
                        self._sample_index[skey] = len(self.samples)
                        self.samples.append(sf2.Sample(Path(rel).stem[-15:] + f"_{key}", y, SR, key, 0, None))
                    izones.append(sf2.RawZone([(G_KEY_RANGE, (key << 8) | key), (G_VEL_RANGE, (hivel << 8) | lovel),
                                               (G_RELEASE_VOL_ENV, sf2.timecents(release_s)), (G_SAMPLE_MODES, 0),
                                               (G_OVERRIDING_ROOT_KEY, key)], [], self._sample_index[skey]))
                lovel = hivel + 1
        extra = []  # their zones are on the replaced keys only
        for i, (p_gens, izones) in enumerate(groups.items()):
            self.instruments.append(sf2.RawInstrument(f"VSCO concert {i}", izones))
            extra.append(sf2.RawZone(list(p_gens), [], len(self.instruments) - 1))
        replaced = {k for keys, *_ in KIT for k in keys}
        self.drum_kit(MSBASIC, 0, as_program=program, name="Band kit", exclude=replaced, extra=extra)


# The band SoundFont's velocity curve (build.py VEL_CURVE). alphaSynth plays amplitude proportional to velocity
# inside a layer (it ignores the SoundFont's velocity modulators): 2 dB from mp to mf but 6 dB from pp to p. Each
# layer's velocity range is therefore cut into steps at most VEL_STEP_MAX_DB apart, each attenuated so the level
# follows VEL_CURVE. No step boosts, so the curve sits VEL_CURVE_OFFSET_DB under full scale at velocity 127; the
# apps' make-up gain restores the loudness. AVAudioUnitSampler hardly applies zone attenuation: it plays its own
# steep velocity curve, continuous across the layer splits because every layer is baked at one level, and the app
# remaps the score's velocities onto it (playback-levels.json dynamics.sampler_velocity).
VEL_STEP_MAX_DB = 1.0  # 0.5 dB steps overflow the SF2 generator index (65,535)


def _residual(v: int, layer_db: float) -> float:
    """How far a layer at `layer_db` plays over the curve at velocity v on alphaSynth (amplitude ~ velocity)."""
    return layer_db + 20 * np.log10(v / 127) - vel_curve_db(v)


def _curve_offset() -> float:
    """The largest offset under which every layer of LAYER_DYNAMICS reaches the curve over its whole range."""
    from build import LAYER_DYNAMICS, velocity_ranges
    worst = np.inf
    dyn_sets = list(LAYER_DYNAMICS.values()) + [["mf", "ff"]]  # + the solo cornet's named sustain layers
    for dyns in dyn_sets:
        for (lo, hi), d in zip(velocity_ranges(dyns), dyns):
            worst = min(worst, min(_residual(v, DYN_LEVEL_DB[d]) for v in range(lo, hi + 1)))
    return float(worst)


VEL_CURVE_OFFSET_DB = _curve_offset()


def velocity_steps(lovel: int, hivel: int, layer_db: float) -> list[tuple[int, int, float]]:
    """A layer's velocity range as (lo, hi, attenuation dB) steps that follow VEL_CURVE (see above)."""
    out: list[tuple[int, int, float]] = []
    lo = lovel
    while lo <= hivel:
        r = [_residual(v, layer_db) - VEL_CURVE_OFFSET_DB for v in range(lo, hivel + 1)]
        n = 1
        while n < len(r) and max(r[:n + 1]) - min(r[:n + 1]) <= VEL_STEP_MAX_DB:
            n += 1
        out.append((lo, lo + n - 1, max(0.0, float(np.mean(r[:n])))))
        lo += n
    return out


def z_detune(variant: int) -> int:
    return FALLBACK_DETUNE_CENTS if variant % 2 else -FALLBACK_DETUNE_CENTS


def _runs(keys: list[int]) -> list[tuple[int, int]]:
    out: list[tuple[int, int]] = []
    for k in keys:
        if out and out[-1][1] == k - 1:
            out[-1] = (out[-1][0], k)
        else:
            out.append((k, k))
    return out


def load_drum(path: Path, keep_s: float, highpass: float | None = None) -> np.ndarray:
    x, sr = sf.read(str(path), dtype="float64", always_2d=True)
    assert sr == SR, path
    y = x.mean(axis=1)
    if highpass:
        y = apply_eq(y, [{"type": "highpass", "f": highpass, "q": 0.707}])
    on = int(np.argmax(np.abs(y) > np.abs(y).max() * 0.01))
    y = y[max(0, on - int(0.002 * SR)): max(0, on - int(0.002 * SR)) + int(keep_s * SR)].copy()
    fo = min(len(y) // 3, int(0.3 * SR))
    y[len(y) - fo:] *= np.linspace(1, 0, fo) ** 2
    return y


def peak_limit(y: np.ndarray, ceiling: float = 0.95, release_s: float = 0.05) -> np.ndarray:
    """A look-ahead peak limiter for a drum hit: the gain drops to what keeps the next 2 ms under the ceiling
    and recovers over `release_s`. The concert bass drum's first milliseconds peak far above its body."""
    need = np.minimum(1.0, ceiling / (np.abs(y) + 1e-12))
    w = int(0.002 * SR)
    ahead = np.array([need[i:i + w].min() for i in range(len(need))])
    g = np.empty_like(ahead)
    k = np.exp(-1.0 / (release_s * SR))
    cur = 1.0
    for i, v in enumerate(ahead):
        cur = v if v < cur else v + (cur - v) * k
        g[i] = cur
    return y * g


def kit_level_db(y: np.ndarray, sr: int = SR) -> float:
    """K-weighted level over the first 400 ms of a hit."""
    k = k_weight(y, sr)[: int(0.4 * sr)]
    return float(10 * np.log10(np.mean(k ** 2) + 1e-20))


def msbasic_levels(src: SoundFontReader, preset) -> dict[int, tuple[float, tuple]]:
    """Per MS Basic key we replace: its loudest zone's sample level minus the zone's instrument attenuation,
    and the generators of the preset zone that plays it. Our drum on that key sits under a preset zone with
    the same generators, so every player treats the two alike: MS Basic's kick carries a preset-level
    initialAttenuation of -10 dB (a boost), which alphaSynth applies in full, FluidSynth clamps to 0 and
    AVAudioUnitSampler hardly applies; levelled on the sample alone, the concert bass drum came out within
    2 dB of the kick on alphaSynth and 4.5 dB over it in FluidSynth."""
    out: dict[int, tuple[float, tuple]] = {}
    for pz in preset.zones:
        if pz.ref is None:
            continue
        p_gens = tuple(pz.gens)
        ri = src.instrument(pz.ref)
        g_att = 0
        for iz in ri.zones:
            g = dict(iz.gens)
            if iz.ref is None:
                g_att = g.get(G_INITIAL_ATTENUATION, 0)
                continue
            kr = g.get(G_KEY_RANGE, 127 << 8)
            vr = g.get(G_VEL_RANGE, 127 << 8)
            if vr >> 8 < 127:
                continue  # the top velocity layer only
            att = g.get(G_INITIAL_ATTENUATION, g_att)
            for key in set(KIT_REPLACES.values()):
                if (kr & 0xFF) <= key <= (kr >> 8) and key not in out:
                    s = src.sample(iz.ref)
                    out[key] = (kit_level_db(s.data, s.rate) - att / 10, p_gens)
    return out


def desk_variant(a: dict, variant: int) -> list[dict]:
    """The zones of desk variant `variant` of an articulation: variant 0 is the region table as built.

    For variant v > 0 every key of every layer sounds a different recording from variant 0's: another
    round robin of the same note where the note has several, else the v-th nearest other sampled note
    that plays at this layer's level (its own layer, or a level-matched copy), within MAX_STRETCH + v - 1
    semitones; a key with no such note keeps variant 0's sample, detuned by FALLBACK_DETUNE_CENTS."""
    by_file = {s["file"]: s for s in a["samples"]}
    dyns = a["layers"]
    if variant == 0:
        return [{"file": r["variants"][0], "lokey": r["lokey"], "hikey": r["hikey"], "lovel": r["lovel"],
                 "hivel": r["hivel"], "volume_db": r["volume_db"]} for r in a["regions"]]

    def plays_at(s: dict) -> int | None:
        if "copy_of" not in s:
            return s["layer"]
        for li, d in enumerate(dyns):
            if abs(DYN_LEVEL_DB[d] - DYN_LEVEL_DB[dyns[s["layer"]]] - s["gain_db"]) < 0.01:
                return li
        return None
    pool: dict[int, list[dict]] = defaultdict(list)
    for s in a["samples"]:
        li = plays_at(s)
        if li is not None and s.get("rr", 1) == 1:
            pool[li].append(s)
    keys = []
    for r in a["regions"]:
        base = by_file[r["variants"][0]]
        for k in range(r["lokey"], r["hikey"] + 1):
            detune = False
            if len(r["variants"]) > 1:
                f = r["variants"][variant % len(r["variants"])]
            else:
                alts, seen = [], {base["midi"]}
                for s in sorted(pool[r["layer"]], key=lambda s: (abs(s["midi"] - k), s["midi"])):
                    if abs(s["midi"] - k) <= MAX_STRETCH + variant - 1 and s["midi"] not in seen:
                        seen.add(s["midi"])
                        alts.append(s)
                if len(alts) >= variant:
                    f = alts[variant - 1]["file"]
                else:
                    f, detune = base["file"], True
            keys.append({"file": f, "key": k, "lovel": r["lovel"], "hivel": r["hivel"], "volume_db": r["volume_db"],
                         "detune": detune})
    zones: list[dict] = []
    for z in keys:
        last = zones[-1] if zones else None
        if (last and last["file"] == z["file"] and last["lovel"] == z["lovel"] and last["hikey"] == z["key"] - 1
                and last["detune"] == z["detune"]):
            last["hikey"] = z["key"]
        else:
            zones.append({"file": z["file"], "lokey": z["key"], "hikey": z["key"], "lovel": z["lovel"],
                          "hivel": z["hivel"], "volume_db": z["volume_db"], "detune": z["detune"]})
    return zones


def layers(players: list[dict]) -> list[tuple[str, int]]:
    """The distinct (target, desk variant) pairs a part's players use, in order."""
    seen: list[tuple[str, int]] = []
    for pl in players:
        key = (pl["target"], pl.get("variant", 0))
        if key not in seen:
            seen.append(key)
    return seen


def build_bank(mapping: dict, arts: tuple[str, ...] = ("sus", "stac")) -> tuple[Bank, list[tuple]]:
    """Every brass preset (and its staccato when `arts` has it) and both kits. Writes each part's
    channel_gain_db, layered and single_voice_gain_db into `mapping` (see the module docstring)."""
    brass = {name: p for name, p in mapping["parts"].items()
             if p["players"][0]["target"] != "msbasic-drums" and "preset_of" not in p}
    loudest = max(p["balance_lu"] for p in mapping["parts"].values())
    bank = Bank()
    table = []
    for name, part in brass.items():
        bs = part["band_soundfont"]
        targets = layers(part["players"])
        # Balance is NOT baked into the SoundFont: AVAudioUnitSampler applies almost none of a
        # preset-level attenuation and FluidSynth applies 0.4 of it, so the apps set it as channel
        # volume instead (parts[].band_soundfont.channel_gain_db, written back to mapping.json).
        channel_gain = round(part["balance_lu"] - loudest - (3.0 if len(targets) > 1 else 0.0), 1)
        bs["channel_gain_db"] = channel_gain
        # a player that sounds one target for this part (the SFZ tier) has no second layer to compensate for
        bs["layered"] = len(targets) > 1
        bs["single_voice_gain_db"] = round(part["balance_lu"] - loudest, 1)
        for art, b in (("sus", bs["bank"]), ("stac", bs["staccato_bank"])):
            if art not in arts:
                continue
            zones = []
            for li, (tid, variant) in enumerate(targets):
                gens = []
                if len(targets) > 1:
                    gens.append((G_FINE_TUNE, LAYER_DETUNE_CENTS if li % 2 == 0 else -LAYER_DETUNE_CENTS))
                zones.append(sf2.RawZone(gens, [], bank.target(tid, art, variant)))
            short = name.replace("♭", "b").replace("Cornet", "Cnt").replace("Trombone", "Tbn").replace("Baritone", "Bar")
            bank.presets.append(sf2.RawPreset(f"{short} {art}"[:19], bs["program"], b, zones))
        table.append((name, bs["program"], bs["bank"], bs["staccato_bank"],
                      "+".join(f"{t}" + (f"/{v}" if v else "") for t, v in targets), channel_gain))
    for part in mapping["parts"].values():  # one-player parts that play a section principal's preset
        if "preset_of" in part:
            src = mapping["parts"][part["preset_of"]]
            layered = len(layers(src["players"])) > 1
            part["band_soundfont"] = {**src["band_soundfont"],
                                      "channel_gain_db": round(part["balance_lu"] - loudest - (3.0 if layered else 0.0), 1),
                                      "single_voice_gain_db": round(part["balance_lu"] - loudest, 1)}
    drum = mapping["parts"]["Percussion"]["band_soundfont"]
    perc = mapping["parts"]["Percussion"]
    drum["channel_gain_db"] = round(perc["balance_lu"] + perc.get("kit_offset_db", 0.0) - loudest, 1)
    drum["single_voice_gain_db"] = drum["channel_gain_db"]
    drum["layered"] = False
    bank.band_kit(drum["program"])
    bank.drum_kit(MSBASIC, 0, as_program=mapping["band_soundfont"]["pop_kit_program"], name="Pop kit")
    return bank, table


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--bits", type=int, choices=[16, 24], default=24)
    ap.add_argument("-o", "--out", default=str(BUILT.parent / "band" / "brasscribe-band.sf2"))
    args = ap.parse_args()
    mapping = json.loads((HERE / "mapping.json").read_text())
    bank, table = build_bank(mapping)
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    sf2.write_raw(args.out, "brasscribe band", bank.samples, bank.instruments, bank.presets, bits=args.bits,
                  comment="brasscribe brass band: VSCO 2 CE (CC0) and Univ. of Iowa MIS samples adapted per part; "
                          "band kit from VSCO 2 CE concert percussion (CC0) and MuseScore MS Basic (MIT); "
                          "pop kit from MS Basic. See sounds/LICENSES.md.")
    (HERE / "mapping.json").write_text(json.dumps(mapping, indent=2, ensure_ascii=False) + "\n")
    size = Path(args.out).stat().st_size
    print(f"{args.out}: {size / 1e6:.1f} MB, {args.bits}-bit, {len(bank.samples)} samples, "
          f"{len(bank.instruments)} instruments, {len(bank.presets)} presets")
    for row in sorted(table, key=lambda r: (r[1], r[2])):
        print(f"  program {row[1]:3d} bank {row[2]:3d} (stac {row[3]:3d})  {row[0]:15s} {row[4]:28s} channel {row[5]:+.1f} dB")
    drum = mapping["parts"]["Percussion"]["band_soundfont"]
    print(f"  program {drum['program']:3d} bank 128              Percussion      band kit (VSCO concert percussion + MS Basic)")
    print(f"  program {mapping['band_soundfont']['pop_kit_program']:3d} bank 128              pop kit         MS Basic Standard")


if __name__ == "__main__":
    main()
