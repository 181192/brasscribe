# /// script
# requires-python = ">=3.11"
# dependencies = ["fonttools>=4.55", "pillow>=11"]
# ///
"""Build the Brasscribe brand assets from the mark and the display face.

    uv run design/brand/build.py

Writes:
  design/brand/logo/          mark, wordmark and lockups as SVG (text converted to outlines)
  design/brand/icon/          app icon masters (SVG)
  design/dist/icons/          per-platform PNG exports, Apple/Android/Windows manifests, favicon set
  design/brand/social/        the link-preview image (1280 x 640) for the repository and the site

Needs `rsvg-convert` (librsvg) on PATH. PNGs are rendered, not diffed: the sync test covers
only the text outputs of design/tokens/build.py.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from PIL import Image

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FONTS = HERE / "fonts"
LOGO = HERE / "logo"
ICON = HERE / "icon"
DIST = ROOT / "design" / "dist" / "icons"

# The mark: a flat sign (every brass-band instrument is in B-flat or E-flat) whose bowl flares
# open like a bell. 64 x 64 grid, optically centred. Fill rule: evenodd.
MARK = ("M9.5 10a4.5 4.5 0 0 1 9 0V31C29.5 31 41.5 26 50.5 15C52 13.5 54.5 14 54.5 16V26"
        "C54.5 45 39.5 58 18.5 59H9.5Z"
        "M18.5 41V51C31.5 49.5 40.5 42 44.5 31C37.5 37 28.5 40.5 18.5 41Z")

INK = "#1B1A17"
PAPER = "#FBFAF7"
BRASS = "#A57A2C"        # brand brass on light
BRASS_ON_DARK = "#D2A955"
BRASS_TEXT = "#7A5719"
TILE_TOP, TILE_BOTTOM = "#2B2824", "#141311"
BRASS_HI, BRASS_LO = "#E7C77E", "#B48633"


def svg_doc(w: float, h: float, body: str, view: str | None = None) -> str:
    vb = view or f"0 0 {w:g} {h:g}"
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:g}" height="{h:g}" viewBox="{vb}">\n'
            f"{body}\n</svg>\n")


def mark_group(x: float, y: float, size: float, fill: str) -> str:
    s = size / 64
    return f'<path transform="translate({x:g} {y:g}) scale({s:g})" fill="{fill}" fill-rule="evenodd" d="{MARK}"/>'


# ---------- wordmark: text to outlines ----------

def text_path(font: TTFont, text: str, size: float, x0: float, baseline: float, tracking_em: float = 0.0) -> tuple[str, float]:
    gs = font.getGlyphSet()
    cmap = font.getBestCmap()
    upm = font["head"].unitsPerEm
    scale = size / upm
    hmtx = font["hmtx"]
    kern = {}
    if "kern" in font:
        for t in font["kern"].kernTables:
            kern.update(t.kernTable)
    pen = SVGPathPen(gs)
    x = x0
    prev = None
    for ch in text:
        gname = cmap[ord(ch)]
        if prev is not None:
            x += kern.get((prev, gname), 0) * scale
        tp = TransformPen(pen, (scale, 0, 0, -scale, x, baseline))
        gs[gname].draw(tp)
        x += hmtx[gname][0] * scale + tracking_em * size
        prev = gname
    return pen.getCommands(), x - tracking_em * size


def build_logo() -> None:
    LOGO.mkdir(exist_ok=True)
    regular = TTFont(FONTS / "InstrumentSerif-Regular.ttf")
    italic = TTFont(FONTS / "InstrumentSerif-Italic.ttf")
    cap = regular["OS/2"].sCapHeight / regular["head"].unitsPerEm

    # Mark alone, three colourways.
    for name, fill in (("mark", INK), ("mark-brass", BRASS), ("mark-on-dark", BRASS_ON_DARK), ("mark-white", "#FFFFFF")):
        (LOGO / f"{name}.svg").write_text(svg_doc(64, 64, mark_group(0, 0, 64, fill)))

    size = 96
    d, end = text_path(regular, "Brasscribe", size, 0, size, 0.005)
    h = size * 1.25
    for name, fill in (("wordmark", INK), ("wordmark-on-dark", "#EDEBE6")):
        (LOGO / f"{name}.svg").write_text(svg_doc(round(end, 1), h, f'<path fill="{fill}" d="{d}"/>'))

    # Lockups: mark height = 1.5 x cap height, mark sits on the baseline; product name in italic brass.
    for product in ("Play", "Studio"):
        for suffix, ink, brass_fill, mark_fill in (("", INK, BRASS_TEXT, BRASS), ("-on-dark", "#EDEBE6", BRASS_ON_DARK, BRASS_ON_DARK)):
            mh = cap * size * 1.3
            baseline = size * 1.05
            gap = size * 0.2
            mx, my = 0, baseline - mh * 59 / 64
            d1, e1 = text_path(regular, "Brasscribe", size, mh + gap, baseline, 0.005)
            d2, e2 = text_path(italic, product, size, e1 + size * 0.22, baseline, 0.0)
            body = (mark_group(mx, my, mh, mark_fill) + "\n" + f'<path fill="{ink}" d="{d1}"/>\n'
                    f'<path fill="{brass_fill}" d="{d2}"/>')
            (LOGO / f"lockup-{product.lower()}{suffix}.svg").write_text(svg_doc(round(e2 + 2, 1), size * 1.3, body))


# ---------- app icon masters ----------

DEFS = f"""<defs>
  <linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{TILE_TOP}"/><stop offset="1" stop-color="{TILE_BOTTOM}"/>
  </linearGradient>
  <linearGradient id="brass" x1="1" y1="0" x2="0" y2="1">
    <stop offset="0" stop-color="{BRASS_HI}"/><stop offset="1" stop-color="{BRASS_LO}"/>
  </linearGradient>
</defs>"""


def icon_full_bleed() -> str:
    """1024 square, no mask: iOS/iPadOS (the system applies the mask), Android store icon, Windows tiles."""
    m = 600
    return svg_doc(1024, 1024, DEFS + '\n<rect width="1024" height="1024" fill="url(#tile)"/>\n'
                   + mark_group((1024 - m) / 2, (1024 - m) / 2, m, "url(#brass)"))


def icon_macos() -> str:
    """macOS: 824 rounded tile on a 1024 canvas with the system-style drop shadow baked in."""
    m = 480
    return svg_doc(1024, 1024, DEFS + """
<defs><filter id="shadow" x="-10%" y="-10%" width="120%" height="125%">
  <feDropShadow dx="0" dy="10" stdDeviation="14" flood-color="#000" flood-opacity="0.28"/></filter></defs>
<rect x="100" y="100" width="824" height="824" rx="185" fill="url(#tile)" filter="url(#shadow)"/>
<rect x="100.5" y="100.5" width="823" height="823" rx="184.5" fill="none" stroke="#FFFFFF" stroke-opacity="0.08"/>
""" + mark_group((1024 - m) / 2, (1024 - m) / 2, m, "url(#brass)"))


def icon_rounded(size: int, mark_ratio: float = 0.62, radius_ratio: float = 0.2237) -> str:
    """Small plated icon (favicon, Windows ICO): rounded tile, larger mark so it survives 16 px."""
    m = size * mark_ratio
    r = size * radius_ratio
    return svg_doc(size, size, DEFS + f'\n<rect width="{size}" height="{size}" rx="{r:g}" fill="url(#tile)"/>\n'
                   + mark_group((size - m) / 2, (size - m) / 2, m, "url(#brass)"))


def android_foreground() -> str:
    """Adaptive icon foreground: 108 dp canvas, mark inside the 66 dp safe zone."""
    m = 52
    return svg_doc(108, 108, DEFS + "\n" + mark_group((108 - m) / 2, (108 - m) / 2, m, "url(#brass)"))


def android_monochrome() -> str:
    m = 52
    return svg_doc(108, 108, mark_group((108 - m) / 2, (108 - m) / 2, m, "#FFFFFF"))


def unplated(size: int = 256) -> str:
    """Windows unplated taskbar icon: mark alone, brass that reads on light and dark taskbars."""
    m = size * 0.92
    return svg_doc(size, size, mark_group((size - m) / 2, (size - m) / 2, m, "#B98C3A"))


def render(svg: Path, out: Path, w: int, h: int | None = None) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h or w), str(svg), "-o", str(out)], check=True)


def build_icons() -> None:
    ICON.mkdir(exist_ok=True)
    masters = {
        "icon-full-bleed.svg": icon_full_bleed(),
        "icon-macos.svg": icon_macos(),
        "icon-small.svg": icon_rounded(64),
        "android-foreground.svg": android_foreground(),
        "android-monochrome.svg": android_monochrome(),
        "windows-unplated.svg": unplated(),
    }
    for name, src in masters.items():
        (ICON / name).write_text(src)

    if DIST.exists():
        shutil.rmtree(DIST)
    full, mac, small = ICON / "icon-full-bleed.svg", ICON / "icon-macos.svg", ICON / "icon-small.svg"

    # Apple: one asset catalog app icon set. iOS uses the single 1024 universal image; macOS needs every size.
    apple = DIST / "apple" / "AppIcon.appiconset"
    images = [{"filename": "ios-1024.png", "idiom": "universal", "platform": "ios", "size": "1024x1024"}]
    render(full, apple / "ios-1024.png", 1024)
    for pt in (16, 32, 128, 256, 512):
        for scale in (1, 2):
            px = pt * scale
            src = small if px <= 32 else mac
            fn = f"mac-{pt}@{scale}x.png"
            render(src, apple / fn, px)
            images.append({"filename": fn, "idiom": "mac", "scale": f"{scale}x", "size": f"{pt}x{pt}"})
    (apple / "Contents.json").write_text(json.dumps({"images": images, "info": {"author": "xcode", "version": 1}}, indent=2) + "\n")

    # Android: adaptive icon (vector foreground + colour background + monochrome) and legacy PNGs.
    res = DIST / "android" / "res"
    dens = {"mdpi": 1, "hdpi": 1.5, "xhdpi": 2, "xxhdpi": 3, "xxxhdpi": 4}
    for d, k in dens.items():
        render(full, res / f"mipmap-{d}" / "ic_launcher.png", round(48 * k))
        render(ICON / "android-foreground.svg", res / f"mipmap-{d}" / "ic_launcher_foreground.png", round(108 * k))
    render(full, DIST / "android" / "play-store-512.png", 512)
    (res / "mipmap-anydpi-v26").mkdir(parents=True, exist_ok=True)
    (res / "mipmap-anydpi-v26" / "ic_launcher.xml").write_text(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<adaptive-icon xmlns:android="http://schemas.android.com/apk/res/android">\n'
        '    <background android:drawable="@color/ic_launcher_background"/>\n'
        '    <foreground android:drawable="@drawable/ic_launcher_foreground"/>\n'
        '    <monochrome android:drawable="@drawable/ic_launcher_monochrome"/>\n'
        '</adaptive-icon>\n')
    (res / "values").mkdir(parents=True, exist_ok=True)
    (res / "values" / "ic_launcher_background.xml").write_text(
        f'<?xml version="1.0" encoding="utf-8"?>\n<resources>\n    <color name="ic_launcher_background">{INK}</color>\n</resources>\n')
    (res / "drawable").mkdir(parents=True, exist_ok=True)
    m, off = 52, (108 - 52) / 2
    s = m / 64
    group = f'android:translateX="{off:g}" android:translateY="{off:g}" android:scaleX="{s:g}" android:scaleY="{s:g}"'
    fg = (f'<?xml version="1.0" encoding="utf-8"?>\n'
          f'<vector xmlns:android="http://schemas.android.com/apk/res/android" xmlns:aapt="http://schemas.android.com/aapt"\n'
          f'    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">\n'
          f'    <group {group}>\n'
          f'        <path android:fillType="evenOdd" android:pathData="{MARK}">\n'
          f'            <aapt:attr name="android:fillColor">\n'
          f'                <gradient android:type="linear" android:startX="64" android:startY="0" android:endX="0" android:endY="64">\n'
          f'                    <item android:offset="0" android:color="#FF{BRASS_HI[1:]}"/>\n'
          f'                    <item android:offset="1" android:color="#FF{BRASS_LO[1:]}"/>\n'
          f'                </gradient>\n'
          f'            </aapt:attr>\n'
          f'        </path>\n'
          f'    </group>\n</vector>\n')
    (res / "drawable" / "ic_launcher_foreground.xml").write_text(fg)
    mono = (f'<?xml version="1.0" encoding="utf-8"?>\n'
            f'<vector xmlns:android="http://schemas.android.com/apk/res/android"\n'
            f'    android:width="108dp" android:height="108dp" android:viewportWidth="108" android:viewportHeight="108">\n'
            f'    <group {group}>\n'
            f'        <path android:fillType="evenOdd" android:fillColor="#FFFFFFFF" android:pathData="{MARK}"/>\n'
            f'    </group>\n</vector>\n')
    (res / "drawable" / "ic_launcher_monochrome.xml").write_text(mono)

    # Windows (MSIX): plated tiles, store logo, unplated target sizes, ICO.
    win = DIST / "windows" / "Assets"
    for sc in (100, 125, 150, 200, 400):
        f = sc / 100
        render(full if 44 * f > 48 else small, win / f"Square44x44Logo.scale-{sc}.png", round(44 * f))
        render(full, win / f"Square150x150Logo.scale-{sc}.png", round(150 * f))
        render(full, win / f"StoreLogo.scale-{sc}.png", round(50 * f))
        render(full, win / f"SmallTile.scale-{sc}.png", round(71 * f))
        render(full, win / f"LargeTile.scale-{sc}.png", round(310 * f))
        wide = ICON / "windows-wide.svg"
        if not wide.exists():
            mw = 90
            wide.write_text(svg_doc(310, 150, DEFS + '\n<rect width="310" height="150" fill="url(#tile)"/>\n'
                                    + mark_group((310 - mw) / 2, (150 - mw) / 2, mw, "url(#brass)")))
        render(wide, win / f"Wide310x150Logo.scale-{sc}.png", round(310 * f), round(150 * f))
    for t in (16, 20, 24, 30, 32, 36, 40, 48, 60, 64, 72, 80, 96, 256):
        render(small, win / f"Square44x44Logo.targetsize-{t}.png", t)
        render(ICON / "windows-unplated.svg", win / f"Square44x44Logo.targetsize-{t}_altform-unplated.png", t)
        render(ICON / "windows-unplated.svg", win / f"Square44x44Logo.targetsize-{t}_altform-lightunplated.png", t)
    ico_sizes = (16, 24, 32, 48, 64, 256)
    tmp = win / "_ico"
    for t in ico_sizes:
        render(small, tmp / f"{t}.png", t)
    frames = [Image.open(tmp / f"{t}.png").convert("RGBA") for t in ico_sizes]
    frames[-1].save(win / "AppIcon.ico", sizes=[(t, t) for t in ico_sizes], append_images=frames[:-1])
    shutil.rmtree(tmp)

    # Web: favicon set for Studio.
    web = DIST / "web"
    web.mkdir(parents=True, exist_ok=True)
    shutil.copy(small, web / "favicon.svg")
    for t in (16, 32, 48):
        render(small, web / f"favicon-{t}.png", t)
    render(full, web / "apple-touch-icon.png", 180)
    render(small, web / "icon-192.png", 192)
    render(small, web / "icon-512.png", 512)
    frames = [Image.open(web / f"favicon-{t}.png").convert("RGBA") for t in (16, 32, 48)]
    frames[-1].save(web / "favicon.ico", sizes=[(16, 16), (32, 32), (48, 48)], append_images=frames[:-1])

    # Contact sheet of the mark at small sizes, for review.
    sheet = ICON / "_legibility.svg"
    cells = []
    x = 12
    for sz in (16, 20, 24, 32, 48):
        cells.append(mark_group(x, 12, sz, INK))
        cells.append(mark_group(x, 76, sz, BRASS_ON_DARK))
        x += sz + 20
    x += 10
    for sz in (16, 24, 32, 48):
        cells.append(f'<g transform="translate({x} 12) scale({sz/64:g})">{icon_rounded(64).split(">", 1)[1].rsplit("</svg>", 1)[0]}</g>')
        x += sz + 20
    body = (f'<rect width="{x}" height="64" fill="{PAPER}"/><rect y="64" width="{x}" height="64" fill="#131210"/>' + "".join(cells))
    sheet.write_text(svg_doc(x, 128, body))
    render(sheet, HERE / "legibility.png", x * 3, 128 * 3)
    sheet.unlink()


# ---------- social preview ----------

SOCIAL = HERE / "social"
TAGLINE = "A score for your brass band, from any recording."


def social_preview() -> str:
    """1280 x 640 image for link previews (GitHub, chat apps): the app icon's ink ground, the mark in
    brass, the wordmark and the tagline. GitHub crops about 40 px on every side in some views, so all
    content stays well inside."""
    w, h = 1280, 640
    regular = TTFont(FONTS / "InstrumentSerif-Regular.ttf")
    italic = TTFont(FONTS / "InstrumentSerif-Italic.ttf")
    word_size, tag_size = 168, 46
    mark = 232
    gap = 44
    # Measure first, then centre the mark + text block horizontally.
    _, word_end = text_path(regular, "Brasscribe", word_size, 0, 0, 0.005)
    _, tag_end = text_path(italic, TAGLINE, tag_size, 0, 0, 0.0)
    block_w = mark + gap + max(word_end, tag_end)
    x0 = (w - block_w) / 2
    tx = x0 + mark + gap
    top = (h - mark) / 2
    word_base = top + mark * 0.60
    tag_base = word_base + tag_size * 1.75
    d_word, _ = text_path(regular, "Brasscribe", word_size, tx, word_base, 0.005)
    d_tag, _ = text_path(italic, TAGLINE, tag_size, tx + 4, tag_base, 0.0)
    body = (DEFS + f'\n<rect width="{w}" height="{h}" fill="url(#tile)"/>\n'
            + mark_group(x0, top, mark, "url(#brass)") + "\n"
            + f'<path fill="#EDEBE6" d="{d_word}"/>\n'
            + f'<path fill="{BRASS_ON_DARK}" d="{d_tag}"/>')
    return svg_doc(w, h, body)


def build_social() -> None:
    SOCIAL.mkdir(exist_ok=True)
    src = SOCIAL / "social-preview.svg"
    src.write_text(social_preview())
    render(src, SOCIAL / "social-preview.png", 1280, 640)


if __name__ == "__main__":
    build_logo()
    build_icons()
    build_social()
    print("brand assets written to", LOGO.relative_to(ROOT), ICON.relative_to(ROOT), DIST.relative_to(ROOT))
