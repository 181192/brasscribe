"""Write the band SoundFont's program map into a MusicXML score.

    uv run --project sounds python sounds/band_programs.py IN.musicxml OUT.musicxml

For every <score-part> whose <part-name> is in sounds/mapping.json, sets <midi-program>
and <midi-bank> (both 1-based in MusicXML) in its <midi-instrument> to the part's preset
in brasscribe-band.sf2. The rest of the file is left byte-for-byte unchanged. This is the
reference for what the arranger's MusicXML writer should emit.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent


def apply(xml: str, mapping: dict) -> tuple[str, list[str]]:
    done = []

    def fix_part(m: re.Match) -> str:
        block = m.group(0)
        name = re.search(r"<part-name>([^<]*)</part-name>", block)
        part = mapping["parts"].get(name.group(1).strip()) if name else None
        if not part or "band_soundfont" not in part or "midi-bank" not in part["band_soundfont"]["musicxml"]:
            return block
        mx = part["band_soundfont"]["musicxml"]

        def fix_inst(mi: re.Match) -> str:
            body = mi.group(2)
            body = re.sub(r"\s*<midi-bank>\d+</midi-bank>", "", body)
            body = re.sub(r"\s*<midi-program>\d+</midi-program>", "", body)
            # MusicXML order: midi-channel, midi-name, midi-bank, midi-program, midi-unpitched, volume, pan
            indent = re.search(r"\n(\s*)<midi-channel>", body)
            ind = indent.group(1) if indent else "        "
            new = f"\n{ind}<midi-bank>{mx['midi-bank']}</midi-bank>\n{ind}<midi-program>{mx['midi-program']}</midi-program>"
            anchor = re.search(r"(<midi-channel>\d+</midi-channel>|<midi-name>[^<]*</midi-name>)(?![\s\S]*<midi-name>)", body)
            body = body[: anchor.end()] + new + body[anchor.end():] if anchor else new + body
            return mi.group(1) + body + mi.group(3)

        done.append(name.group(1).strip())
        return re.sub(r"(<midi-instrument[^>]*>)([\s\S]*?)(</midi-instrument>)", fix_inst, block, count=1)

    out = re.sub(r"<score-part\b[\s\S]*?</score-part>", fix_part, xml)
    return out, done


def main() -> None:
    src, dst = Path(sys.argv[1]), Path(sys.argv[2])
    mapping = json.loads((HERE / "mapping.json").read_text())
    out, done = apply(src.read_text(encoding="utf-8"), mapping)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(out, encoding="utf-8")
    print(f"{dst}: programs set for {len(done)} parts")


if __name__ == "__main__":
    main()
