"""Individual parts from a written score: one MusicXML file per part, with multi-bar rests.

`mscore -P` (export all parts) crashes in MuseScore 4.7 before writing, so
the parts are cut from our own MusicXML instead and rendered one by one.
Per part:
  - only that part's <score-part> and <part>
  - tempo marks and rehearsal letters copied from the top part, so every player sees them
  - runs of two or more empty bars marked as one multi-bar rest
    (<measure-style><multiple-rest>)
  - a part with no notes at all is written as a one-line "Tacet" part
  - a footer where one is given (the source line of an arranged part), as a page-one `rights`
    credit, which MuseScore prints at the foot of the page
"""

from __future__ import annotations

import copy
import re
import xml.etree.ElementTree as ET
from pathlib import Path

MIN_MULTI_REST = 2


def _empty(measure: ET.Element) -> bool:
    return not any(n.find("rest") is None for n in measure.iter("note"))


def _tempo_directions(part: ET.Element) -> dict[str, list[ET.Element]]:
    """Tempo marks and rehearsal letters of a part, per measure number."""
    out: dict[str, list[ET.Element]] = {}
    for m in part.iter("measure"):
        for d in m.findall("direction"):
            sound = d.find("sound")
            if d.find("direction-type/metronome") is not None or d.find("direction-type/rehearsal") is not None \
                    or (sound is not None and sound.get("tempo")):
                out.setdefault(m.get("number"), []).append(d)
    return out


STYLE = Path(__file__).with_name("parts.mss")  # MuseScore style for rendering parts: multi-bar rests from 2 bars


def _breaks_rest(measure: ET.Element) -> bool:
    """A multi-bar rest must not swallow a rehearsal letter, tempo or key change."""
    return measure.find("direction/direction-type/rehearsal") is not None or \
        measure.find("direction/direction-type/metronome") is not None or measure.find("attributes/key") is not None


def _mark_multi_rests(part: ET.Element) -> int:
    measures = part.findall("measure")
    runs, i = 0, 0
    while i < len(measures):
        if not _empty(measures[i]):
            i += 1
            continue
        j = i
        while j + 1 < len(measures) and _empty(measures[j + 1]) and measures[j + 1].find("attributes/time") is None \
                and not _breaks_rest(measures[j + 1]):
            j += 1
        n = j - i + 1
        if n >= MIN_MULTI_REST:
            m = measures[i]
            attrs = m.find("attributes")
            if attrs is None:
                attrs = ET.Element("attributes")
                m.insert(0, attrs)
            style = ET.SubElement(attrs, "measure-style")
            ET.SubElement(style, "multiple-rest").text = str(n)
            runs += 1
        i = j + 1
    return runs


def _add_footer(doc: ET.Element, text: str) -> None:
    """A page-one footer credit, placed before the part list (the Rust core writes the same)."""
    credit = ET.Element("credit", {"page": "1"})
    ET.SubElement(credit, "credit-type").text = "rights"
    ET.SubElement(credit, "credit-words", {"justify": "center", "valign": "bottom", "font-size": "8"}).text = text
    children = list(doc)
    at = next((i for i, c in enumerate(children) if c.tag == "part-list"), len(children))
    doc.insert(at, credit)


def split_parts(xml: Path, out_dir: Path, footers: dict[str, str] | None = None) -> list[Path]:
    """Write <out_dir>/<nn>-<part name>.musicxml for every part; returns the paths in score order.

    `footers`: {part name: text} printed at the foot of that part's first page (arranger.part_footers)."""
    raw = xml.read_text(encoding="utf-8")
    head, _, _ = raw.partition("<score-partwise")
    root = ET.fromstring(raw[len(head):])
    parts = root.findall("part")
    part_list = root.find("part-list")
    score_parts = {sp.get("id"): sp for sp in part_list.findall("score-part")}
    tempos = _tempo_directions(parts[0]) if parts else {}
    out_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for k, part in enumerate(parts, start=1):
        pid = part.get("id")
        name = (score_parts[pid].findtext("part-name") or pid).strip()
        doc = copy.deepcopy(root)
        for p in doc.findall("part"):
            if p.get("id") != pid:
                doc.remove(p)
        pl = doc.find("part-list")
        for child in list(pl):
            if child.tag != "score-part" or child.get("id") != pid:
                pl.remove(child)
        mine = doc.find("part")
        if k > 1:
            for m in mine.findall("measure"):
                for d in tempos.get(m.get("number"), []):
                    m.insert(0 if m.find("attributes") is None else 1, copy.deepcopy(d))
        tacet = all(_empty(m) for m in mine.findall("measure"))
        label = name + (" (Tacet)" if tacet else "")
        for el in (doc.find("work/work-title"), doc.find("movement-title")):
            if el is not None:
                el.text = f"{el.text} — {label}" if el.text else label
        _mark_multi_rests(mine)
        if footers and name in footers:
            _add_footer(doc, footers[name])
        slug = re.sub(r"[^A-Za-z0-9]+", "-", name.replace("♭", "b").replace("♯", "#")).strip("-")
        path = out_dir / f"{k:02d}-{slug}.musicxml"
        path.write_text(head + ET.tostring(doc, encoding="unicode"), encoding="utf-8")
        written.append(path)
    return written
