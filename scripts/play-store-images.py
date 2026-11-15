#!/usr/bin/env python3
"""The pictures Google Play asks for, for both apps (docs/play-store.md says where each goes):

    python3 scripts/play-store-images.py

Writes docs/play-store/<app>/:
  icon-512.png               the store icon, 512 x 512 (Brasscribe's is its brand build's play-store-512.png)
  feature-graphic.png        1024 x 500, from the brand's own artwork
  screenshots/<lang>-<n>-<screen>.png   phone screenshots from the Android screen catalogue

Every file is a 24-bit PNG without alpha, as Play wants. A catalogue screenshot is 1080 x 2400 (2.22:1), taller
than Play's 2:1, so it is padded at the sides to 1200 x 2400 with the colour of its own left edge: nothing of the
screen is cut. Only screens that show the public-domain Old Hundredth or an invented song are used.

Standard library only, plus rsvg-convert (librsvg) on PATH for the SVG artwork.
"""

from __future__ import annotations

import struct
import subprocess
import tempfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRANDS = ROOT / "design" / "brands"
SHOTS = ROOT / "apps" / "android" / "docs" / "screenshots"

# Per app and language, in the order Play shows them: (name, catalogue file).
SCREENSHOTS = {
    "brasscribe": {
        "en": [("first-run", "brasscribe/my-instrument/first-run-chosen-en-light.png"),
               ("score", "brasscribe/my-instrument/score-en-light.png"),
               ("check", "brasscribe/my-instrument/review-arranged-en-light.png"),
               ("music-stand", "brasscribe/music-stand/en-portrait-shown.png")],
        "no": [("first-run", "brasscribe/my-instrument/first-run-chosen-nb-light.png"),
               ("score", "brasscribe/my-instrument/score-nb-light.png"),
               ("check", "brasscribe/my-instrument/review-arranged-nb-light.png"),
               ("music-stand", "brasscribe/music-stand/nb-portrait-shown.png")],
    },
    "fretscribe": {
        "en": [("tab", "fretscribe/tab-light.png"),
               ("instrument", "fretscribe/your-instrument-light.png"),
               ("check", "fretscribe/check-the-song-light.png"),
               ("practise", "fretscribe/practice-repeat-light.png")],
        "no": [("tab", "fretscribe/tab-nb.png"),
               ("instrument", "fretscribe/your-instrument-nb.png"),
               ("check", "fretscribe/check-the-song-nb.png"),
               ("practise", "fretscribe/practice-repeat-nb.png")],
    },
}


# --- PNG in and out (8-bit RGB or RGBA, not interlaced) ---------------------------------------------------------

def read_png(path: Path) -> tuple[int, int, list[bytearray]]:
    """Width, height and rows of RGB bytes; alpha is laid over white."""
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path} is not a PNG"
    i, idat, w = 8, b"", 0
    while i < len(data):
        n, kind = struct.unpack(">I4s", data[i:i + 8])
        body = data[i + 8:i + 8 + n]
        if kind == b"IHDR":
            w, h, depth, colour, _, _, interlace = struct.unpack(">IIBBBBB", body)
            assert depth == 8 and colour in (2, 6) and not interlace, f"{path}: only 8-bit RGB/RGBA, not interlaced"
        elif kind == b"IDAT":
            idat += body
        i += 12 + n
    bpp = 3 if colour == 2 else 4
    raw, stride, prev, rows = zlib.decompress(idat), w * bpp, bytearray(w * bpp), []
    for y in range(h):
        f, line = raw[y * (stride + 1)], bytearray(raw[y * (stride + 1) + 1:(y + 1) * (stride + 1)])
        for x in range(stride):
            a = line[x - bpp] if x >= bpp else 0
            b, c = prev[x], prev[x - bpp] if x >= bpp else 0
            if f == 1:
                line[x] = (line[x] + a) & 255
            elif f == 2:
                line[x] = (line[x] + b) & 255
            elif f == 3:
                line[x] = (line[x] + (a + b) // 2) & 255
            elif f == 4:
                p = a + b - c
                pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        prev = line
        if bpp == 4:
            rgb = bytearray(w * 3)
            for x in range(w):
                r, g, bl, al = line[x * 4:x * 4 + 4]
                rgb[x * 3:x * 3 + 3] = bytes((r * al + 255 * (255 - al)) // 255 for r in (r, g, bl))
            rows.append(rgb)
        else:
            rows.append(line)
    return w, h, rows


def write_png(path: Path, w: int, rows: list[bytearray]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    chunk = lambda kind, body: struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body))
    raw = b"".join(b"\x00" + bytes(r) for r in rows)
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", w, len(rows), 8, 2, 0, 0, 0))
                     + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def render(svg: str, w: int, h: int, out: Path, base: Path) -> None:
    """An SVG (its relative links resolved from `base`) as an RGB PNG of w x h."""
    with tempfile.TemporaryDirectory() as tmp:
        src, png = base / ".play-store-render.svg", Path(tmp) / "out.png"
        src.write_text(svg)
        try:
            subprocess.run(["rsvg-convert", "-w", str(w), "-h", str(h), str(src), "-o", str(png)], check=True)
        finally:
            src.unlink()
        width, _, rows = read_png(png)
        write_png(out, width, rows)


# --- the pictures -----------------------------------------------------------------------------------------------

def feature_brasscribe() -> str:
    """The link-preview image (1280 x 640: ink ground, the mark in brass, wordmark and tagline), widened to Play's
    2.048:1 with the same ground at the sides."""
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="500"
 viewBox="-15.36 0 1310.72 640">
<defs><linearGradient id="tile" x1="0" y1="0" x2="0" y2="1">
<stop offset="0" stop-color="#2B2824"/><stop offset="1" stop-color="#141311"/></linearGradient></defs>
<rect x="-20" width="1320" height="640" fill="url(#tile)"/>
<image width="1280" height="640" xlink:href="brand/social/social-preview.svg"/>
</svg>'''


def feature_fretscribe() -> str:
    """The lockup (the mark and the wordmark) on the brand's paper."""
    lockup_w, lockup_h = 5396.6, 776  # lockup.svg's viewBox
    w = 760
    h = w * lockup_h / lockup_w
    return f'''<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" width="1024" height="500"
 viewBox="0 0 1024 500">
<rect width="1024" height="500" fill="#FAF8F3"/>
<image x="{(1024 - w) / 2:.1f}" y="{(500 - h) / 2:.1f}" width="{w}" height="{h:.1f}" xlink:href="brand/lockup.svg"/>
</svg>'''


def pad_to_two_to_one(src: Path, out: Path) -> None:
    w, h, rows = read_png(src)
    target_w, target_h = max(w, (max(h, 2 * w) + 1) // 2), max(h, 2 * w)
    if target_h > 2 * target_w:
        target_w = (target_h + 1) // 2
    left = (target_w - w) // 2
    edge = bytes(rows[h // 2][0:3])
    padded = []
    for r in rows:
        padded.append(bytearray(edge * left) + r + bytearray(edge * (target_w - w - left)))
    while len(padded) < target_h:
        padded.append(bytearray(edge * target_w))
    write_png(out, target_w, padded)


def main() -> None:
    for app, feature in (("brasscribe", feature_brasscribe), ("fretscribe", feature_fretscribe)):
        brand = BRANDS / app
        out = ROOT / "docs" / "play-store" / app
        render(feature(), 1024, 500, out / "feature-graphic.png", brand)
        if app == "fretscribe":
            render((brand / "brand" / "app-icon-fullbleed.svg").read_text(), 512, 512, out / "icon-512.png", brand / "brand")
        else:
            w, _, rows = read_png(brand / "dist" / "icons" / "android" / "play-store-512.png")
            write_png(out / "icon-512.png", w, rows)
        for lang, shots in SCREENSHOTS[app].items():
            for n, (name, file) in enumerate(shots, 1):
                pad_to_two_to_one(SHOTS / file, out / "screenshots" / f"{lang}-{n}-{name}.png")
        print(f"play_store_images: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
