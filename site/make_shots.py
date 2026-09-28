"""Make the site's screenshots from the apps' own screenshots, as listed in site/shots.txt.

Each source is cropped to its kind's ratio (see SIZES; too tall keeps the top, too wide keeps the
middle; a kind without a height keeps the source's own ratio), then written at two sizes: the 2x
size (<slot>-<lang>-<theme>.avif/.webp) and half of it (…-1x.avif/.webp), plus a quantised PNG at
2x for light variants (the <img> fallback). Needs avifenc, cwebp and pngquant on PATH.
Usage: uv run --with pillow python site/make_shots.py
"""

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "site" / "shots"
# 2x pixel size per kind. phone = iPhone 17 portrait (1206 × 2622), tablet = iPad Air 11" portrait
# (1640 × 2360), desktop = 16:10, mac = a macOS window capture at its own ratio.
SIZES = {"phone": (600, 1304), "tablet": (720, 1036), "desktop": (1440, 900), "mac": (1440, None)}
LIMIT = 250 * 1024


def crop_to(img: Image.Image, w: int, h: int | None) -> Image.Image:
    sw, sh = img.size
    if h is None:
        return img.resize((w, round(sh * w / sw)), Image.LANCZOS)
    target = w / h
    if sw / sh > target:  # too wide: keep the middle
        nw = round(sh * target)
        left = (sw - nw) // 2
        img = img.crop((left, 0, left + nw, sh))
    else:  # too tall: keep the top, where the screen's title is
        img = img.crop((0, 0, sw, round(sw / target)))
    return img.resize((w, h), Image.LANCZOS)


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def encode(png: Path, stem: str) -> None:
    run("cwebp", "-quiet", "-q", "82", "-m", "6", "-sharp_yuv", "-exact", str(png), "-o", str(OUT / f"{stem}.webp"))
    run("avifenc", "-q", "60", "-s", "4", "-j", "all", str(png), str(OUT / f"{stem}.avif"))


def main() -> int:
    for tool in ("avifenc", "cwebp", "pngquant"):
        if not shutil.which(tool):
            print(f"{tool} is missing (brew install libavif webp pngquant)", file=sys.stderr)
            return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rows, names = [], {}
    for line in (ROOT / "site" / "shots.txt").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        if "=" in line and " " not in line.strip():  # NAME=path, used as $NAME below
            key, value = line.strip().split("=", 1)
            names[key] = value
            continue
        cols = line.split()
        for key, value in names.items():
            cols = [c.replace(f"${key}", value) for c in cols]
        rows.append(cols)
    tmp = Path(tempfile.mkdtemp())
    for slot, kind, *srcs in rows:
        w, h = SIZES[kind]
        for (lang, theme), src in zip(
            [("en", "light"), ("en", "dark"), ("nb", "light"), ("nb", "dark")], srcs
        ):
            if src == "-":
                continue
            name = f"{slot}-{lang}-{theme}"
            # A macOS window capture has transparent rounded corners: keep them.
            img = crop_to(Image.open(ROOT / src).convert("RGBA" if kind == "mac" else "RGB"), w, h)
            png = tmp / f"{name}.png"
            img.save(png)
            encode(png, name)
            half = tmp / f"{name}-1x.png"
            img.resize((img.width // 2, img.height // 2), Image.LANCZOS).save(half)
            encode(half, f"{name}-1x")
            if theme == "light":
                run("pngquant", "--quality", "60-90", "--speed", "1", "--strip", "--force",
                    "--output", str(OUT / f"{name}.png"), str(png))
            print(f"{name}: {img.width} × {img.height}")
    total = 0
    for f in sorted(OUT.iterdir()):
        size = f.stat().st_size
        total += size
        flag = "  TOO BIG" if size > LIMIT else ""
        if flag:
            print(f"{size // 1024:5d} KB  {f.name}{flag}")
    print(f"{total / 1024 / 1024:.2f} MB in {len(list(OUT.iterdir()))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
