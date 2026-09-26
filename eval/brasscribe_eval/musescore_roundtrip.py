"""Check a band score survives MuseScore: re-export via mscore, compare sounding pitches.

MuseScore is the real consumer of our MusicXML, so music21's own round trip is
not enough. This re-exports the file with the MuseScore CLI, re-imports it,
merges ties (MuseScore splits notes at barlines), converts to sounding pitch
and compares every part's pitch sequence to the arranger's concert pitches.
It also reports which instrument sound MuseScore assigned to each part.
"""

from __future__ import annotations

from brasscribe_music import musescore

import argparse
import re
import subprocess
from pathlib import Path

from brasscribe_music.arranger import arrange, arrange_layers
from brasscribe_music.score_model import Composition
from music21 import converter


def norm(name: str) -> str:
    return name.replace("♭", "b").replace("♯", "#").strip()


def _merge_ties(part) -> list[int]:
    """Pitch sequence with tie chains collapsed (music21's stripTies misses mid-bar 'continue' ties)."""
    out: list[int] = []
    for n in part.recurse().notes:
        if not n.isNote:
            continue
        if n.tie is not None and n.tie.type in ("continue", "stop") and out and out[-1] == n.pitch.midi:
            continue
        out.append(n.pitch.midi)
    return out


def check(xml: Path, comp_json: Path) -> bool:
    re_xml = xml.with_name(xml.stem + ".mscore.musicxml")
    if not musescore.convert(xml, re_xml):
        raise SystemExit("MuseScore did not re-export the file")
    raw = re_xml.read_text()
    sounds = dict(zip([norm(n) for n in re.findall(r"<part-name>([^<]*)</part-name>", raw)],
                      re.findall(r"<instrument-sound>([^<]+)</instrument-sound>", raw)))
    comp = Composition.from_json(comp_json)
    opts = comp.arrangement or {}
    if any(v.layer for v in comp.voices):
        from brasscribe_music.instruments import BRASS_BAND, MINIMAL_BAND
        lineup = MINIMAL_BAND if opts.get("lineup") == "minimal" else BRASS_BAND
        arr = arrange_layers(comp, lineup, difficulty=opts.get("difficulty", "faithful"))
    else:
        arr = arrange(comp)
    want = {norm(k): [n.pitch for n in sorted(v, key=lambda n: n.start)] for k, v in arr.parts.items()}
    back = converter.parse(re_xml).toSoundingPitch()
    ok = True
    for p in back.parts:
        name = norm(p.partName)
        if name == "Percussion":
            hits = sum(1 for n in p.recurse().notes)
            print(f"{name:14s} drum kit              events={hits:4d} (unpitched, not compared)")
            continue
        got = _merge_ties(p)
        same = got == want.get(name)
        ok &= same
        print(f"{name:14s} sound={sounds.get(name, '?'):22s} notes={len(got):4d} {'OK' if same else 'MISMATCH'}")
    return ok


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("musicxml", type=Path)
    ap.add_argument("composition", type=Path)
    args = ap.parse_args()
    print("ALL MATCH" if check(args.musicxml, args.composition) else "MISMATCH")


if __name__ == "__main__":
    main()
