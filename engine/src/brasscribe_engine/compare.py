"""Compare a run's score output with a reference (the golden output).

composition.json must be byte-identical. MusicXML is compared after
canonicalisation: music21 writes random part/instrument ids and the encoding
date, so those are replaced by stable values; everything else, including every
note, must match byte for byte. The result lists each part with its note count
and whether it is identical.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from pathlib import Path

_ID = re.compile(r'"([PI][0-9a-f]{32})(-\d+)?"')
_DATE = re.compile(r"<encoding-date>[^<]*</encoding-date>")
_PART = re.compile(r'<part id="([^"]+)">(.*?)</part>', re.S)
_SCORE_PART = re.compile(r'<score-part id="([^"]+)">.*?<part-name>([^<]*)</part-name>', re.S)
_NOTE = re.compile(r"<note\b.*?</note>", re.S)


def stable_ids(text: str) -> str:
    """Replace music21's random part/instrument ids (P<32 hex>, I<32 hex>) by P1, P2 ..., I1, I2 ... in order.

    Per-drum instrument ids carry a -<GM note> suffix, which is kept.
    """
    ids: dict[str, str] = {}

    def sub(m: re.Match) -> str:
        raw = m.group(1)
        if raw not in ids:
            ids[raw] = f"{raw[0]}{sum(1 for k in ids if k[0] == raw[0]) + 1}"
        return f'"{ids[raw]}{m.group(2) or ""}"'

    return _ID.sub(sub, text)


def canonical_musicxml(text: str) -> str:
    return _DATE.sub("<encoding-date/>", stable_ids(text))


def parts(text: str) -> list[tuple[str, str, int]]:
    """(part name, canonical body, sounding-note count) per part, in score order."""
    text = canonical_musicxml(text)
    names = dict(_SCORE_PART.findall(text))
    out = []
    for pid, body in _PART.findall(text):
        notes = sum(1 for n in _NOTE.findall(body) if "<rest" not in n)
        out.append((names.get(pid, pid), body, notes))
    return out


@dataclass
class PartDiff:
    name: str
    notes: int
    reference_notes: int
    identical: bool


@dataclass
class Comparison:
    composition_identical: bool
    musicxml_identical: bool
    parts: list[PartDiff] = field(default_factory=list)
    extra_files: dict[str, bool] = field(default_factory=dict)  # other score outputs the reference has: identical?

    @property
    def parts_identical(self) -> int:
        return sum(p.identical for p in self.parts)

    @property
    def notes_identical(self) -> int:
        return sum(p.notes for p in self.parts if p.identical)

    @property
    def ok(self) -> bool:
        return self.composition_identical and self.musicxml_identical and all(self.extra_files.values())

    def to_dict(self) -> dict:
        return {**asdict(self), "ok": self.ok, "parts_identical": self.parts_identical, "parts_total": len(self.parts),
                "notes_identical": self.notes_identical, "notes_total": sum(p.reference_notes for p in self.parts)}

    def report(self) -> str:
        lines = [f"composition.json  {'identical' if self.composition_identical else 'DIFFERENT'}",
                 f"MusicXML          {'identical' if self.musicxml_identical else 'DIFFERENT'} (ids and date canonicalised)"]
        for p in self.parts:
            lines.append(f"  {p.name:18s} notes={p.notes:5d} ref={p.reference_notes:5d} {'OK' if p.identical else 'DIFF'}")
        for name, same in self.extra_files.items():
            lines.append(f"{name:40s} {'identical' if same else 'DIFFERENT'}")
        lines.append(f"parts identical {self.parts_identical}/{len(self.parts)}, notes in identical parts "
                     f"{self.notes_identical}/{sum(p.reference_notes for p in self.parts)}")
        return "\n".join(lines)


def compare(candidate: Path, reference: Path) -> Comparison:
    candidate, reference = Path(candidate), Path(reference)
    comp_same = (candidate / "composition.json").read_bytes() == (reference / "composition.json").read_bytes()
    a = (candidate / "brass-band.musicxml").read_text()
    b = (reference / "brass-band.musicxml").read_text()
    xml_same = canonical_musicxml(a) == canonical_musicxml(b)
    pa, pb = parts(a), parts(b)
    diffs = []
    for i, (name, body, n) in enumerate(pb):
        other = pa[i] if i < len(pa) else None
        diffs.append(PartDiff(name, other[2] if other else 0, n, bool(other and other[0] == name and other[1] == body)))
    for name, _, n in pa[len(pb):]:
        diffs.append(PartDiff(name, n, 0, False))
    extra = {}
    ref_parts = sorted((reference / "parts").glob("*.musicxml")) if (reference / "parts").is_dir() else []
    for f in ref_parts:
        mine = candidate / "parts" / f.name
        extra[f"parts/{f.name}"] = mine.exists() and canonical_musicxml(mine.read_text()) == canonical_musicxml(f.read_text())
    if (reference / "separation-check.json").exists():
        mine = candidate / "separation-check.json"
        extra["separation-check.json"] = mine.exists() and mine.read_bytes() == (reference / "separation-check.json").read_bytes()
    return Comparison(comp_same, xml_same, diffs, extra)
