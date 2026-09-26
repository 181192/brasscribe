"""Cut bars from a MusicXML score (optionally only some parts) and render them with MuseScore.

    uv run python -W ignore -m brasscribe_eval.score_excerpt brass-band.musicxml --bars 1 16 \
        --parts "Solo Cornet" "Euphonium" "E♭ Bass" --out intro-solo.png

MuseScore writes one PNG per page (intro-solo-1.png, ...). It aborts during
shutdown after writing, so the files are checked, not the exit code.
"""

from __future__ import annotations

from brasscribe_music import musescore

import argparse
import subprocess
from pathlib import Path

from music21 import converter, stream


def excerpt(xml: Path, first: int, last: int, parts: list[str] | None) -> stream.Score:
    score = converter.parse(xml)
    cut = score.measures(first, last)
    if parts:
        for p in list(cut.parts):
            if p.partName not in parts:
                cut.remove(p)
    return cut


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("musicxml", type=Path)
    ap.add_argument("--bars", type=int, nargs=2, required=True, metavar=("FIRST", "LAST"))
    ap.add_argument("--parts", nargs="*")
    ap.add_argument("--out", type=Path, required=True, help=".png (or .pdf)")
    args = ap.parse_args()
    cut = excerpt(args.musicxml, *args.bars, args.parts)
    tmp = args.out.with_suffix(".musicxml")
    cut.write("musicxml", fp=str(tmp))
    for old in args.out.parent.glob(f"{args.out.stem}*{args.out.suffix}"):
        old.unlink()
    musescore.convert(tmp, args.out)
    made = sorted(args.out.parent.glob(f"{args.out.stem}*{args.out.suffix}"))
    if not made:
        raise SystemExit("MuseScore wrote nothing")
    print("\n".join(map(str, made)))


if __name__ == "__main__":
    main()
