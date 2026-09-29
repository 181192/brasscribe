"""Fetch, verify and pin the band SoundFonts the apps bundle (they are built, not in git).

    python3 sounds/tools/band_sounds.py fetch  [--dir DIR] [FILE...]   # download the pinned release, verify, install
    python3 sounds/tools/band_sounds.py verify [--dir DIR] [FILE...]   # DIR matches the pin (exit 1 if not)
    python3 sounds/tools/band_sounds.py pin    [--version TAG] [--dir DIR]  # after a rebuild: rewrite sounds/band-sounds.json

sounds/band-sounds.json pins one sound pack: the GitHub release tag (`version`) in this repository
and the size and sha256 of every file. DIR defaults to data/sounds/band; FILE defaults to every
pinned file. `fetch` uses the GitHub CLI (`gh release download`), which needs a login (`gh auth
login`) or GH_TOKEN; the repository is private, so the files are bundled into the apps at build time
and never downloaded by users. Files already in DIR with the pinned hash are kept. The release's
SHA256SUMS must agree with the pin, and every file must match it, or nothing is installed.

Every release build fetches before it builds and stops when the files cannot be had, so a release
never ships without the band sounds and quietly plays the basic tier.

Publishing a new pack: build the files (sounds/band.py --bits 16, apps/android/scripts/mobile_soundfont.py),
`pin --version sounds-YYYY.MM.DD`, then
`gh release create sounds-YYYY.MM.DD --prerelease data/sounds/band/{brasscribe-band-16bit.sf2,brasscribe-band-mobile.sf2,SHA256SUMS}`.
Standard library only.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BAND = ROOT / "data" / "sounds" / "band"
PIN = ROOT / "sounds" / "band-sounds.json"
SUMS = "SHA256SUMS"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def load_pin() -> dict:
    return json.loads(PIN.read_text())


def selected(pin: dict, names: list[str]) -> dict[str, dict]:
    files = pin["files"]
    unknown = [n for n in names if n not in files]
    if unknown:
        raise SystemExit(f"not in {PIN.name}: {', '.join(unknown)} (pinned: {', '.join(files)})")
    return {n: files[n] for n in (names or files)}


def matches(path: Path, want: dict) -> bool:
    return path.is_file() and path.stat().st_size == want["size"] and sha256(path) == want["sha256"]


def parse_sums(text: str) -> dict[str, str]:
    """`<sha256>  <name>` lines (sha256sum / shasum -a 256 output, `*name` in binary mode too)."""
    out = {}
    for line in text.splitlines():
        parts = line.split(None, 1)
        if len(parts) == 2:
            out[parts[1].strip().lstrip("*")] = parts[0].lower()
    return out


def write_sums(pin: dict, dest: Path) -> None:
    (dest / SUMS).write_text("".join(f"{v['sha256']}  {n}\n" for n, v in pin["files"].items()))


def verify(dest: Path, names: list[str]) -> int:
    bad = 0
    for n, v in selected(load_pin(), names).items():
        p = dest / n
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            bad += 1
        elif not matches(p, v):
            print(f"differs from sounds/band-sounds.json: {p}", file=sys.stderr)
            bad += 1
        else:
            print(f"ok {n}")
    return 1 if bad else 0


def gh_download(pin: dict, patterns: list[str], into: Path) -> None:
    gh = shutil.which("gh")
    if not gh:
        raise SystemExit("the GitHub CLI (gh) is needed to fetch the band sounds: https://cli.github.com, then `gh auth login`")
    cmd = [gh, "release", "download", pin["version"], "--repo", pin["repo"], "--dir", str(into), "--clobber"]
    for p in patterns:
        cmd += ["--pattern", p]
    print(f"gh release download {pin['version']} ({', '.join(patterns)})", flush=True)
    r = subprocess.run(cmd)
    if r.returncode != 0:
        raise SystemExit(f"could not download the band sounds from release {pin['version']} of {pin['repo']} "
                         "(logged in with `gh auth login`, or GH_TOKEN set with contents: read?)")


def fetch(dest: Path, names: list[str]) -> int:
    pin = load_pin()
    want = selected(pin, names)
    dest.mkdir(parents=True, exist_ok=True)
    todo = [n for n, v in want.items() if not matches(dest / n, v)]
    for n in want:
        if n not in todo:
            print(f"ok {n} (already here)")
    if todo:
        with tempfile.TemporaryDirectory(dir=dest, prefix=".fetch-") as tmp:
            t = Path(tmp)
            gh_download(pin, [SUMS, *todo], t)
            sums = parse_sums((t / SUMS).read_text())
            for n in todo:
                if sums.get(n) != want[n]["sha256"]:
                    raise SystemExit(f"{SUMS} of {pin['version']} says {sums.get(n)} for {n}, the pin says {want[n]['sha256']}")
                if not matches(t / n, want[n]):
                    raise SystemExit(f"{n} from {pin['version']} does not match its sha256/size; nothing installed")
            for n in todo:
                (t / n).replace(dest / n)
                print(f"installed {dest / n}")
    return verify(dest, list(want))


def pin_files(version: str | None, band: Path = BAND) -> int:
    pin = load_pin()
    if version:
        pin["version"] = version
    pin["files"] = {n: {"sha256": sha256(band / n), "size": (band / n).stat().st_size} for n in pin["files"]}
    PIN.write_text(json.dumps(pin, indent=1) + "\n")
    write_sums(pin, band)
    print(f"{PIN} ({pin['version']}): {', '.join(f'{n} {v['size'] / 1e6:.1f} MB' for n, v in pin['files'].items())}")
    return 0


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("fetch", "verify"):
        s = sub.add_parser(name)
        s.add_argument("--dir", type=Path, default=BAND, help="where the files go (default: data/sounds/band)")
        s.add_argument("files", nargs="*", help="pinned file names (default: all)")
    p = sub.add_parser("pin")
    p.add_argument("--version", help="release tag of the new pack, e.g. sounds-2026.09.27")
    p.add_argument("--dir", type=Path, default=BAND, help="where the built files are (default: data/sounds/band)")
    a = ap.parse_args(argv)
    if a.cmd == "pin":
        return pin_files(a.version, a.dir.resolve())
    return (fetch if a.cmd == "fetch" else verify)(a.dir.resolve(), a.files)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
