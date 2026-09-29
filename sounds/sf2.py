"""Minimal SoundFont 2.04 writer (mono 24-bit samples, one instrument per preset).

Written for AVAudioUnitSampler, TinySoundFont/alphaSynth and FluidSynth. Each region
becomes one instrument zone. Velocity behaviour is made explicit instead of relying on
the SF2 default modulators: the default velocity->attenuation (concave, 96 dB) and
velocity->filter-cutoff modulators are overridden with amount 0, and one linear
velocity->attenuation modulator gives the same dB-linear curve the SFZ files declare.
"""

from __future__ import annotations

import math
import struct
from dataclasses import dataclass, field

import numpy as np

# generator ids (SF2.04 section 8.1.2)
G_ATTACK_VOL_ENV = 34
G_RELEASE_VOL_ENV = 38
G_INSTRUMENT = 41
G_KEY_RANGE = 43
G_VEL_RANGE = 44
G_INITIAL_ATTENUATION = 48
G_FINE_TUNE = 52
G_SAMPLE_ID = 53
G_SAMPLE_MODES = 54
G_OVERRIDING_ROOT_KEY = 58

# modulator source operators: type<<10 | polarity<<9 | direction<<8 | cc<<7 | index
SRC_VEL_CONCAVE_NEG = 0x0502
SRC_VEL_LINEAR_NEG = 0x0102
DEST_FILTER_FC = 8


@dataclass
class Sample:
    name: str
    data: np.ndarray  # float mono, -1..1
    rate: int
    root: int
    cents: int  # pitch correction applied by the player (+ raises pitch)
    loop: tuple[int, int] | None  # [start, end) in sample frames
    kind: int = 1  # SF2 sampleType: 1 mono, 2 right, 4 left (stereo halves point at each other via link)
    link: int = 0  # index of the other stereo half


@dataclass
class Zone:
    sample: int
    lokey: int
    hikey: int
    lovel: int
    hivel: int
    attenuation_cb: int = 0
    loop: bool = False


@dataclass
class Instrument:
    name: str
    zones: list[Zone] = field(default_factory=list)
    attack_s: float = 0.002
    release_s: float = 0.2
    vel_span_db: float = 6.0  # attenuation at velocity 0 relative to 127


def _name(s: str) -> bytes:
    return s.encode("ascii", "replace")[:19].ljust(20, b"\0")


def _zstr(s: str) -> bytes:
    """Zero-terminated INFO string padded to an even size (SF2 2.04 section 5)."""
    b = s.encode("ascii", "replace") + b"\0"
    return b + b"\0" if len(b) % 2 else b


def _chunk(tag: bytes, data: bytes) -> bytes:
    pad = b"\0" if len(data) % 2 else b""
    return tag + struct.pack("<I", len(data)) + data + pad


def _list(tag: bytes, chunks: list[bytes]) -> bytes:
    body = tag + b"".join(chunks)
    return b"LIST" + struct.pack("<I", len(body)) + body


def timecents(seconds: float) -> int:
    return int(round(1200 * math.log2(max(seconds, 0.001))))


@dataclass
class RawZone:
    """One zone as raw generators: (generator id, 16-bit amount as int, signed or packed lo/hi)."""
    gens: list[tuple[int, int]]
    mods: list[bytes] = field(default_factory=list)  # 10-byte modulator records
    ref: int | None = None  # sample index (instrument zone), instrument index (preset zone), None = global


@dataclass
class RawInstrument:
    name: str
    zones: list[RawZone]


@dataclass
class RawPreset:
    name: str
    program: int
    bank: int
    zones: list[RawZone]


def _gen(oper: int, amount: int) -> bytes:
    return struct.pack("<HH", oper, amount & 0xFFFF)


def _range(lo: int, hi: int) -> int:
    return (hi << 8) | lo


def _zone_records(z: RawZone, ref_gen: int) -> tuple[list[bytes], list[bytes]]:
    """Generators in SF2 order: keyRange, velRange, the rest, then the sample/instrument reference."""
    first = [g for g in z.gens if g[0] == G_KEY_RANGE] + [g for g in z.gens if g[0] == G_VEL_RANGE]
    rest = [g for g in z.gens if g[0] not in (G_KEY_RANGE, G_VEL_RANGE, ref_gen)]
    gens = [_gen(*g) for g in first + rest]
    if z.ref is not None:
        gens.append(_gen(ref_gen, z.ref))
    return gens, list(z.mods)


def target_instrument(inst: Instrument) -> RawInstrument:
    """The per-target instrument (explicit velocity modulators, envelope) as raw zones."""
    glob = RawZone(
        [(G_ATTACK_VOL_ENV, timecents(inst.attack_s)), (G_RELEASE_VOL_ENV, timecents(inst.release_s))],
        [struct.pack("<HHhHH", SRC_VEL_CONCAVE_NEG, G_INITIAL_ATTENUATION, 0, 0, 0),
         struct.pack("<HHhHH", SRC_VEL_LINEAR_NEG, DEST_FILTER_FC, 0, 0, 0),
         struct.pack("<HHhHH", SRC_VEL_LINEAR_NEG, G_INITIAL_ATTENUATION, int(round(inst.vel_span_db * 10)), 0, 0)])
    zones = [glob]
    for z in inst.zones:
        gens = [(G_KEY_RANGE, _range(z.lokey, z.hikey)), (G_VEL_RANGE, _range(z.lovel, z.hivel))]
        if z.attenuation_cb:
            gens.append((G_INITIAL_ATTENUATION, z.attenuation_cb))
        if z.loop:  # 0 (no loop) is the default
            gens.append((G_SAMPLE_MODES, 1))
        zones.append(RawZone(gens, [], z.sample))
    return RawInstrument(inst.name, zones)


def write_sf2(path: str, bank_name: str, samples: list[Sample], presets: list[tuple[str, int, Instrument]]) -> None:
    """One instrument per preset, bank 0: presets are (name, program number, instrument)."""
    insts = [target_instrument(inst) for _, _, inst in presets]
    raw = [RawPreset(name, program, 0, [RawZone([], [], i)]) for i, (name, program, _) in enumerate(presets)]
    write_raw(path, bank_name, samples, insts, raw)


def write_raw(path: str, bank_name: str, samples: list[Sample], instruments: list[RawInstrument],
              presets: list[RawPreset], bits: int = 24, comment: str = "") -> None:
    """General writer. bits=16 drops the sm24 chunk."""
    # ---- sample data: 16-bit high words in smpl, low bytes in sm24, 46 zero frames after each sample
    hi_parts, lo_parts, headers, pos = [], [], [], 0
    for s in samples:
        q = np.clip(np.round(s.data * 8388607.0), -8388608, 8388607).astype(np.int32)
        pad = np.zeros(46, dtype=np.int32)
        q = np.concatenate([q, pad])
        hi_parts.append((q >> 8).astype("<i2").tobytes())
        lo_parts.append((q & 0xFF).astype(np.uint8).tobytes())
        n = len(s.data)
        ls, le = s.loop if s.loop else (0, 0)
        headers.append(struct.pack("<20sIIIIIBbHH", _name(s.name), pos, pos + n, pos + ls, pos + le,
                                   s.rate, s.root, int(np.clip(s.cents, -99, 99)), s.link, s.kind))
        pos += n + 46
    if pos % 2:  # keep sm24 an even size: some readers (alphaTab/TinySoundFont) ignore RIFF pad bytes
        hi_parts.append(b"\0\0")
        lo_parts.append(b"\0")
        pos += 1
    headers.append(struct.pack("<20sIIIIIBbHH", _name("EOS"), 0, 0, 0, 0, 0, 0, 0, 0, 0))
    sm24 = b"".join(lo_parts)

    # ---- instruments
    inst_recs, ibag, imod, igen = [], [], [], []
    for inst in instruments:
        inst_recs.append(struct.pack("<20sH", _name(inst.name), len(ibag)))
        for z in inst.zones:
            ibag.append(struct.pack("<HH", len(igen), len(imod)))
            g, m = _zone_records(z, G_SAMPLE_ID)
            igen += g
            imod += m
    inst_recs.append(struct.pack("<20sH", _name("EOI"), len(ibag)))
    ibag.append(struct.pack("<HH", len(igen), len(imod)))
    imod.append(struct.pack("<HHhHH", 0, 0, 0, 0, 0))
    igen.append(struct.pack("<Hh", 0, 0))

    # ---- presets
    phdr, pbag, pmod, pgen = [], [], [], []
    for p in sorted(presets, key=lambda p: (p.bank, p.program)):
        phdr.append(struct.pack("<20sHHHIII", _name(p.name), p.program, p.bank, len(pbag), 0, 0, 0))
        for z in p.zones:
            pbag.append(struct.pack("<HH", len(pgen), len(pmod)))
            g, m = _zone_records(z, G_INSTRUMENT)
            pgen += g
            pmod += m
    phdr.append(struct.pack("<20sHHHIII", _name("EOP"), 0, 0, len(pbag), 0, 0, 0))
    pbag.append(struct.pack("<HH", len(pgen), len(pmod)))
    pmod.append(struct.pack("<HHhHH", 0, 0, 0, 0, 0))
    pgen.append(struct.pack("<Hh", 0, 0))

    info = _list(b"INFO", [
        _chunk(b"ifil", struct.pack("<HH", 2, 4)),
        _chunk(b"isng", _zstr("EMU8000")),
        _chunk(b"INAM", _zstr(bank_name)),
        _chunk(b"ICMT", _zstr(comment or "Built by brasscribe sounds/build.py from CC0 / unrestricted samples; "
                                         "see sounds/manifest.json")),
    ])
    sdta = _list(b"sdta", [_chunk(b"smpl", b"".join(hi_parts))] + ([_chunk(b"sm24", sm24)] if bits == 24 else []))
    pdta = _list(b"pdta", [
        _chunk(b"phdr", b"".join(phdr)), _chunk(b"pbag", b"".join(pbag)), _chunk(b"pmod", b"".join(pmod)),
        _chunk(b"pgen", b"".join(pgen)), _chunk(b"inst", b"".join(inst_recs)), _chunk(b"ibag", b"".join(ibag)),
        _chunk(b"imod", b"".join(imod)), _chunk(b"igen", b"".join(igen)), _chunk(b"shdr", b"".join(headers)),
    ])
    body = b"sfbk" + info + sdta + pdta
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", len(body)) + body)
