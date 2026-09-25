"""Canonical forms used for exact comparison.

MusicXML: the only differences allowed between two files are the ones music21
randomises or stamps per run. Canonicalisation therefore
  - drops comments and whitespace-only text between elements,
  - removes <encoding-date> and <software>,
  - renumbers every `id` / `id`-reference (score-part, part, score-instrument,
    midi-instrument, instrument) in order of first appearance,
and serialises the result as C14N (attribute order normalised, child order kept).
The XML declaration and DOCTYPE lines are compared verbatim.

Composition JSON: compared as parsed JSON with exact float equality, and also
byte for byte (reported separately).
"""

from __future__ import annotations

import json
from pathlib import Path

from lxml import etree

_DROP = {"encoding-date", "software"}


def _header(raw: bytes) -> list[bytes]:
    head = raw.split(b"<score-partwise", 1)[0]
    return [line.strip() for line in head.splitlines() if line.strip()]


def canonical_musicxml(path: Path) -> bytes:
    raw = path.read_bytes()
    parser = etree.XMLParser(remove_comments=True, remove_blank_text=True, resolve_entities=False, load_dtd=False,
                             no_network=True)
    root = etree.fromstring(raw, parser)
    for el in list(root.iter(*_DROP)):
        el.getparent().remove(el)
    ids: dict[str, str] = {}
    counters: dict[str, int] = {}
    for el in root.iter():
        v = el.get("id")
        if v is None:
            continue
        if v not in ids:
            prefix = v[:1] if v[:1] in ("P", "I") else "X"
            counters[prefix] = counters.get(prefix, 0) + 1
            ids[v] = f"{prefix}{counters[prefix]}"
        el.set("id", ids[v])
    for el in root.iter():
        if el.text is not None and not el.text.strip() and len(el):
            el.text = None
        if el.tail is not None and not el.tail.strip():
            el.tail = None
    body = etree.tostring(root, method="c14n")
    return b"\n".join(_header(raw)) + b"\n" + body


def musicxml_equal(a: Path, b: Path) -> tuple[bool, str]:
    ca, cb = canonical_musicxml(a), canonical_musicxml(b)
    if ca == cb:
        return True, ""
    # First differing region, for the report.
    i = next((k for k in range(min(len(ca), len(cb))) if ca[k] != cb[k]), min(len(ca), len(cb)))
    lo = max(0, i - 300)
    return False, f"first diff at byte {i}:\n  ref: {ca[lo:i + 200]!r}\n  rs:  {cb[lo:i + 200]!r}"


def json_equal(a: Path, b: Path) -> tuple[bool, bool, str]:
    """(parsed-equal, byte-equal, detail)."""
    ra, rb = a.read_bytes(), b.read_bytes()
    ja, jb = json.loads(ra), json.loads(rb)
    same = ja == jb
    detail = "" if same else _first_json_diff(ja, jb, "$")
    return same, ra == rb, detail


def _first_json_diff(a, b, path: str) -> str:
    if type(a) is not type(b):
        return f"{path}: type {type(a).__name__} != {type(b).__name__} ({a!r} vs {b!r})"
    if isinstance(a, dict):
        if list(a) != list(b):
            return f"{path}: keys {list(a)} != {list(b)}"
        for k in a:
            if a[k] != b[k]:
                return _first_json_diff(a[k], b[k], f"{path}.{k}")
    elif isinstance(a, list):
        if len(a) != len(b):
            return f"{path}: len {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            if x != y:
                return _first_json_diff(x, y, f"{path}[{i}]")
    return f"{path}: {a!r} != {b!r}"
