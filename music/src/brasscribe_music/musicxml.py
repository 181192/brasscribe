"""Quantized parts -> MusicXML via music21.

Notes sharing a start tick within a part become a chord (clipped to the
shortest member); overlaps within a part are cut at the next onset, so every
part is a single voice. Real voice separation belongs to a later stage.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from music21 import chord, clef, instrument, key, meter, note, stream, tempo

from .quantize import TICKS_PER_BEAT, QNote


@dataclass
class PartSpec:
    name: str
    notes: list[QNote]
    clef: str = "treble"  # treble | bass
    extra: dict = field(default_factory=dict)


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
        if i + 1 < len(starts):
            end = min(end, starts[i + 1])
        out.append((s, max(end, s + 1), sorted({q.pitch for q in g}), min(q.confidence for q in g)))
    return out


def build_score(parts: list[PartSpec], beats_per_bar: int, bpm: float, title: str,
                pickup_ticks: int = 0, low_confidence: float = 0.6) -> stream.Score:
    score = stream.Score()
    score.metadata = None
    from music21 import metadata
    score.insert(0, metadata.Metadata(title=title))

    all_pitches = [q.pitch for p in parts for q in p.notes]
    detected_key = None
    # Every part must span the same whole bars; MuseScore crashes on ragged part lengths.
    bar = beats_per_bar * TICKS_PER_BEAT
    last = max((q.end for p in parts for q in p.notes), default=0) - pickup_ticks
    total = -(-max(last, bar) // bar) * bar
    for p in parts:
        part = stream.Part()
        inst = instrument.Instrument()
        inst.partName = p.name
        part.insert(0, inst)
        part.insert(0, clef.BassClef() if p.clef == "bass" else clef.TrebleClef())
        part.insert(0, meter.TimeSignature(f"{beats_per_bar}/4"))
        part.insert(0, tempo.MetronomeMark(number=round(bpm)))
        cursor = 0
        for start, end, pitches, conf in _events(p.notes):
            start -= pickup_ticks
            end -= pickup_ticks
            if start < 0:
                continue
            if start > cursor:
                part.insert(cursor / TICKS_PER_BEAT, note.Rest(quarterLength=(start - cursor) / TICKS_PER_BEAT))
            ql = (end - start) / TICKS_PER_BEAT
            el = note.Note(pitches[0], quarterLength=ql) if len(pitches) == 1 else chord.Chord(pitches, quarterLength=ql)
            if conf < low_confidence:
                el.style.color = "#d0021b"  # flag uncertain notes for review
            part.insert(start / TICKS_PER_BEAT, el)
            cursor = end
        if cursor < total:
            part.insert(cursor / TICKS_PER_BEAT, note.Rest(quarterLength=(total - cursor) / TICKS_PER_BEAT))
        score.insert(0, part)

    if all_pitches:
        probe = stream.Stream([note.Note(p) for p in all_pitches])
        detected_key = probe.analyze("key")
        for part in score.parts:
            part.insert(0, key.KeySignature(detected_key.sharps))
    score = score.makeNotation()
    for n in score.recurse().notes:
        # Spell accidentals in the detected key rather than MIDI defaults.
        if detected_key is not None:
            pitches = n.pitches
            for pch in pitches:
                if pch.accidental is not None and detected_key.sharps < 0 and pch.accidental.name == "sharp":
                    enh = pch.getEnharmonic()
                    pch.step, pch.accidental, pch.octave = enh.step, enh.accidental, enh.octave
    return score


def write_musicxml(score: stream.Score, path: Path) -> Path:
    score.write("musicxml", fp=str(path))
    return path
