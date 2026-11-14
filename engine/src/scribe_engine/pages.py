"""Pages a job reads instead of a recording: pictures of printed music and PDFs.

One page is stored in the uploads folder as the file it is. Several pages are stored as one archive, in
the order they were given, so that a job still has one input file with one checksum: a ZIP without
compression whose members are page-001.<suffix>, page-002.<suffix>, …, written with fixed dates so that
the same pages always make the same archive.

What a file is, is read from its first bytes, never from its name: a page that is not one of the formats
below is refused when it is uploaded, with the format it seems to be (an iPhone's HEIC photo is the one
that is met in practice; the apps send JPEG).

A picture is also refused by what it would take to open it. A few kilobytes of PNG can hold a picture of
hundreds of megapixels, and the recogniser decodes whatever it is given: so a picture's size is read from
its header here, before anything decodes it, and one over MAX_PIXELS is refused, as is a file over
MAX_PAGE_BYTES. A PDF's pages cannot be counted without a PDF library, which the engine does not have: the
adapter counts and renders them, within the same limits (ml/adapters/homr/prepare.py).
"""

from __future__ import annotations

import re
import shutil
import struct
import zipfile
from pathlib import Path
from typing import BinaryIO

THIS = Path(__file__).resolve()
ARCHIVE = ".zip"
PAGE_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".webp", ".pdf"})
INPUT_SUFFIXES = PAGE_SUFFIXES | {ARCHIVE}
MAX_PAGES = 40  # files in one upload, and pages in all once its PDFs are opened
MAX_PAGE_BYTES = 50 * 1024 * 1024  # one file: a phone's largest photo is a fifth of this
MAX_PIXELS = 50_000_000  # one picture, decoded: an A4 page at 600 dpi is 35 million
# What the API answers with, as {"code", "detail"}: 415 for a file that is not a page and for an input that is
# not the kind the job's profile reads, 413 for a page too large to read and for more files than MAX_PAGES.
NOT_A_PAGE = "not_a_page"
WRONG_INPUT = "wrong_input"
PAGE_TOO_LARGE = "page_too_large"
TOO_MANY_PAGES = "too_many_pages"
WRONG_INPUT_DETAIL = ("this profile does not read that kind of file: the sheet profiles read pictures and PDFs of "
                      "printed music, the others a recording")
MEMBER = re.compile(r"page-\d{3}\.(png|jpg|webp|pdf)")


class WrongInput(ValueError):
    """A job's input is not the kind its profile reads: a recording for one that reads pages, or pages for one
    that listens."""


def is_pages(path: Path | str) -> bool:
    """A job's input that is read as pages: one page, or an archive of them."""
    return Path(path).suffix.lower() in INPUT_SUFFIXES


def is_archive(path: Path | str) -> bool:
    return Path(path).suffix.lower() == ARCHIVE


def kind(head: bytes) -> str | None:
    """The suffix of the page format `head` (a file's first bytes) starts, or None when it is none of them."""
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if head.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if head[:4] == b"RIFF" and head[8:12] == b"WEBP":
        return ".webp"
    if head.startswith(b"%PDF-"):
        return ".pdf"
    return None


def seems(head: bytes) -> str:
    """What a refused file seems to be, for the message."""
    if head[4:8] == b"ftyp" and head[8:12] in (b"heic", b"heix", b"hevc", b"mif1", b"msf1", b"avif"):
        return "a HEIC or AVIF picture"
    if head.startswith(b"PK"):
        return "an archive or an office document"
    if head.startswith(b"GIF8"):
        return "a GIF"
    if head[:4] in (b"II*\x00", b"MM\x00*"):
        return "a TIFF picture"
    if head.startswith(b"BM"):
        return "a BMP picture"
    return "not a picture or a PDF"


JPEG_FRAMES = frozenset(range(0xC0, 0xD0)) - {0xC4, 0xC8, 0xCC}  # the markers that start a frame: SOF0 to SOF15


def _jpeg_size(f: BinaryIO) -> tuple[int, int] | None:
    f.seek(2)
    while True:
        marker = f.read(2)
        if len(marker) < 2 or marker[0] != 0xFF:
            return None
        if marker[1] == 0xFF:  # padding before a marker
            f.seek(-1, 1)
            continue
        if marker[1] in (0x01, *range(0xD0, 0xDA)):  # markers without a length
            if marker[1] == 0xD9:
                return None
            continue
        length = f.read(2)
        if len(length) < 2:
            return None
        size = struct.unpack(">H", length)[0]
        if marker[1] in JPEG_FRAMES:
            frame = f.read(5)
            if len(frame) < 5:
                return None
            height, width = struct.unpack(">HH", frame[1:5])
            return width, height
        if marker[1] == 0xDA or size < 2:  # the picture's data, with no frame before it
            return None
        f.seek(size - 2, 1)


def _webp_size(head: bytes) -> tuple[int, int] | None:
    chunk = head[12:16]
    if chunk == b"VP8X" and len(head) >= 30:
        return int.from_bytes(head[24:27], "little") + 1, int.from_bytes(head[27:30], "little") + 1
    if chunk == b"VP8L" and len(head) >= 25 and head[20] == 0x2F:
        bits = int.from_bytes(head[21:25], "little")
        return (bits & 0x3FFF) + 1, ((bits >> 14) & 0x3FFF) + 1
    if chunk == b"VP8 " and len(head) >= 30 and head[23:26] == b"\x9d\x01\x2a":
        return int.from_bytes(head[26:28], "little") & 0x3FFF, int.from_bytes(head[28:30], "little") & 0x3FFF
    return None


def picture_size(path: Path) -> tuple[int, int] | None:
    """(width, height) of the PNG, JPEG or WebP picture in `path`, read from its header alone; None when the
    header does not give one (the file is then no picture the recogniser should be handed)."""
    with path.open("rb") as f:
        head = f.read(32)
        suffix = kind(head)
        if suffix == ".png":
            return struct.unpack(">II", head[16:24]) if head[12:16] == b"IHDR" and len(head) >= 24 else None
        if suffix == ".webp":
            return _webp_size(head)
        if suffix == ".jpg":
            return _jpeg_size(f)
    return None


def too_large(path: Path, suffix: str) -> str | None:
    """Why the page in `path` is too large to read, or None when it is not: more bytes than MAX_PAGE_BYTES, or a
    picture of more pixels than MAX_PIXELS. A picture whose header gives no size is too large to trust."""
    megabytes = path.stat().st_size / (1024 * 1024)
    if path.stat().st_size > MAX_PAGE_BYTES:
        return f"is {megabytes:.0f} MB: a page is at most {MAX_PAGE_BYTES // (1024 * 1024)} MB"
    if suffix == ".pdf":
        return None
    size = picture_size(path)
    if size is None or size[0] <= 0 or size[1] <= 0:
        return "does not say how large it is"
    if size[0] * size[1] > MAX_PIXELS:
        return (f"is {size[0]} by {size[1]} pixels: a page is at most {MAX_PIXELS // 1_000_000} million pixels "
                "(a photo from a phone, or a scan at up to 600 dpi)")
    return None


def pack(files: list[tuple[Path, str]], dst: Path) -> None:
    """The archive of `files` ((path, suffix) in page order) at `dst`: the same files always give the same bytes.
    Each page is copied a block at a time, never held whole."""
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_STORED) as z:
        for i, (path, suffix) in enumerate(files, 1):
            info = zipfile.ZipInfo(f"page-{i:03d}{suffix}", date_time=(1980, 1, 1, 0, 0, 0))
            info.external_attr = 0o644 << 16
            info.file_size = path.stat().st_size
            with path.open("rb") as src, z.open(info, "w") as member:
                shutil.copyfileobj(src, member, 1 << 20)


def unpack(archive: Path, folder: Path) -> int:
    """The pages of `archive` into `folder`, under their own names, a block at a time. ValueError for an archive
    that is not one pack() wrote: nothing but page-NNN members no larger than a page may be is ever written, and
    never outside `folder`."""
    try:
        with zipfile.ZipFile(archive) as z:
            members = z.infolist()
            if not members or len(members) > MAX_PAGES or any(
                    not MEMBER.fullmatch(m.filename) or m.file_size > MAX_PAGE_BYTES or m.compress_type != zipfile.ZIP_STORED
                    for m in members):
                raise ValueError(f"{archive.name} is not an archive of pages")
            for m in members:
                with z.open(m) as src, (folder / m.filename).open("wb") as dst:
                    shutil.copyfileobj(src, dst, 1 << 20)
    except zipfile.BadZipFile as e:
        raise ValueError(f"{archive.name} is not an archive of pages") from e
    return len(members)
