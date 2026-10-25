# /// script
# requires-python = ">=3.11"
# dependencies = ["pillow>=11"]
# ///
"""Build Fretscribe's Android launcher icon and Windows app icons from the mark.

    uv run design/brands/fretscribe/brand/build.py

Reads logo-mark.svg (the strings and the tile colour) and writes
design/brands/fretscribe/dist/icons/android/res, laid out like Brasscribe's design/brands/brasscribe/dist/icons/android/res
(design/brands/brasscribe/brand/build.py):

  mipmap-anydpi/ic_launcher.xml          the adaptive icon
  drawable/ic_launcher_foreground.xml    the strings in paper, the art at 64% of the 108 dp canvas
  drawable/ic_launcher_monochrome.xml    the same strings in one colour, for themed icons
  values/ic_launcher_background.xml      the tile's ink

and design/brands/fretscribe/dist/icons/windows/Assets, with the names Brasscribe's has: the tiles from
app-icon-fullbleed.svg, the small sizes and AppIcon.ico from the rounded tile (favicon-16.svg at 16 and 20 px),
and the taskbar's unplated sizes as the strings alone in blue ink (the dark taskbar's blue on a dark one).
Needs rsvg-convert on the PATH.
"""

from __future__ import annotations

import math
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
RES = HERE.parent / "dist" / "icons" / "android" / "res"
WINDOWS = HERE.parent / "dist" / "icons" / "windows" / "Assets"

# Blue ink, light and dark (brand.md, Colour): the unplated taskbar icon on a light and on a dark taskbar.
BLUE_INK = ("#1F5FAD", "#8AB8F2")

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
        "mipmap-anydpi/ic_launcher.xml": (
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
    print(f"launcher icon written to {RES.relative_to(HERE.parents[3])}: art at {ART:.0%}, scale {scale:g}, offset {offset:g} dp")


def render(svg: str, out: Path, w: int, h: int | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", suffix=".svg", delete=False) as f:
        f.write(svg)
    try:
        subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h or w), f.name, "-o", str(out)], check=True)
    finally:
        Path(f.name).unlink()


def build_windows() -> None:
    d, paper, ink = mark()
    full = (HERE / "app-icon-fullbleed.svg").read_text()
    rounded = (HERE / "logo-mark.svg").read_text()
    hinted = (HERE / "favicon-16.svg").read_text()
    small = lambda size: hinted if size <= 20 else rounded  # noqa: E731
    # The strings alone, 92% of the square, as Brasscribe's unplated icon has its mark.
    unplated = lambda colour: (  # noqa: E731
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 48 48">'
        f'<g transform="translate(24 24) scale(1.38) translate(-24 -24)"><path fill="{colour}" d="{d}"/></g></svg>')
    # The wide tile: the ink ground, the tile's strings at the square tile's height.
    wide = ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 310 150">'
            f'<rect width="310" height="150" fill="{ink}"/>'
            f'<g transform="translate(155 75) scale(2.44) translate(-24 -24)"><path fill="{paper}" d="{d}"/></g></svg>')
    if WINDOWS.exists():
        shutil.rmtree(WINDOWS)
    for sc in (100, 125, 150, 200, 400):
        f = sc / 100
        render(full if 44 * f > 48 else small(round(44 * f)), WINDOWS / f"Square44x44Logo.scale-{sc}.png", round(44 * f))
        render(full, WINDOWS / f"Square150x150Logo.scale-{sc}.png", round(150 * f))
        render(full, WINDOWS / f"StoreLogo.scale-{sc}.png", round(50 * f))
        render(full, WINDOWS / f"SmallTile.scale-{sc}.png", round(71 * f))
        render(full, WINDOWS / f"LargeTile.scale-{sc}.png", round(310 * f))
        render(wide, WINDOWS / f"Wide310x150Logo.scale-{sc}.png", round(310 * f), round(150 * f))
    for t in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        render(small(t), WINDOWS / f"Square44x44Logo.targetsize-{t}.png", t)
        render(unplated(BLUE_INK[1]), WINDOWS / f"Square44x44Logo.targetsize-{t}_altform-unplated.png", t)
        render(unplated(BLUE_INK[0]), WINDOWS / f"Square44x44Logo.targetsize-{t}_altform-lightunplated.png", t)
    sizes = (16, 24, 32, 48, 64, 256)
    with tempfile.TemporaryDirectory() as tmp:
        for t in sizes:
            render(small(t), Path(tmp) / f"{t}.png", t)
        frames = [Image.open(Path(tmp) / f"{t}.png").convert("RGBA") for t in sizes]
        frames[-1].save(WINDOWS / "AppIcon.ico", sizes=[(t, t) for t in sizes], append_images=frames[:-1])
    print(f"Windows icons written to {WINDOWS.relative_to(HERE.parents[3])}")


if __name__ == "__main__":
    build()
    build_windows()
