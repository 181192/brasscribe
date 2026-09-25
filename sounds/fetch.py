# /// script
# requires-python = ">=3.12"
# dependencies = ["truststore>=0.10"]
# ///
"""Download the sample libraries and impulse responses for the realistic sound tier.

    uv run sounds/fetch.py            # download what is missing, verify every sha256
    uv run sounds/fetch.py --pin      # rediscover the file lists, download, rewrite manifest.json

Everything lands in data/sounds/raw/ (gitignored). `sounds/manifest.json` pins every
file by URL, size and sha256, and carries the licence and attribution text per source.
Upstream URLs are pinned to commits where the host supports it (GitHub); the Iowa and
OpenAIR hosts have no versioning, so a changed file shows up as a checksum failure.
"""

from __future__ import annotations

import argparse
import concurrent.futures as cf
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path

try:  # use the OS trust store (needed behind TLS-inspecting proxies)
    import truststore

    truststore.inject_into_ssl()
except ImportError:
    pass

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
MANIFEST = HERE / "manifest.json"
RAW = ROOT / "data" / "sounds" / "raw"

VSCO_REPO = "sgossner/VSCO-2-CE"
VSCO_COMMIT = "440300901dfe9275fd84e0b7763af1f8443ae62e"
# Sustain and staccato for the four modern brass instruments. OldTrombone, mutes and
# vibrato variants are left out: the band plays open, non-vibrato sustains.
VSCO_DIRS = [
    "Brass/Trumpet/sus", "Brass/Trumpet/stac",
    "Brass/F Horn/sus", "Brass/F Horn/stac",
    "Brass/Tenor Trombone/sus", "Brass/Tenor Trombone/stac",
    "Brass/Tuba/sus", "Brass/Tuba/stac",
]

MUSESCORE_REPO = "musescore/MuseScore"
MUSESCORE_COMMIT = "37128c5ac8f9af804b63650610952414421828b8"  # last change to MS Basic.sf3
MUSESCORE_FILES = ["share/sound/MS Basic.sf3", "share/sound/MS Basic_License.md", "share/sound/MS Basic_Readme.md"]

IOWA_BASE = "https://theremin.music.uiowa.edu/"
# Per-pitch pages (2014 re-edit, ff only) and chromatic-run pages (pp/mf/ff, one file per octave).
IOWA_PAGES = {
    "trumpet": ["MIS-Pitches-2012/MISBbTrumpet2012.html", "MISBbtrumpet.html"],
    "horn": ["MIS-Pitches-2012/MISHorn2012.html", "MISFrenchhorn.html"],
    "tenor-trombone": ["MIS-Pitches-2012/MISTenorTrombone2012.html", "MIStenortrombone.html"],
    "bass-trombone": ["MIS-Pitches-2012/MISBassTrombone2012.html", "MISbasstrombone.html"],
    "tuba": ["MIS-Pitches-2012/MISTuba2012.html", "MIStuba.html"],
}

OPENAIR_BASE = "https://webfiles.york.ac.uk/OPENAIR/IRs/"
# Licence and attribution scraped from the archived OpenAIR entry pages (the live
# openair.hosted.york.ac.uk and openairlib.net hosts return "account suspended";
# the IR zips themselves are still served from webfiles.york.ac.uk).
OPENAIR = [
    {
        "id": "central-hall-university-york",
        "title": "Central Hall, University of York",
        "role": "concert hall (default room)",
        "attribution": "www.openairlib.net; Alexander Vilkaitis, Ilias Antonopoulos, Joska De Langen, Xuan Liu",
        "evidence": "https://web.archive.org/web/20260331080517/https://www.openair.hosted.york.ac.uk/?page_id=435",
    },
    {
        "id": "jack-lyons-concert-hall-university-york",
        "title": "Jack Lyons Concert Hall, University of York",
        "role": "concert hall; lp1 is the conductor's position",
        "attribution": "www.openairlib.net; Audiolab, University of York; Alex Duffell, Aishwarya Sridhar, Zhong Li",
        "evidence": "https://web.archive.org/web/20250911050036/https://www.openair.hosted.york.ac.uk/?page_id=571",
    },
    {
        "id": "dixon-studio-theatre-university-york",
        "title": "The Dixon Studio Theatre, University of York",
        "role": "small room, band-room stand-in",
        "attribution": "www.openairlib.net; Ben Lavin, Darren Robinson, Ya-Hsin Chou; University of York",
        "evidence": "https://web.archive.org/web/20260610185221/https://www.openair.hosted.york.ac.uk/?page_id=452",
    },
    {
        "id": "st-margarets-church-ncem-5-piece-band-spatial-measurements",
        "title": "St. Margaret's Church (NCEM), 5 Piece Band Spatial Measurements",
        "role": "ensemble room with five measured source positions",
        "attribution": "www.openairlib.net; AudioLab, University of York; www.ncem.co.uk",
        "evidence": "https://web.archive.org/web/20260610182553/https://www.openair.hosted.york.ac.uk/?page_id=702",
    },
    {
        "id": "usina-del-arte-symphony-hall",
        "title": "Usina del Arte Symphony Hall",
        "role": "symphony hall with KEMAR binaural IRs (not the default: see licence note)",
        "attribution": "www.untref.edu.ar",
        "evidence": "https://web.archive.org/web/20260419210932/https://www.openair.hosted.york.ac.uk/?page_id=770",
        "licence_note": "The archived page links both CC BY-SA 3.0 and CC BY 4.0; the attribution block says CC BY 4.0. Open question: confirm with the author before bundling.",
    },
]


def http_get(url: str, timeout: int = 120) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": "brasscribe-sounds-fetch/1"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def quote_url(url: str) -> str:
    """Percent-encode the path (file names contain spaces and '#'); no query or fragment is used."""
    origin = "/".join(url.split("/")[:3])
    return origin + urllib.parse.quote(urllib.parse.unquote(url[len(origin):]))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------- discovery (--pin)

def discover_vsco() -> list[dict]:
    tree = json.loads(http_get(f"https://api.github.com/repos/{VSCO_REPO}/git/trees/{VSCO_COMMIT}?recursive=1"))
    files = []
    for node in tree["tree"]:
        p = node["path"]
        if node["type"] == "blob" and p.endswith(".wav") and any(p.startswith(d + "/") for d in VSCO_DIRS):
            files.append({
                "url": quote_url(f"https://raw.githubusercontent.com/{VSCO_REPO}/{VSCO_COMMIT}/{p}"),
                "path": f"vsco2ce/{p}",
            })
    return files


def discover_musescore() -> list[dict]:
    return [{
        "url": quote_url(f"https://raw.githubusercontent.com/{MUSESCORE_REPO}/{MUSESCORE_COMMIT}/{p}"),
        "path": f"msbasic/{Path(p).name}",
    } for p in MUSESCORE_FILES]


def discover_iowa() -> list[dict]:
    files = []
    for inst, pages in IOWA_PAGES.items():
        for page in pages:
            html = http_get(IOWA_BASE + page).decode("latin-1")
            for href in re.findall(r'href="([^"]+\.aiff?)"', html):
                name = href.rsplit("/", 1)[-1]
                # Trumpet: keep the non-vibrato set; brass-band cornets play without vibrato by default.
                if inst == "trumpet" and ".vib." in name:
                    continue
                kind = "pitch" if "2012" in page else "run"
                url = quote_url(urllib.parse.urljoin(IOWA_BASE + page, href))
                files.append({"url": url, "path": f"iowa-mis/{inst}/{kind}/{name.replace(' ', '')}"})
    return files


def discover_openair() -> list[dict]:
    return [{"url": f"{OPENAIR_BASE}{e['id']}/{e['id']}.zip", "path": f"openair/{e['id']}.zip", "extract": True}
            for e in OPENAIR]


def build_manifest() -> dict:
    sources = [
        {
            "id": "vsco2ce",
            "title": "Versilian Studios Chamber Orchestra 2, Community Edition (brass)",
            "homepage": "https://github.com/sgossner/VSCO-2-CE",
            "licence": "CC0-1.0",
            "licence_url": "https://creativecommons.org/publicdomain/zero/1.0/",
            "attribution": "Versilian Studios Chamber Orchestra 2 Community Edition, Versilian Studios LLC (CC0). Credit is not required; given as courtesy.",
            "pinned": f"git commit {VSCO_COMMIT}",
            "files": discover_vsco(),
        },
        {
            "id": "iowa-mis",
            "title": "University of Iowa Electronic Music Studios, Musical Instrument Samples (brass)",
            "homepage": "https://theremin.music.uiowa.edu/MIS.html",
            "licence": "Iowa MIS terms: 'may be downloaded and used for any projects, without restrictions'",
            "licence_url": "https://theremin.music.uiowa.edu/MIS.html",
            "attribution": "Musical Instrument Samples, University of Iowa Electronic Music Studios (Lawrence Fritts).",
            "pinned": "no versioning on the host; sha256 per file",
            "notes": "pitch/ = 2014 per-note files (ff only). run/ = chromatic runs per octave at pp, mf and ff; the builder segments them into notes.",
            "files": discover_iowa(),
        },
        {
            "id": "msbasic",
            "title": "MuseScore MS Basic SoundFont (SF3)",
            "homepage": "https://github.com/musescore/MuseScore/tree/master/share/sound",
            "licence": "MIT",
            "licence_url": f"https://github.com/{MUSESCORE_REPO}/blob/{MUSESCORE_COMMIT}/share/sound/MS%20Basic_License.md",
            "attribution": "MS Basic SoundFont, MuseScore; MIT licence, notice in MS Basic_License.md must be kept.",
            "pinned": f"git commit {MUSESCORE_COMMIT}",
            "files": discover_musescore(),
        },
    ]
    for e in OPENAIR:
        src = {
            "id": f"openair-{e['id']}",
            "title": f"OpenAIR impulse responses: {e['title']}",
            "homepage": "https://www.openair.hosted.york.ac.uk/ (host suspended as of 2026-09-25; zips still on webfiles.york.ac.uk)",
            "licence": "CC-BY-4.0",
            "licence_url": "https://creativecommons.org/licenses/by/4.0/",
            "licence_evidence": e["evidence"],
            "attribution": f"{e['title']}, OpenAIR Library, {e['attribution']}. Licensed under CC BY 4.0.",
            "role": e["role"],
            "pinned": "no versioning on the host; sha256 per file",
            "files": [f for f in discover_openair() if e["id"] in f["url"]],
        }
        if "licence_note" in e:
            src["licence_note"] = e["licence_note"]
        sources.append(src)
    return {"version": 1, "root": "data/sounds/raw", "sources": sources}


# ---------------------------------------------------------------- download + verify

def fetch_one(entry: dict, pin: bool) -> tuple[str, str]:
    dest = RAW / entry["path"]
    if dest.exists() and not pin and entry.get("sha256") and dest.stat().st_size == entry.get("size"):
        if sha256(dest) == entry["sha256"]:
            return entry["path"], "ok"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if not dest.exists() or pin:
        try:
            data = http_get(entry["url"], timeout=600)
        except OSError as e:
            return entry["path"], f"FAIL {e} {entry['url']}"
        if data[:15].lower().startswith(b"<!doctype html") or data[:6].lower() == b"<html>":
            return entry["path"], f"FAIL html instead of data from {entry['url']}"
        tmp = dest.with_suffix(dest.suffix + ".part")
        tmp.write_bytes(data)
        tmp.replace(dest)
    digest = sha256(dest)
    if pin:
        entry["sha256"], entry["size"] = digest, dest.stat().st_size
        return entry["path"], "pinned"
    if digest != entry.get("sha256"):
        return entry["path"], f"FAIL sha256 {digest} != {entry.get('sha256')}"
    return entry["path"], "downloaded"


def extract(entry: dict) -> None:
    dest = RAW / entry["path"]
    out = dest.with_suffix("")
    if out.exists():
        return
    with zipfile.ZipFile(dest) as z:
        z.extractall(out.parent)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pin", action="store_true", help="rediscover sources and rewrite manifest.json with fresh checksums")
    ap.add_argument("--only", help="comma-separated source ids")
    ap.add_argument("-j", "--jobs", type=int, default=8)
    args = ap.parse_args()

    manifest = build_manifest() if args.pin else json.loads(MANIFEST.read_text())
    only = set(args.only.split(",")) if args.only else None
    entries = [f for s in manifest["sources"] if not only or s["id"] in only for f in s["files"]]
    failures = 0
    with cf.ThreadPoolExecutor(args.jobs) as ex:
        for path, status in ex.map(lambda e: fetch_one(e, args.pin), entries):
            if status.startswith("FAIL"):
                failures += 1
                print(f"{status}  {path}", file=sys.stderr)
    for e in entries:
        if e.get("extract") and (RAW / e["path"]).exists():
            extract(e)
    if args.pin:
        for s in manifest["sources"]:
            s["total_bytes"] = sum(f.get("size", 0) for f in s["files"])
        MANIFEST.write_text(json.dumps(manifest, indent=1, ensure_ascii=False) + "\n")
    n = len(entries)
    print(f"{n - failures}/{n} files verified under {RAW.relative_to(ROOT)}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
