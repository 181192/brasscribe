"""Quantized parts -> MusicXML via music21.

Notes sharing a start tick within a part become a chord (clipped to the
shortest member); overlaps within a part are cut at the next onset, so every
part is a single voice. Real voice separation belongs to a later stage.
"""

from __future__ import annotations

import warnings

from dataclasses import dataclass, field
from pathlib import Path

from music21 import chord, clef, instrument, interval, key, meter, note, pitch, stream, tempo

from .instruments import Instrument as BandInstrument

from .quantize import TICKS_PER_BEAT, QNote
from .spelling import key_of, spell


@dataclass
class PartSpec:
    name: str
    notes: list[QNote]
    clef: str = "treble"  # treble | bass
    instrument: BandInstrument | None = None  # transposing band instrument; None = concert-pitch part
    extra: dict = field(default_factory=dict)


def _m21_instrument(name: str, band: BandInstrument | None) -> instrument.Instrument:
    if band is not None and band.clef == "percussion":
        inst = instrument.UnpitchedPercussion()
        inst.partName = name
        inst.instrumentName = band.name
        inst.partAbbreviation = band.short
        return inst
    inst = instrument.Instrument()
    inst.partName = name
    if band is None:
        return inst
    inst.instrumentName = band.name
    inst.partAbbreviation = band.short
    inst.midiProgram = band.gm_program
    generic = band.diatonic + (1 if band.diatonic >= 0 else -1)
    if band.chromatic:
        inst.transposition = interval.intervalFromGenericAndChromatic(generic, band.chromatic)
    return inst


# General MIDI drum number -> (display step+octave on a 5-line percussion staff, notehead).
DRUM_MAP: dict[int, tuple[str, str]] = {
    35: ("F4", "normal"), 36: ("F4", "normal"),
    37: ("C5", "x"), 38: ("C5", "normal"), 40: ("C5", "normal"),
    41: ("A4", "normal"), 43: ("A4", "normal"), 45: ("D5", "normal"), 47: ("D5", "normal"),
    48: ("E5", "normal"), 50: ("E5", "normal"),
    42: ("G5", "x"), 44: ("D4", "x"), 46: ("G5", "circle-x"),
    49: ("A5", "x"), 52: ("A5", "x"), 55: ("A5", "x"), 57: ("A5", "x"),
    51: ("F5", "x"), 53: ("F5", "diamond"), 59: ("F5", "x"),
}
OTHER_PERCUSSION = ("B5", "x")


def _drum_element(pitches: list[int], ql: float):
    from music21 import percussion

    heads = []
    for p in sorted(set(pitches)):
        disp, head = DRUM_MAP.get(p, OTHER_PERCUSSION)
        u = note.Unpitched(displayName=disp)
        u.notehead = head
        heads.append(u)
    if len(heads) == 1:
        heads[0].quarterLength = ql
        return heads[0]
    return percussion.PercussionChord(heads, quarterLength=ql)


def _notatable_end(start: int, end: int) -> int:
    """Snap an end tick to the nearest 16th (6) or triplet-8th (8) position after start.

    Upstream durations can carry odd tick counts (e.g. a MIDI quarter stored as
    23/24), which music21 can only express as absurd tuplets.
    """
    cands = [g * round(end / g) for g in (6, 8)] + [g * (end // g + 1) for g in (6, 8)]
    cands = [c for c in cands if c > start]
    return min(cands, key=lambda c: (abs(c - end), c))


def _events(notes: list[QNote]) -> list[tuple[int, int, list[int], float]]:
    """Group by start tick into (start, end, pitches, min confidence); make the line non-overlapping."""
    groups: dict[int, list[QNote]] = {}
    for q in notes:
        groups.setdefault(q.start, []).append(q)
    starts = sorted(groups)
    out = []
    for i, s in enumerate(starts):
        g = groups[s]
        end = min(q.end for q in g)
        end = _notatable_end(s, end)
        if i + 1 < len(starts):
            end = min(end, starts[i + 1])
        out.append((s, max(end, s + 1), sorted({q.pitch for q in g}), min(q.confidence for q in g)))
    return out


def build_score(parts: list[PartSpec], beats_per_bar: int, bpm: float, title: str,
                pickup_ticks: int = 0, low_confidence: float = 0.6, key_fifths: int | None = None) -> stream.Score:
    score = stream.Score()
    score.metadata = None
    from music21 import metadata
    md = metadata.Metadata(title=title)
    md.composer = "arr. brasscribe"
    score.insert(0, md)

    # Spell every note from the whole ensemble at concert pitch (ps13), and pick the key.
    def is_drums(p: PartSpec) -> bool:
        return p.instrument is not None and p.instrument.clef == "percussion"

    events = [(pi, ev) for pi, p in enumerate(parts) if not is_drums(p) for ev in _events(p.notes)]
    flat = [(pi, s, e, p) for pi, (s, e, ps, _) in events for p in ps]
    spelled: dict[tuple[int, int, int], pitch.Pitch] = {}
    fifths = 0
    if flat:
        on = [s / TICKS_PER_BEAT for _, s, _, _ in flat]
        du = [(e - s) / TICKS_PER_BEAT for _, s, e, _ in flat]
        ps = [p for *_, p in flat]
        for (pi, s, _, p), (step, alter, octave) in zip(flat, spell(on, du, ps)):
            spelled[(pi, s, p)] = pitch.Pitch(step=step, octave=octave, accidental=alter if alter else None)
        _, fifths = key_of(on, du, ps)
    if key_fifths is not None:
        fifths = key_fifths

    # Every part must span the same whole bars; MuseScore mis-handles ragged part lengths.
    bar = beats_per_bar * TICKS_PER_BEAT
    last = max((q.end for p in parts for q in p.notes), default=0) - pickup_ticks
    total = -(-max(last, bar) // bar) * bar
    for pi, p in enumerate(parts):
        part = stream.Part()
        part.insert(0, _m21_instrument(p.name, p.instrument))
        if is_drums(p):
            part.insert(0, clef.PercussionClef())
        else:
            part.insert(0, clef.BassClef() if p.clef == "bass" else clef.TrebleClef())
            part.insert(0, key.KeySignature(fifths))
        part.insert(0, meter.TimeSignature(f"{beats_per_bar}/4"))
        if pi == 0:
            part.insert(0, tempo.MetronomeMark(number=round(bpm)))
        cursor = 0
        dropped = 0
        for start, end, pitches, conf in _events(p.notes):
            tick = start
            start -= pickup_ticks
            end -= pickup_ticks
            if start < 0:
                dropped += 1
                continue
            if start > cursor:
                part.insert(cursor / TICKS_PER_BEAT, note.Rest(quarterLength=(start - cursor) / TICKS_PER_BEAT))
            ql = (end - start) / TICKS_PER_BEAT
            if is_drums(p):
                el = _drum_element(pitches, ql)
            else:
                sp = [spelled.get((pi, tick, m), pitch.Pitch(midi=m)) for m in pitches]
                el = note.Note(sp[0], quarterLength=ql) if len(sp) == 1 else chord.Chord(sp, quarterLength=ql)
            if conf < low_confidence:
                el.style.color = "#d0021b"  # flag uncertain notes for review
            part.insert(start / TICKS_PER_BEAT, el)
            cursor = end
        if cursor < total:
            part.insert(cursor / TICKS_PER_BEAT, note.Rest(quarterLength=(total - cursor) / TICKS_PER_BEAT))
        if dropped:
            warnings.warn(f"{p.name}: {dropped} note(s) before the first bar were not written")
        score.insert(0, part)
    score = score.makeNotation()
    score.atSoundingPitch = True
    return score


def write_musicxml(score: stream.Score, path: Path, sounds: dict[str, str] | None = None) -> Path:
    """Write written-pitch MusicXML: transposing parts are converted exactly once, here.

    `sounds` maps part name -> <instrument-sound> id. music21 does not write that
    element, and without it MuseScore guesses from the part name (it reads
    "E♭ Bass" as a bass voice).
    """
    written = score.toWrittenPitch(inPlace=False) if any(
        (i.transposition is not None) for i in score.recurse().getElementsByClass(instrument.Instrument)) else score
    written.write("musicxml", fp=str(path))
    if sounds:
        _add_instrument_sounds(path, sounds)
    return path


def _add_instrument_sounds(path: Path, sounds: dict[str, str]) -> None:
    import xml.etree.ElementTree as ET

    raw = path.read_text(encoding="utf-8")
    head, sep, _ = raw.partition("<score-partwise")
    tree = ET.ElementTree(ET.fromstring(raw[len(head):]))
    root = tree.getroot()
    for sp in root.iter("score-part"):
        name = (sp.findtext("part-name") or "").strip()
        sound = sounds.get(name)
        if not sound:
            continue
        for si in sp.iter("score-instrument"):
            if si.find("instrument-sound") is None:
                el = ET.Element("instrument-sound")
                el.text = sound
                # Schema order: instrument-name, instrument-abbreviation?, instrument-sound?
                idx = 1 + (si.find("instrument-abbreviation") is not None)
                si.insert(idx, el)
    path.write_text(head + ET.tostring(root, encoding="unicode"), encoding="utf-8")


def build_band_score(arrangement, comp) -> stream.Score:
    """Arrangement (concert notes per band part) -> transposing score in lineup order."""
    specs = []
    for part in arrangement.lineup.parts:
        notes = [QNote(n.pitch, n.start, n.end, n.onset_s or 0.0, n.offset_s or 0.0, n.confidence)
                 for n in arrangement.parts.get(part.name, [])]
        specs.append(PartSpec(part.name, notes, clef=part.instrument.clef, instrument=part.instrument))
    meter0 = comp.meters[0].beats if comp.meters else 4
    fifths = comp.keys[0].fifths if comp.keys else None
    return build_score(specs, beats_per_bar=meter0, bpm=comp.bpm, title=comp.title, low_confidence=0.7, key_fifths=fifths)


def band_sounds(arrangement) -> dict[str, str]:
    return {p.name: p.instrument.sound for p in arrangement.lineup.parts if p.instrument.sound}
