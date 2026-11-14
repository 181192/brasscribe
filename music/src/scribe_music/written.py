"""A written score read back from MusicXML: the notes of every staff, bar by bar.

The other modules here write MusicXML from notes that were heard. This one reads MusicXML that was
written by something else (a recogniser of printed music, a notation program) into plain notes: what
each staff plays in each bar, where in the bar, and for how long. It reads the part-wise format only,
which is what every such program writes, and it keeps what a staff shows (the written pitch); a part's
transposition is kept beside it, for the caller to apply.

Positions and lengths are in quarter notes, as fractions, so a triplet is exact.
"""

from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass, field
from fractions import Fraction
from pathlib import Path
from xml.etree import ElementTree as ET

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


@dataclass(frozen=True)
class WrittenNote:
    pitch: int  # MIDI pitch as written on the staff (the part's transposition not applied)
    start: Fraction  # quarter notes from the start of the bar
    dur: Fraction  # quarter notes
    tied_from_previous: bool = False  # the note continues one of the same pitch before it
    string: int | None = None  # a tab staff's string (1 = the highest) and fret, when it has them
    fret: int | None = None


@dataclass
class Bar:
    length: Fraction  # quarter notes: what this staff's bar holds (its notes and rests), not what its meter says
    notes: list[WrittenNote] = field(default_factory=list)
    beats: int | None = None  # the meter in force, when the score gives one
    beat_unit: int | None = None
    fifths: int | None = None  # the key signature in force


@dataclass
class Staff:
    part: str  # the part's name in the score ("" when it has none)
    number: int  # the staff within its part, from 1
    clef: str  # "G", "F", "C", "TAB", "percussion"; the first clef the staff shows
    transpose: int  # semitones from written to sounding pitch (-2 for a B flat cornet)
    clef_octave: int = 0  # the clef's octave mark (-1: the small 8 under a guitar's clef); its pitches already include it
    bars: list[Bar] = field(default_factory=list)

    @property
    def is_tab(self) -> bool:
        return self.clef == "TAB"

    def notes(self) -> int:
        return sum(len(b.notes) for b in self.bars)


@dataclass
class WrittenScore:
    title: str
    staves: list[Staff]

    @property
    def bars(self) -> int:
        return max((len(s.bars) for s in self.staves), default=0)


def _root(path: Path) -> ET.Element:
    data = Path(path).read_bytes()
    if data[:2] == b"PK":  # compressed MusicXML: the score is the first file that is not the container's own
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            name = next(n for n in z.namelist() if not n.startswith("META-INF") and n.endswith((".xml", ".musicxml")))
            data = z.read(name)
    return ET.fromstring(data)


def _int(el: ET.Element | None, default: int = 0) -> int:
    try:
        return int(float(el.text)) if el is not None and el.text else default
    except ValueError:
        return default


def _pitch(el: ET.Element) -> int | None:
    step = (el.findtext("step") or "").strip().upper()
    if step not in STEPS:
        return None
    return 12 * (_int(el.find("octave"), 4) + 1) + STEPS[step] + _int(el.find("alter"))


def read(path: Path) -> WrittenScore:
    """The score in `path` (MusicXML, plain or compressed). ValueError when it is not a part-wise score."""
    try:
        root = _root(path)
    except (ET.ParseError, zipfile.BadZipFile, StopIteration) as e:
        raise ValueError(f"{Path(path).name} is not MusicXML: {e}") from e
    if root.tag != "score-partwise":
        raise ValueError(f"{Path(path).name} is not a part-wise MusicXML score (it is {root.tag})")
    title = (root.findtext("work/work-title") or root.findtext("movement-title") or "").strip()
    names = {sp.get("id"): (sp.findtext("part-name") or "").strip() for sp in root.iterfind("part-list/score-part")}
    staves: list[Staff] = []
    for part in root.iterfind("part"):
        staves += _part(part, names.get(part.get("id"), ""))
    return WrittenScore(title, staves)


def _part(part: ET.Element, name: str) -> list[Staff]:
    divisions = 1
    transpose = 0
    clefs: dict[int, str] = {}
    octaves: dict[int, int] = {}
    meter: tuple[int | None, int | None] = (None, None)
    fifths: int | None = None
    bars: dict[int, list[Bar]] = {}
    count = 0
    for measure in part.iterfind("measure"):
        count += 1
        now = Fraction(0)
        last_start = Fraction(0)
        ends: dict[int, Fraction] = {}  # per staff: where its last note or rest ends
        found: dict[int, list[WrittenNote]] = {}
        for el in measure:
            if el.tag == "attributes":
                divisions = _int(el.find("divisions"), divisions) or divisions
                if el.find("transpose") is not None:
                    transpose = _int(el.find("transpose/chromatic")) + 12 * _int(el.find("transpose/octave-change"))
                if el.find("time/beats") is not None:
                    meter = (_int(el.find("time/beats")) or None, _int(el.find("time/beat-type")) or None)
                if el.find("key/fifths") is not None:
                    fifths = _int(el.find("key/fifths"))
                for clef in el.iterfind("clef"):
                    if int(clef.get("number") or 1) not in clefs:
                        clefs[int(clef.get("number") or 1)] = (clef.findtext("sign") or "G").strip()
                        octaves[int(clef.get("number") or 1)] = _int(clef.find("clef-octave-change"))
            elif el.tag in ("backup", "forward"):
                step = Fraction(_int(el.find("duration")), divisions)
                now = max(Fraction(0), now - step) if el.tag == "backup" else now + step
            elif el.tag == "note":
                if el.find("grace") is not None or el.find("cue") is not None:
                    continue
                dur = Fraction(_int(el.find("duration")), divisions)
                start = last_start if el.find("chord") is not None else now
                staff = _int(el.find("staff"), 1)
                pitch = el.find("pitch")
                if pitch is not None and _pitch(pitch) is not None:
                    tied = any(t.get("type") == "stop" for t in el.iterfind("tie"))
                    technical = el.find("notations/technical")
                    string = _int(technical.find("string")) if technical is not None and technical.find("string") is not None else None
                    fret = _int(technical.find("fret")) if technical is not None and technical.find("fret") is not None else None
                    found.setdefault(staff, []).append(WrittenNote(_pitch(pitch), start, dur, tied, string, fret))
                else:
                    found.setdefault(staff, [])
                ends[staff] = max(ends.get(staff, Fraction(0)), start + dur)
                if el.find("chord") is None:
                    last_start = now
                    now += dur
        for staff in set(found) | set(clefs) | set(bars) | {1}:
            line = bars.setdefault(staff, [])
            while len(line) < count - 1:  # a staff that first shows later has empty bars before it
                line.append(Bar(Fraction(0)))
            line.append(Bar(ends.get(staff, Fraction(0)), sorted(found.get(staff, []), key=lambda n: (n.start, n.pitch)),
                            meter[0], meter[1], fifths))
    return [Staff(name, number, clefs.get(number, "G"), transpose, octaves.get(number, 0), bars[number]) for number in sorted(bars)]
