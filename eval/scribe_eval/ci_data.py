"""Build the data directory CI benchmarks run on, without dataset audio.

Two sources:
  - ChoraleBricks v1.1.0 annotations (CC-BY 4.0, Zenodo 10.5281/zenodo.20849469):
    only metadata_tracks.csv and the alignment CSVs of the brass-quartet tracks are
    read, straight out of the 1.2 GB archive with HTTP range requests (a few MB).
    Every extracted file and every built reference.json is checked against the
    sha256 pinned in eval/fixtures/choralebricks-pins.json.
  - eval/fixtures/: our own model outputs on those chorales (MuScriptor, Basic
    Pitch, Beat This! MIDI/beats; SwiftF0 contours of the part tracks).

    python -m brasscribe_eval.ci_data --out ci-data              # download
    python -m brasscribe_eval.ci_data --out ci-data --zip X.zip  # from a local copy of the archive
    python -m brasscribe_eval.ci_data --pin                      # rewrite pins from data/ (maintainers)

Then `BRASSCRIBE_DATA=ci-data brasscribe bench ci --require-data`.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

import pandas as pd

from .choralebricks import BRASS_QUARTET, alignment_path, reference_notes, track_row, write_reference
from .paths import DATA, ROOT

URL = "https://zenodo.org/records/20849469/files/01_AudioAndAnnotations.zip"
ARCHIVE_BYTES = 1157617569
PREFIX = "01_AudioAndAnnotations/"
FIXTURES = ROOT / "eval" / "fixtures"
PINS = FIXTURES / "choralebricks-pins.json"
SET = "choralebricks-brass4"


class HttpRangeFile(io.RawIOBase):
    """Read-only, seekable view of a remote file via HTTP Range requests (enough for zipfile)."""

    def __init__(self, url: str, size: int):
        self.url, self.size, self.pos = url, size, 0
        self.fetched = 0

    def seekable(self) -> bool:
        return True

    def readable(self) -> bool:
        return True

    def tell(self) -> int:
        return self.pos

    def seek(self, offset: int, whence: int = 0) -> int:
        self.pos = {0: offset, 1: self.pos + offset, 2: self.size + offset}[whence]
        return self.pos

    def read(self, n: int = -1) -> bytes:
        if n is None or n < 0:
            n = self.size - self.pos
        if n == 0 or self.pos >= self.size:
            return b""
        end = min(self.size, self.pos + n) - 1
        req = urllib.request.Request(self.url, headers={"Range": f"bytes={self.pos}-{end}"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=60) as r:
                    if r.status != 206:
                        raise OSError(f"server ignored the Range header (HTTP {r.status})")
                    data = r.read()
                break
            except OSError:
                if attempt == 3:
                    raise
        self.pos += len(data)
        self.fetched += len(data)
        return data

    def readinto(self, b) -> int:
        data = self.read(len(b))
        b[: len(data)] = data
        return len(data)


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _needed(tracks: pd.DataFrame) -> dict[str, dict[str, str]]:
    """song -> part -> alignment path (relative to 01_AudioAndAnnotations)."""
    out: dict[str, dict[str, str]] = {}
    for song in sorted(tracks.song_id.unique()):
        try:
            out[song] = {part: alignment_path(song, track_row(tracks, song, part, inst).path_audio)
                         for part, inst in BRASS_QUARTET.items()}
        except SystemExit:
            continue
    return out


def build(read, out: Path, pins: dict | None) -> dict:
    """read(relative path) -> bytes. Writes <out>/eval/choralebricks-brass4/<song>/reference.json."""
    got: dict[str, str] = {}

    def fetch(rel: str) -> bytes:
        data = read(rel)
        got[rel] = _sha(data)
        if pins is not None and pins["files"].get(rel) != got[rel]:
            raise SystemExit(f"checksum mismatch for {rel}: {got[rel]} (pinned {pins['files'].get(rel)})")
        return data

    tracks = pd.read_csv(io.BytesIO(fetch("metadata_tracks.csv")), sep=";")
    refs: dict[str, str] = {}
    for song, parts in _needed(tracks).items():
        alignments = {part: pd.read_csv(io.BytesIO(fetch(rel)), sep=";") for part, rel in parts.items()}
        dest = out / "eval" / SET / song
        write_reference(dest, reference_notes(alignments, BRASS_QUARTET), dict(BRASS_QUARTET))
        refs[song] = _sha((dest / "reference.json").read_bytes())
        if pins is not None and pins["references"].get(song) != refs[song]:
            raise SystemExit(f"{song}: built reference.json differs from the pinned one")
    return {"files": got, "references": refs}


def copy_fixtures(out: Path) -> int:
    n = 0
    for src in sorted((FIXTURES / SET).rglob("*")):
        if src.is_file():
            dst = out / "eval" / SET / src.relative_to(FIXTURES / SET)
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            n += 1
    contours = FIXTURES / "contours" / SET
    if contours.is_dir():
        shutil.copytree(contours, out / "runs" / "contours" / SET, dirs_exist_ok=True)
    return n


def pin() -> None:
    """Record checksums from the local ChoraleBricks copy and check they rebuild data/eval exactly."""
    root = DATA / "choralebricks" / "01_AudioAndAnnotations"
    tmp = ROOT / ".pixi" / "ci-data-pin"
    shutil.rmtree(tmp, ignore_errors=True)
    result = build(lambda rel: (root / rel).read_bytes(), tmp, None)
    for song, digest in result["references"].items():
        local = DATA / "eval" / SET / song / "reference.json"
        if _sha(local.read_bytes()) != digest:
            raise SystemExit(f"{song}: rebuilt reference.json differs from {local}")
    PINS.write_text(json.dumps({"source": URL, "doi": "10.5281/zenodo.20849469", "licence": "CC-BY 4.0",
                                "archive_bytes": ARCHIVE_BYTES, **result}, indent=1, sort_keys=True) + "\n")
    shutil.rmtree(tmp)
    print(f"pinned {len(result['files'])} files, {len(result['references'])} references -> {PINS}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path)
    ap.add_argument("--zip", type=Path, help="local copy of 01_AudioAndAnnotations.zip instead of downloading")
    ap.add_argument("--pin", action="store_true", help="rewrite the pins from the local data directory")
    args = ap.parse_args()
    if args.pin:
        return pin()
    if not args.out:
        ap.error("--out is required")
    pins = json.loads(PINS.read_text())
    remote = None if args.zip else HttpRangeFile(URL, pins["archive_bytes"])
    with zipfile.ZipFile(args.zip if args.zip else io.BufferedReader(remote, buffer_size=1 << 16)) as z:
        build(lambda rel: z.read(PREFIX + rel), args.out, pins)
    n = copy_fixtures(args.out)
    fetched = f", {remote.fetched / 1e6:.1f} MB downloaded" if remote else ""
    print(f"{len(pins['references'])} chorale references and {n} model-output fixtures in {args.out}{fetched}")


if __name__ == "__main__":
    sys.exit(main())
