"""Structural check of an SF2 file against the SoundFont 2.04 specification.

    uv run --project sounds python sounds/sf2check.py FILE.sf2 [...]

Checks what strict readers (AVAudioUnitSampler/DLS-SF2 loader, TinySoundFont, FluidSynth)
rely on: RIFF sizes; mandatory chunks; every chunk even-sized; record sizes; terminal
records; monotonic bag/generator/modulator indices; generator order (keyRange first,
velRange second, sampleID/instrument last, only the first zone may be global); sample
bounds, loops inside the sample with 8 frames of margin and 46 frames of padding after each
sample; stereo links pointing at a matching partner; sm24 length; unique (bank, program).
Prints the problems and a preset list; exit status 1 when anything fails.
"""

from __future__ import annotations

import struct
import sys

G_KEY_RANGE, G_VEL_RANGE, G_INSTRUMENT, G_SAMPLE_ID, G_SAMPLE_MODES = 43, 44, 41, 53, 54
RECORD = {b"phdr": 38, b"pbag": 4, b"pmod": 10, b"pgen": 4, b"inst": 22, b"ibag": 4, b"imod": 10, b"igen": 4, b"shdr": 46}


def chunks(b: bytes, off: int, end: int):
    while off + 8 <= end:
        tag, size = b[off : off + 4], struct.unpack_from("<I", b, off + 4)[0]
        yield tag, off + 8, size
        off += 8 + size + (size & 1)


def check(path: str) -> list[str]:
    b = open(path, "rb").read()
    err: list[str] = []
    if b[:4] != b"RIFF" or b[8:12] != b"sfbk":
        return ["not a RIFF sfbk file"]
    if struct.unpack_from("<I", b, 4)[0] + 8 != len(b):
        err.append("RIFF size does not match the file size")
    lists, c = {}, {}
    for tag, o, s in chunks(b, 12, len(b)):
        if tag == b"LIST":
            lists[b[o : o + 4]] = (o, s)
            for t2, o2, s2 in chunks(b, o + 4, o + s):
                c[t2] = (o2, s2)
                if s2 % 2:
                    err.append(f"chunk {t2.decode()} has odd size {s2}")
    for need in (b"INFO", b"sdta", b"pdta"):
        if need not in lists:
            err.append(f"missing LIST {need.decode()}")
    for need in [b"ifil", b"isng", b"INAM", b"smpl"] + list(RECORD):
        if need not in c:
            err.append(f"missing chunk {need.decode()}")
    if err:
        return err
    ver = struct.unpack_from("<HH", b, c[b"ifil"][0])
    if ver[0] != 2:
        err.append(f"ifil version {ver} (expected 2.x)")
    rec = {}
    for tag, size in RECORD.items():
        o, s = c[tag]
        if s % size:
            err.append(f"{tag.decode()} size {s} not a multiple of {size}")
        rec[tag] = [b[o + i * size : o + (i + 1) * size] for i in range(s // size)]
    frames = c[b"smpl"][1] // 2
    if b"sm24" in c and c[b"sm24"][1] not in (frames, frames + 1):
        err.append(f"sm24 has {c[b'sm24'][1]} bytes for {frames} frames")

    phdr = [struct.unpack("<20sHHHIII", r) for r in rec[b"phdr"]]
    inst = [struct.unpack("<20sH", r) for r in rec[b"inst"]]
    pbag = [struct.unpack("<HH", r) for r in rec[b"pbag"]]
    ibag = [struct.unpack("<HH", r) for r in rec[b"ibag"]]
    pgen = [struct.unpack("<HH", r) for r in rec[b"pgen"]]
    igen = [struct.unpack("<HH", r) for r in rec[b"igen"]]
    shdr = [struct.unpack("<20sIIIIIBbHH", r) for r in rec[b"shdr"]]
    for name, hdr in ((b"EOP", phdr[-1][0]), (b"EOI", inst[-1][0]), (b"EOS", shdr[-1][0])):
        if not hdr.startswith(name):
            err.append(f"terminal record {name.decode()} missing")

    def zones(headers, bags, gens, nmod, ref_gen, nref, what):
        for i in range(len(headers) - 1):
            b0, b1 = headers[i][-1] if what == "instrument" else headers[i][3], (
                headers[i + 1][-1] if what == "instrument" else headers[i + 1][3])
            if b1 < b0:
                err.append(f"{what} {i}: bag index decreases")
                continue
            if b1 == b0:
                err.append(f"{what} {i}: no zones")
            for z in range(b0, b1):
                g0, m0 = bags[z]
                g1, m1 = bags[z + 1]
                if g1 < g0 or m1 < m0 or g1 > len(gens) or m1 > nmod:
                    err.append(f"{what} {i} zone {z}: bad generator/modulator indices")
                    continue
                ops = [gens[k][0] for k in range(g0, g1)]
                if G_KEY_RANGE in ops and ops.index(G_KEY_RANGE) != 0:
                    err.append(f"{what} {i} zone {z}: keyRange not first")
                if G_VEL_RANGE in ops and ops.index(G_VEL_RANGE) != (1 if G_KEY_RANGE in ops else 0):
                    err.append(f"{what} {i} zone {z}: velRange out of order")
                if ref_gen in ops:
                    if ops[-1] != ref_gen:
                        err.append(f"{what} {i} zone {z}: {ref_gen} not the last generator")
                    ref = gens[g0 + ops.index(ref_gen)][1]
                    if ref >= nref:
                        err.append(f"{what} {i} zone {z}: reference {ref} out of range")
                elif z != b0:
                    err.append(f"{what} {i} zone {z}: global zone that is not the first zone")

    zones(phdr, pbag, pgen, len(rec[b"pmod"]), G_INSTRUMENT, len(inst) - 1, "preset")
    zones(inst, ibag, igen, len(rec[b"imod"]), G_SAMPLE_ID, len(shdr) - 1, "instrument")
    for i, (name, start, end, ls, le, rate, root, cents, link, kind) in enumerate(shdr[:-1]):
        n = name.split(b"\0")[0].decode("latin-1")
        if not start < end <= frames:
            err.append(f"sample {i} {n}: bounds {start}-{end} outside smpl ({frames} frames)")
        if le > ls and not (start + 8 <= ls < le <= end - 8):
            err.append(f"sample {i} {n}: loop {ls}-{le} not inside {start}-{end} with 8 frames margin")
        if i + 1 < len(shdr) - 1 and shdr[i + 1][1] < end + 46:
            err.append(f"sample {i} {n}: fewer than 46 padding frames after it")
        if not 400 <= rate <= 192000:
            err.append(f"sample {i} {n}: rate {rate}")
        if root > 127:
            err.append(f"sample {i} {n}: root {root}")
        if kind & 0x8000:
            err.append(f"sample {i} {n}: ROM sample")
        k = kind & 0x7FFF
        if k not in (1, 2, 4):
            err.append(f"sample {i} {n}: sampleType {kind}")
        elif k in (2, 4):
            other = shdr[link] if link < len(shdr) - 1 else None
            if other is None or (other[9] & 0x7FFF) != (6 - k) or other[8] != i:
                err.append(f"sample {i} {n}: stereo link {link} does not point back")
    seen = {}
    for name, prog, bank, *_ in phdr[:-1]:
        key = (bank, prog)
        if key in seen:
            err.append(f"duplicate preset bank {bank} program {prog}")
        seen[key] = name.split(b"\0")[0].decode("latin-1")
    print(f"{path}: SF2 {ver[0]}.{ver[1]:02d}, {len(b) / 1e6:.1f} MB, {len(phdr) - 1} presets, {len(inst) - 1} instruments, "
          f"{len(shdr) - 1} samples, {'24' if b'sm24' in c else '16'}-bit")
    for (bank, prog), name in sorted(seen.items()):
        print(f"   bank {bank:3d} program {prog:3d}  {name}")
    return err


def main() -> int:
    bad = 0
    for path in sys.argv[1:]:
        errs = check(path)
        for e in errs[:40]:
            print("  FAIL", e)
        print(f"  {'OK' if not errs else f'{len(errs)} problems'}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
