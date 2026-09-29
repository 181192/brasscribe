"""Score part -> band SoundFont preset: the reference resolver every player implements.

    uv run --project sounds python sounds/partsound.py "Tenor Horn" "Tuba" ...   # resolve names
    uv run --project sounds python sounds/partsound.py --vectors                 # rewrite partsound-vectors.json
    python3 sounds/partsound.py --check                                          # CI: stdlib only

--check fails when a lineup part does not resolve by name (exact or alias) to its own preset,
when a brass part's players use anything but a real-sample target, when a target's range does
not cover the instrument's professional range, or when partsound-vectors.json is out of date.

The rules live in sounds/mapping.json `resolve` (normalize, then exact, alias, keyword,
instrument, GM program; a percussion part then takes the kit its <midi-program> selects,
`kit_programs`, else the band kit). sounds/partsound-vectors.json holds input -> expected preset
rows that the Apple, Android, Windows and Studio tests read, so the four resolvers cannot drift apart.
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

HERE = Path(__file__).resolve().parent
MAPPING = HERE / "mapping.json"
VECTORS = HERE / "partsound-vectors.json"


def normalize(name: str) -> str:
    s = name.lower().replace("♭", "b").replace("♯", "#")
    return re.sub(r"\s+", " ", s.replace(" ", " ")).strip()


@dataclass(frozen=True)
class Preset:
    part: str  # the mapping.json part whose preset plays
    step: str  # exact | alias | keyword | instrument | program
    program: int
    bank: int
    channel_gain_db: float
    percussion: bool


def resolve(name: str, mapping: dict, instrument: str | None = None, program: int | None = None) -> Preset | None:
    parts = mapping["parts"]
    r = mapping["resolve"]
    n = normalize(name)
    hit, step = None, None
    by_norm = {normalize(k): k for k in parts}
    if n in by_norm:
        hit, step = by_norm[n], "exact"
    elif n in r["aliases"]:
        hit, step = r["aliases"][n], "alias"
    else:
        for kw, part in r["keywords"]:
            if kw in n:
                hit, step = part, "keyword"
                break
    if hit is None and instrument and instrument in r["instruments"]:
        hit, step = r["instruments"][instrument], "instrument"
    if hit is None and program is not None and str(program) in r["programs"]:
        hit, step = r["programs"][str(program)], "program"
    if hit is None:
        return None
    bs = parts[hit]["band_soundfont"]
    prog = bs["program"]
    if bs["bank"] == 128 and program is not None and program in r["kit_programs"]:
        prog = program  # step 6: the kit the part selects (the pop kit); any other program plays the band kit
    return Preset(hit, step, prog, bs["bank"], bs["channel_gain_db"], bs["bank"] == 128)


VECTOR_INPUTS = [
    # every lineup part, by its exact name
    *[(None,)],
    # names other writers use
    ("1st Cornet",), ("Sop.",), ("Cornet 1",), ("Cornet",), ("Solo Cornet ",), ("Trumpet in B♭",), ("Tenor Horn",),
    ("Horn in E♭",), ("E♭ Horn",), ("Alto Horn",), ("Flugel",), ("Flügelhorn",), ("Baritone",), ("Baritone Horn",),
    ("Euphonium 2",), ("Trombone",), ("Bass Trombone",), ("Tuba",), ("Bass",), ("B♭ Tuba",), ("Eb Bass",), ("BBb Bass",),
    ("Drum Set",),
    # percussion kits by <midi-program> (0-based): band kit, pop kit, anything else the band kit
    ("Percussion", None, 0), ("Percussion", None, 1), ("Drum Set", None, 1), ("Percussion", None, 25),
    ("Part 5", "drum.group.set", 1), ("Part 6", "drum.group.set", 48),
    # unknown names resolved by instrument or GM program
    ("Part 1", "brass.alto-horn", None), ("Part 2", "brass.euphonium", None), ("P3", None, 56), ("P4", None, 58),
    ("Piano", None, 0),
]


def vectors(mapping: dict) -> list[dict]:
    rows = []
    names = []
    for lineup, ps in mapping["lineups"].items():
        if lineup != "about":
            names += [p for p in ps if p not in names]
    inputs = [(p, None, None) for p in names] + [v if len(v) == 3 else (v[0], None, None) for v in VECTOR_INPUTS[1:]]
    seen = set()
    for name, inst, prog in inputs:
        if (name, inst, prog) in seen:
            continue
        seen.add((name, inst, prog))
        p = resolve(name, mapping, inst, prog)
        rows.append({"name": name, "instrument": inst, "program": prog,
                     "expect": None if p is None else {"part": p.part, "step": p.step, "program": p.program, "bank": p.bank,
                                                        "channel_gain_db": p.channel_gain_db, "percussion": p.percussion}})
    return rows


REAL_LIBRARIES = {"vsco2ce", "iowa-mis"}


def check(mapping: dict) -> list[str]:
    errors = []
    sys.path.insert(0, str(HERE.parent / "music" / "src"))
    from brasscribe_music.instruments import INSTRUMENTS
    for lineup, names in mapping["lineups"].items():
        if lineup == "about":
            continue
        for name in names:
            p = resolve(name, mapping)
            if p is None or p.step not in ("exact", "alias"):
                errors.append(f"{lineup}: {name!r} does not resolve by name ({p.step if p else 'unresolved'})")
                continue
            part = mapping["parts"][p.part]
            inst = INSTRUMENTS[part["instrument"]]
            if inst.id == "drum-kit":
                if not p.percussion:
                    errors.append(f"{lineup}: {name!r} percussion is not on bank 128")
                continue
            for pl in part["players"]:
                t = mapping["targets"].get(pl["target"])
                if t is None:
                    errors.append(f"{lineup}: {name!r} player target {pl['target']!r} is not a built target")
                    continue
                if t["source"]["library"] not in REAL_LIBRARIES:
                    errors.append(f"{lineup}: {name!r} target {pl['target']!r} is not a real-sample library")
                if t["range"][0] > inst.pro[0] or t["range"][1] < inst.pro[1]:
                    errors.append(f"{lineup}: {name!r} target {pl['target']!r} range {t['range']} misses {inst.pro}")
            if "channel_gain_db" not in part["band_soundfont"]:
                errors.append(f"{lineup}: {name!r} has no channel gain (run sounds/band.py)")
    if VECTORS.exists():
        current = json.loads(VECTORS.read_text())["vectors"]
        if current != vectors(mapping):
            errors.append("sounds/partsound-vectors.json is out of date: run sounds/partsound.py --vectors")
    else:
        errors.append("sounds/partsound-vectors.json is missing")
    return errors


def main() -> None:
    mapping = json.loads(MAPPING.read_text())
    if sys.argv[1:] == ["--check"]:
        errors = check(mapping)
        for e in errors:
            print("FAIL", e)
        n = sum(len(v) for k, v in mapping["lineups"].items() if k != "about")
        print(f"{n} lineup parts checked, {len(errors)} problems")
        sys.exit(1 if errors else 0)
    if sys.argv[1:] == ["--vectors"]:
        rows = vectors(mapping)
        VECTORS.write_text(json.dumps({"about": "Generated by sounds/partsound.py --vectors from sounds/mapping.json. "
                                                "Input (name, MusicXML instrument-sound or instrument id, 0-based GM program) "
                                                "-> the band SoundFont preset every player must pick. expect null: unresolved "
                                                "(not a brass-band instrument).", "vectors": rows},
                                      indent=1, ensure_ascii=False) + "\n")
        print(f"{VECTORS}: {len(rows)} vectors")
        return
    for name in sys.argv[1:]:
        print(name, "->", resolve(name, mapping))


if __name__ == "__main__":
    main()
