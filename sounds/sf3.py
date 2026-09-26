"""Read presets out of an SF2 or SF3 (Ogg Vorbis compressed) SoundFont.

Used to take the General MIDI drum kit from MuseScore's MS Basic (MIT) into the band
SoundFont. SF3 is the MuseScore extension of SF2: each sample in `smpl` is an Ogg Vorbis
stream, `shdr` start/end are byte offsets of that stream, and the loop points are frame
offsets relative to the decoded sample's start. Decoding uses libsndfile (soundfile), with
each sample peak-normalised the way FluidSynth and MuseScore play SF3.
"""

from __future__ import annotations

import io
import struct
from dataclasses import dataclass, field

import numpy as np
import soundfile as sf

G_INSTRUMENT = 41
G_SAMPLE_ID = 53


@dataclass
class RawSample:
    name: str
    data: np.ndarray  # float mono
    rate: int
    root: int
    cents: int
    loop: tuple[int, int] | None
    kind: int  # SF2 sampleType: 1 mono, 2 right, 4 left
    link: int  # index of the linked sample (stereo pairs), in this reader's sample list


@dataclass
class RawZone:
    gens: list[tuple[int, int]]  # (generator, raw 16-bit amount), sampleID/instrument excluded
    mods: list[bytes] = field(default_factory=list)  # 10-byte SF2 modulator records
    ref: int | None = None  # sample index (instrument zone) or instrument index (preset zone)


@dataclass
class RawInstrument:
    name: str
    zones: list[RawZone]  # zones[0] may be a global zone (ref None)


@dataclass
class RawPreset:
    name: str
    program: int
    bank: int
    zones: list[RawZone]


def _chunks(b: bytes, off: int, end: int):
    while off + 8 <= end:
        tag, size = b[off : off + 4], struct.unpack_from("<I", b, off + 4)[0]
        yield tag, off + 8, size
        off += 8 + size + (size & 1)


class SoundFontReader:
    def __init__(self, path: str):
        b = open(path, "rb").read()
        if b[:4] != b"RIFF" or b[8:12] != b"sfbk":
            raise ValueError(f"{path}: not a SoundFont")
        self.b = b
        self.chunks: dict[bytes, tuple[int, int]] = {}
        for tag, o, s in _chunks(b, 12, len(b)):
            if tag == b"LIST":
                for t2, o2, s2 in _chunks(b, o + 4, o + s):
                    self.chunks[t2] = (o2, s2)
        ver = self._records(b"ifil", 4)[0] if b"ifil" in self.chunks else (2, 1)
        self.compressed = ver[0] >= 3
        self._decoded: dict[int, np.ndarray] = {}

    def _raw(self, tag: bytes) -> bytes:
        o, s = self.chunks[tag]
        return self.b[o : o + s]

    def _records(self, tag: bytes, size: int) -> list[tuple]:
        fmt = {4: "<HH", 10: "<HHhHH", 38: "<20sHHHIII", 22: "<20sH", 46: "<20sIIIIIBbHH"}[size]
        raw = self._raw(tag)
        return [struct.unpack_from(fmt, raw, i * size) for i in range(len(raw) // size)]

    def presets(self) -> list[RawPreset]:
        phdr, pbag = self._records(b"phdr", 38), self._records(b"pbag", 4)
        pgen, pmod = self._raw(b"pgen"), self._raw(b"pmod")
        out = []
        for i in range(len(phdr) - 1):
            name, prog, bank, bag0 = phdr[i][:4]
            bag1 = phdr[i + 1][3]
            out.append(RawPreset(name.split(b"\0")[0].decode("latin-1"), prog, bank,
                                 [self._zone(pbag, pgen, pmod, z, G_INSTRUMENT) for z in range(bag0, bag1)]))
        return out

    def instrument(self, index: int) -> RawInstrument:
        inst, ibag = self._records(b"inst", 22), self._records(b"ibag", 4)
        name, bag0 = inst[index]
        bag1 = inst[index + 1][1]
        return RawInstrument(name.split(b"\0")[0].decode("latin-1"),
                             [self._zone(ibag, self._raw(b"igen"), self._raw(b"imod"), z, G_SAMPLE_ID)
                              for z in range(bag0, bag1)])

    def _zone(self, bags, gen_raw, mod_raw, z: int, ref_gen: int) -> RawZone:
        g0, m0 = bags[z]
        g1, m1 = bags[z + 1]
        gens, ref = [], None
        for k in range(g0, g1):
            oper, amount = struct.unpack_from("<HH", gen_raw, k * 4)
            if oper == ref_gen:
                ref = amount
            else:
                gens.append((oper, amount))
        mods = [mod_raw[k * 10 : k * 10 + 10] for k in range(m0, m1)]
        return RawZone(gens, mods, ref)

    def sample(self, index: int) -> RawSample:
        shdr = self._records(b"shdr", 46)
        name, start, end, ls, le, rate, root, cents, link, kind = shdr[index]
        smpl_off = self.chunks[b"smpl"][0]
        if self.compressed:
            if index not in self._decoded:
                x, _ = sf.read(io.BytesIO(self.b[smpl_off + start : smpl_off + end]), dtype="float64", always_2d=True)
                # FluidSynth and MuseScore decode SF3 samples with libsndfile's
                # SFC_SET_SCALE_FLOAT_INT_READ, which scales each sample's peak to full scale;
                # do the same so the copied samples play at the level they have there.
                peak = float(np.abs(x[:, 0]).max())
                self._decoded[index] = x[:, 0] * (32767 / 32768 / peak) if peak > 0 else x[:, 0]
            data = self._decoded[index]
            loop = (ls, le) if le > ls else None  # SF3 loops are relative to the sample start
        else:
            data = np.frombuffer(self.b, "<i2", end - start, smpl_off + 2 * start).astype(np.float64) / 32768
            loop = (ls - start, le - start) if le > ls else None
        return RawSample(name.split(b"\0")[0].decode("latin-1"), data, rate, root, cents, loop, kind & 0x7FFF, link)
