# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Build Fretscribe's Android launcher icon from the mark.

    uv run design/fretscribe/brand/build.py

Reads logo-mark.svg (the strings and the tile colour) and app-icon-fullbleed.svg, and writes
design/fretscribe/dist/icons/android/res, laid out like Brasscribe's design/dist/icons/android/res
(design/brand/build.py):

  mipmap-anydpi-v26/ic_launcher.xml      the adaptive icon
  drawable/ic_launcher_foreground.xml    the strings in paper, the art at 64% of the 108 dp canvas
  drawable/ic_launcher_monochrome.xml    the same strings in one colour, for themed icons
  values/ic_launcher_background.xml      the tile's ink
  mipmap-*/ic_launcher.png               legacy square icons, from the full-bleed master

The PNGs need `rsvg-convert` (librsvg) on PATH. They are rendered, not diffed.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
from pathlib import Path

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "dist" / "icons" / "android" / "res"

CANVAS = 108.0   # dp, the adaptive icon layer
SAFE = 66.0      # dp, the diameter every launcher mask keeps
GRID = 48.0      # the mark's grid (brand.md, Mark)
ART = 0.64       # the grid's share of the canvas; the full-bleed master's 78% breaks the safe zone


def mark() -> tuple[str, str, str]:
    """The strings' path, their colour and the tile's colour, from logo-mark.svg."""
    svg = (HERE / "logo-mark.svg").read_text()
    tile = re.search(r'<rect[^>]*fill="(#[0-9A-Fa-f]{6})"', svg).group(1)
    strings = re.search(r'<path fill="(#[0-9A-Fa-f]{6})" d="([^"]+)"', svg)
    return strings.group(2), strings.group(1), tile


def bounds(d: str) -> tuple[float, float, float, float]:
    """The bounding box of a path of absolute M, L, H and V commands, which is all the mark uses."""
    xs, ys = [], []
    for cmd, args in re.findall(r"([A-Za-z])([^A-Za-z]*)", d):
        n = [float(v) for v in re.findall(r"-?\d*\.?\d+", args)]
        if cmd in "ML":
            xs += n[0::2]
            ys += n[1::2]
        elif cmd == "H":
            xs += n
        elif cmd == "V":
            ys += n
        elif cmd not in "Zz":
            raise SystemExit(f"logo-mark.svg: path command {cmd} is not handled")
    return min(xs), min(ys), max(xs), max(ys)


def placement(d: str) -> tuple[float, float]:
    """Scale and offset that put the grid at ART of the canvas, centred; checks the 66 dp safe zone."""
    scale = CANVAS * ART / GRID
    offset = (CANVAS - GRID * scale) / 2
    x0, y0, x1, y1 = bounds(d)
    reach = max(math.hypot(x * scale + offset - CANVAS / 2, y * scale + offset - CANVAS / 2) for x in (x0, x1) for y in (y0, y1))
    if reach > SAFE / 2:
        raise SystemExit(f"the art reaches {reach:.1f} dp from the centre; the safe zone ends at {SAFE / 2:g} dp")
    return scale, offset


def vector(d: str, colour: str, scale: float, offset: float) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="{CANVAS:g}dp" android:height="{CANVAS:g}dp" android:viewportWidth="{CANVAS:g}" android:viewportHeight="{CANVAS:g}">\n'
            f'    <group android:translateX="{offset:g}" android:translateY="{offset:g}" android:scaleX="{scale:g}" android:scaleY="{scale:g}">\n'
            f'        <path android:fillColor="#FF{colour[1:].upper()}" android:pathData="{d}"/>\n'
            '    </group>\n</vector>\n')


def build() -> None:
    d, paper, ink = mark()
    scale, offset = placement(d)
    if RES.exists():
        shutil.rmtree(RES)
    files = {
        "mipmap-anydpi-v26/ic_launcher.xml": (
            '<?xml version="1.0" encoding="utf-8"?>\n'
            '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
            '    <background android:drawable="@color/ic_launcher_background"/>\n'
            '    <foreground android:drawable="@drawable/ic_launcher_foreground"/>\n'
            '    <monochrome android:drawable="@drawable/ic_launcher_monochrome"/>\n'
            '</adaptive-icon>\n'),
        "values/ic_launcher_background.xml": (
            f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">{ink}</color>\n</resources>\n'),
        "drawable/ic_launcher_foreground.xml": vector(d, paper, scale, offset),
        "drawable/ic_launcher_monochrome.xml": vector(d, "#FFFFFF", scale, offset),
    }
    for name, text in files.items():
        (RES / name).parent.mkdir(parents=True, exist_ok=True)
        (RES / name).write_text(text)
    for density, k in {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}.items():
        out = RES / f"mipmap-{density}" / "ic_launcher.png"
        out.parent.mkdir(parents=True, exist_ok=True)
        px = str(round(48 * k))
        subprocess.run(["rsvg-convert", "-w", px, "-h", px, str(HERE / "app-icon-fullbleed.svg"), "-o", str(out)], check=True)
    print(f"launcher icon written to {RES.relative_to(HERE.parents[2])}: art at {ART:.0%}, scale {scale:g}, offset {offset:g} dp")


if __name__ == "__main__":
    build()
