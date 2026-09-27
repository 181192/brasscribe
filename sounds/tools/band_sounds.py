"""Pin, fetch and verify the band SoundFonts the apps bundle (they are built, not in git).

    python3 sounds/tools/band_sounds.py pin      # after sounds/band.py + mobile_soundfont.py: write sounds/band-sounds.json
    python3 sounds/tools/band_sounds.py verify   # data/sounds/band matches the pin (exit 1 if not)
    python3 sounds/tools/band_sounds.py fetch    # download from $BRASSCRIBE_BAND_SOUNDS_URL/<file>, verify, install

Release builds run `fetch` (then `verify`) before building, and fail when the files cannot be
had, so a release never ships without the band sounds and quietly plays the basic tier.
Hosting: upload the files listed in sounds/band-sounds.json (e.g. as assets of a GitHub release
named band-sounds-<short sha256>) and set the repository variable BRASSCRIBE_BAND_SOUNDS_URL to
the folder URL. Standard library only.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BAND = ROOT / "data" / "sounds" / "band"
PIN = ROOT / "sounds" / "band-sounds.json"
FILES = ["brasscribe-band-16bit.sf2", "brasscribe-band-mobile.sf2"]  # Apple/Windows, Android/Studio


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def pin() -> int:
    files = {n: {"sha256": sha256(BAND / n), "size": (BAND / n).stat().st_size} for n in FILES}
    PIN.write_text(json.dumps({"about": __doc__.split("\n\n")[0].strip(), "files": files}, indent=1) + "\n")
    print(f"{PIN}: {', '.join(f'{n} {v['size'] / 1e6:.1f} MB' for n, v in files.items())}")
    return 0


def verify() -> int:
    bad = 0
    for n, v in json.loads(PIN.read_text())["files"].items():
        p = BAND / n
        if not p.exists():
            print(f"missing {p}")
            bad += 1
        elif p.stat().st_size != v["size"] or sha256(p) != v["sha256"]:
            print(f"differs from the pin: {p}")
            bad += 1
        else:
            print(f"ok {n}")
    return 1 if bad else 0


def fetch() -> int:
    base = os.environ.get("BRASSCRIBE_BAND_SOUNDS_URL", "").rstrip("/")
    if not base:
        print("BRASSCRIBE_BAND_SOUNDS_URL is not set: a release cannot be built without the band sounds "
              "(see sounds/tools/band_sounds.py)")
        return 1
    BAND.mkdir(parents=True, exist_ok=True)
    for n, v in json.loads(PIN.read_text())["files"].items():
        p = BAND / n
        if p.exists() and sha256(p) == v["sha256"]:
            print(f"ok {n} (cached)")
            continue
        print(f"downloading {base}/{n}")
        tmp = p.with_suffix(".part")
        urllib.request.urlretrieve(f"{base}/{n}", tmp)
        if sha256(tmp) != v["sha256"]:
            tmp.unlink()
            print(f"sha256 mismatch for {n}")
            return 1
        tmp.replace(p)
    return verify()


if __name__ == "__main__":
    sys.exit({"pin": pin, "verify": verify, "fetch": fetch}[sys.argv[1]]())
