"""Braille music (BRF) from the arranged MusicXML, through music21's braille translator.

music21 writes Unicode braille cells (U+2800-U+283F); a .brf file is the same cells in North
American Braille ASCII, the encoding embossers and braille displays read. Lines are at most 40
cells, CRLF-terminated, with a form feed after every 25 lines (one embossed page). Title and heading lines
longer than a line are wrapped at word boundaries, runover lines indented two cells.

music21 only transcribes plain text, so titles and part names are reduced to ASCII first. Where
music21 cannot place a text direction (e.g. an "ad lib." above a note) the score is translated
again without text directions, and the result says so.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

# North American Braille ASCII, indexed by the dot pattern (bit 0 = dot 1 ... bit 5 = dot 6).
BRF_ASCII = " A1B'K2L@CIF/MSP\"E3H9O6R^DJG>NTQ,*5<-U8V.%[$+X!&;:4\\0Z7(_?W]#Y)="
LINE_CELLS = 40
PAGE_LINES = 25

_TEXT = str.maketrans({"—": "-", "–": "-", "♭": "b", "♯": "#", "♮": "", "&": "and", "’": "'", "é": "e", "å": "a",
                       "ø": "o", "æ": "ae", "Å": "A", "Ø": "O", "Æ": "AE"})


def ascii_text(t: str | None) -> str:
    return "".join(c for c in (t or "").translate(_TEXT) if c.isascii())


def unicode_to_brf(text: str) -> str:
    out = []
    for ch in text:
        code = ord(ch)
        if 0x2800 <= code <= 0x283F:
            out.append(BRF_ASCII[code - 0x2800])
        elif 0x2840 <= code <= 0x28FF:  # 8-dot cells: drop dots 7 and 8
            out.append(BRF_ASCII[(code - 0x2800) & 0x3F])
        elif ch in "\n\r\f":
            out.append(ch)
        elif ch == " ":
            out.append(" ")
        else:
            raise ValueError(f"not a braille cell: {ch!r}")
    return "".join(out)


def brf_to_unicode(brf: str) -> str:
    table = {c: chr(0x2800 + i) for i, c in enumerate(BRF_ASCII)}
    table.update({c.lower(): chr(0x2800 + i) for i, c in enumerate(BRF_ASCII) if c.isalpha()})
    return "".join(table.get(c, c) for c in brf.replace("\r\n", "\n").replace("\f", ""))


RUNOVER_INDENT = 2  # continuation lines of a wrapped title or heading start in cell 3


def wrap_line(line: str, width: int = LINE_CELLS, indent: int = RUNOVER_INDENT) -> list[str]:
    """Split a line longer than the page width at word boundaries (blank cells).

    music21 wraps the music itself but not the title and heading lines. As in braille title
    formatting, a runover line is indented; a word longer than the line is split where it must be."""
    line = line.rstrip()
    if len(line) <= width:
        return [line]
    lead = len(line) - len(line.lstrip(" "))
    words = line.split()
    out, cur, first = [], " " * lead, True
    for w in words:
        prefix = "" if cur.strip() == "" else " "
        if len(cur) + len(prefix) + len(w) <= width:
            cur += prefix + w
            continue
        if cur.strip():
            out.append(cur)
            first = False
        cur = " " * indent
        while len(cur) + len(w) > width:  # a single word wider than the line
            room = width - len(cur)
            out.append(cur + w[:room])
            w = w[room:]
        cur += w
    if cur.strip():
        out.append(cur)
    return out


def paginate(brf: str) -> str:
    lines = [part for ln in brf.replace("\r\n", "\n").split("\n") for part in wrap_line(ln)]
    while lines and not lines[-1]:
        lines.pop()
    pages = [lines[i:i + PAGE_LINES] for i in range(0, len(lines), PAGE_LINES)]
    return "\f".join("".join(ln + "\r\n" for ln in page) for page in pages)


@dataclass
class BrailleResult:
    brf: str
    unicode: str
    text_directions_dropped: bool


def _prepare(score) -> None:
    md = score.metadata
    if md is not None:
        if (md.movementName or "").lower().endswith((".musicxml", ".xml", ".mxl")):
            md.movementName = None  # music21 fills in the file name when the score has none
        for f in ("title", "movementName", "composer"):
            if getattr(md, f, None):
                setattr(md, f, ascii_text(getattr(md, f)))
    for part in getattr(score, "parts", []):
        part.partName = ascii_text(part.partName)
        part.partAbbreviation = ascii_text(part.partAbbreviation)


def _drop_text_directions(score) -> None:
    from music21 import expressions

    for el in list(score.recurse().getElementsByClass((expressions.TextExpression, expressions.RehearsalMark))):
        el.activeSite.remove(el)


def translate(musicxml: Path) -> BrailleResult:
    from music21 import converter
    from music21.braille import translate as bt
    from music21.braille.basic import BrailleBasicException
    from music21.braille.text import BrailleTextException

    score = converter.parse(str(musicxml))
    _prepare(score)
    dropped = False
    try:
        cells = bt.objectToBraille(score, maxLineLength=LINE_CELLS)
    except (BrailleTextException, BrailleBasicException):
        score = converter.parse(str(musicxml))
        _prepare(score)
        _drop_text_directions(score)
        cells = bt.objectToBraille(score, maxLineLength=LINE_CELLS)
        dropped = True
    return BrailleResult(paginate(unicode_to_brf(cells)), cells, dropped)
