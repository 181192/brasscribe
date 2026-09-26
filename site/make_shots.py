"""Make the site's screenshots from the apps' own screenshots, as listed in site/shots.txt.

Each source is cropped to its frame's ratio (phones 9:20 from the top, desktops 16:10 from the
top), scaled to twice its largest display size, then written as WebP, plus a quantised PNG for
light variants (the <img> fallback). Needs cwebp and pngquant on PATH.
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
SIZES = {"phone": (600, 1334), "desktop": (1440, 900)}
LIMIT = 250 * 1024


def crop_to(img: Image.Image, w: int, h: int) -> Image.Image:
    target = w / h
    sw, sh = img.size
    if sw / sh > target:  # too wide: keep the middle
        nw = round(sh * target)
        left = (sw - nw) // 2
        img = img.crop((left, 0, left + nw, sh))
    else:  # too tall: keep the top, where the screen's title is
        img = img.crop((0, 0, sw, round(sw / target)))
    return img.resize((w, h), Image.LANCZOS)


def run(*cmd: str) -> None:
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> int:
    for tool in ("cwebp", "pngquant"):
        if not shutil.which(tool):
            print(f"{tool} is missing (brew install webp pngquant)", file=sys.stderr)
            return 1
    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)
    rows = [
        line.split()
        for line in (ROOT / "site" / "shots.txt").read_text().splitlines()
        if line.strip() and not line.startswith("#")
    ]
    tmp = Path(tempfile.mkdtemp())
    for slot, kind, *srcs in rows:
        w, h = SIZES[kind]
        for (lang, theme), src in zip(
            [("en", "light"), ("en", "dark"), ("nb", "light"), ("nb", "dark")], srcs
        ):
            if src == "-":
                continue
            name = f"{slot}-{lang}-{theme}"
            img = crop_to(Image.open(ROOT / src).convert("RGB"), w, h)
            png = tmp / f"{name}.png"
            img.save(png)
            run("cwebp", "-quiet", "-q", "82", "-m", "6", "-sharp_yuv", str(png), "-o", str(OUT / f"{name}.webp"))
            if theme == "light":
                run("pngquant", "--quality", "60-90", "--speed", "1", "--strip", "--force",
                    "--output", str(OUT / f"{name}.png"), str(png))
    total = 0
    for f in sorted(OUT.iterdir()):
        size = f.stat().st_size
        total += size
        flag = "  TOO BIG" if size > LIMIT else ""
        print(f"{size // 1024:5d} KB  {f.name}{flag}")
    print(f"{total / 1024 / 1024:.2f} MB in {len(list(OUT.iterdir()))} files")
    return 0


if __name__ == "__main__":
    sys.exit(main())
