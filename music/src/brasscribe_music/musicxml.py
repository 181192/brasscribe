"""Quantized parts -> MusicXML via music21.

Notes sharing a start tick within a part become a chord (clipped to the
shortest member); overlaps within a part are cut at the next onset, so every
part is a single voice. Real voice separation belongs to a later stage.
"""

from __future__ import annotations

import copy
import warnings

from dataclasses import dataclass, field
from pathlib import Path

from music21 import articulations, chord, clef, dynamics, expressions, instrument, interval, key, meter, note, pitch, stream, tempo
from music21 import bar as m21bar

from .instruments import Instrument as BandInstrument

from .quantize import TICKS_PER_BEAT, QNote
from .rhythm_spelling import pieces as _pieces
from .spelling import key_of, spell


@dataclass
class PartSpec:
    name: str
    notes: list[QNote]
    clef: str = "treble"  # treble | bass
    instrument: BandInstrument | None = None  # transposing band instrument; None = concert-pitch part
    extra: dict = field(default_factory=dict)
    abbreviation: str | None = None  # staff label after the first system (default: the instrument's)
    dynamics: list[tuple[int, str]] = field(default_factory=list)  # (tick, marking) changes of this part's layer


def _m21_instrument(name: str, band: BandInstrument | None, abbreviation: str | None = None) -> instrument.Instrument:
    if band is not None and band.clef == "percussion":
        inst = instrument.UnpitchedPercussion()
        inst.partName = name
        inst.instrumentName = band.name
        inst.partAbbreviation = abbreviation or band.short
        return inst
    inst = instrument.Instrument()
    inst.partName = name
    if band is None:
        return inst
    inst.instrumentName = band.name
    inst.partAbbreviation = abbreviation or band.short
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


def _events(notes: list[QNote]) -> list[tuple[int, int, list[int], float, set[str]]]:
    """Group by start tick into (start, end, pitches, min confidence, articulations); make the line non-overlapping."""
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
        arts = {str(getattr(a, "value", a)) for q in g for a in q.articulations}
        out.append((s, max(end, s + 1), sorted({q.pitch for q in g}), min(q.confidence for q in g), arts))
    return out


@dataclass
class FreeSpan:
    """A free-time passage for the score: [start, end) ticks, notated at `bpm`."""
    start: int
    end: int
    bpm: float
    label: str = "ad lib."


# Uncertainty encoding (docs/accessibility/visual-design-tokens.md §2): colour plus a "?" above the
# note, boxed below VERY_UNCERTAIN, so it survives black-and-white print.
UNCERTAIN_COLOUR = "#0063A6"
VERY_UNCERTAIN_COLOUR = "#B04A00"
VERY_UNCERTAIN = 0.4


def _uncertainty_mark(very: bool) -> expressions.TextExpression:
    mark = expressions.TextExpression("?")
    mark.placement = "above"
    if very:
        mark.style.enclosure = "rectangle"
    return mark


def _tie(el, i: int, n: int) -> None:
    from music21 import tie
    if n > 1:
        el.tie = tie.Tie("start" if i == 0 else "stop" if i == n - 1 else "continue")


RESTATE_AFTER_BARS = 2  # a part re-entering after this many empty bars gets its dynamic again


def _place_dynamics(part: stream.Part, spec: "PartSpec", pickup_ticks: int, bar: int) -> None:
    """Put the layer's dynamics on this part's notes: at the first note at or after each change,
    and again when the part re-enters after a rest of RESTATE_AFTER_BARS bars."""
    if not spec.dynamics or not spec.notes:
        return
    starts = sorted({q.start for q in spec.notes})
    ends = {}
    for q in spec.notes:
        ends[q.start] = max(ends.get(q.start, q.start), q.end)
    changes = sorted(spec.dynamics)

    def mark_at(tick: int) -> str | None:
        m = None
        for t, mk in changes:
            if t <= tick:
                m = mk
        return m

    placed: dict[int, str] = {}
    for i, (t, mk) in enumerate(changes):
        nxt = changes[i + 1][0] if i + 1 < len(changes) else None
        first = next((s for s in starts if s >= t and (nxt is None or s < nxt)), None)
        if first is not None:
            placed[first] = mk
    if starts[0] not in placed:  # the first note always carries a dynamic
        placed[starts[0]] = mark_at(starts[0]) or changes[0][1]
    prev_end = None
    for s in starts:
        if prev_end is not None and s - prev_end >= RESTATE_AFTER_BARS * bar and s not in placed:
            m = mark_at(s)
            if m:
                placed[s] = m
        prev_end = max(prev_end or 0, ends[s])
    for s in sorted(placed):
        if s - pickup_ticks >= 0:
            part.insert((s - pickup_ticks) / TICKS_PER_BEAT, dynamics.Dynamic(placed[s]))


def _articulate(el, arts: set[str]) -> None:
    if "staccato" in arts:
        el.articulations.append(articulations.Staccato())
    if "fermata" in arts:
        el.expressions.append(expressions.Fermata())


def _mark_free_spans(part: stream.Part, spans: list[FreeSpan], pickup_ticks: int, total: int, strict_bpm: float,
                     with_tempo: bool) -> None:
    """Direction text and tempo at each free span's start and end ("a tempo")."""
    for sp in spans:
        a, b = sp.start - pickup_ticks, sp.end - pickup_ticks
        if a >= 0:
            part.insert(a / TICKS_PER_BEAT, expressions.TextExpression(sp.label))
            if with_tempo:
                part.insert(a / TICKS_PER_BEAT, tempo.MetronomeMark(number=round(sp.bpm)))
        if 0 <= b < total:
            part.insert(b / TICKS_PER_BEAT, expressions.TextExpression("a tempo"))
            if with_tempo:
                part.insert(b / TICKS_PER_BEAT, tempo.MetronomeMark(number=round(strict_bpm)))


def _dash_free_barlines(score: stream.Score, spans: list[FreeSpan], pickup_ticks: int) -> None:
    """Dashed bar lines inside free spans: the bars there only group the proportional notation."""
    for part in score.parts:
        for m in part.getElementsByClass(stream.Measure):
            end = round((m.offset + m.duration.quarterLength) * TICKS_PER_BEAT) + pickup_ticks
            if any(sp.start < end < sp.end for sp in spans):
                m.rightBarline = m21bar.Barline("dashed")


def build_score(parts: list[PartSpec], beats_per_bar: int, bpm: float, title: str,
                pickup_ticks: int = 0, low_confidence: float = 0.6, key_fifths: int | None = None,
                key_changes: list[tuple[int, int]] | None = None,
                rehearsal: list[tuple[int, str]] | None = None,
                free_spans: list[FreeSpan] | None = None) -> stream.Score:
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
    flat = [(pi, s, e, p) for pi, (s, e, ps, _, _) in events for p in ps]
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
        part.insert(0, _m21_instrument(p.name, p.instrument, p.abbreviation))
        if is_drums(p):
            part.insert(0, clef.PercussionClef())
        else:
            part.insert(0, clef.BassClef() if p.clef == "bass" else clef.TrebleClef())
            part.insert(0, key.KeySignature(fifths))
            for tick, f in key_changes or []:
                if tick - pickup_ticks > 0:
                    part.insert((tick - pickup_ticks) / TICKS_PER_BEAT, key.KeySignature(f))
        part.insert(0, meter.TimeSignature(f"{beats_per_bar}/4"))
        spans = free_spans or []
        opens_free = any(sp.start - pickup_ticks == 0 for sp in spans)
        if pi == 0 and not opens_free:
            part.insert(0, tempo.MetronomeMark(number=round(bpm)))
        _mark_free_spans(part, spans, pickup_ticks, total, bpm, with_tempo=pi == 0)
        if pi == 0:  # system text: on the top staff of the score; parts.split_parts copies it to every part
            for tick, label in rehearsal or []:
                if 0 <= tick - pickup_ticks < total:
                    part.insert((tick - pickup_ticks) / TICKS_PER_BEAT, expressions.RehearsalMark(label))
        _place_dynamics(part, p, pickup_ticks, bar)
        cursor = 0
        dropped = 0

        def rest(a: int, b: int) -> None:
            for x, y in _pieces(a, b, bar):
                part.insert(x / TICKS_PER_BEAT, note.Rest(quarterLength=(y - x) / TICKS_PER_BEAT))

        for start, end, pitches, conf, arts in _events(p.notes):
            tick = start
            start -= pickup_ticks
            end -= pickup_ticks
            if start < 0:
                dropped += 1
                continue
            if start > cursor:
                rest(cursor, start)
            segs = _pieces(start, end, bar)
            if is_drums(p):
                # A drum hit has no meaningful length: keep its first readable value and rest after it.
                segs = segs[:1]
                end = segs[0][1]
            for i, (a, b) in enumerate(segs):
                ql = (b - a) / TICKS_PER_BEAT
                if is_drums(p):
                    el = _drum_element(pitches, ql)
                else:
                    # A fresh Pitch per tied piece: transposing to written pitch works in place.
                    sp = [copy.deepcopy(spelled.get((pi, tick, m), pitch.Pitch(midi=m))) for m in pitches]
                    el = note.Note(sp[0], quarterLength=ql) if len(sp) == 1 else chord.Chord(sp, quarterLength=ql)
                    _tie(el, i, len(segs))
                    # Staccato on the attack, fermata on the held end.
                    _articulate(el, {x for x in arts if (x == "staccato" and i == 0) or (x == "fermata" and i == len(segs) - 1)})
                if conf < low_confidence and i == 0:
                    # Colour and "?" on the attack; tied continuations stay plain.
                    el.style.color = VERY_UNCERTAIN_COLOUR if conf < VERY_UNCERTAIN else UNCERTAIN_COLOUR
                    if not is_drums(p):
                        part.insert(a / TICKS_PER_BEAT, _uncertainty_mark(conf < VERY_UNCERTAIN))
                part.insert(a / TICKS_PER_BEAT, el)
            cursor = end
        if cursor < total:
            rest(cursor, total)
        if dropped:
            warnings.warn(f"{p.name}: {dropped} note(s) before the first bar were not written")
        score.insert(0, part)
    score = score.makeNotation()
    if free_spans:
        _dash_free_barlines(score, free_spans, pickup_ticks)
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
    _plain_spellings(written)
    written.write("musicxml", fp=str(path))
    if sounds:
        _add_instrument_sounds(path, sounds)
    return path


AWKWARD = {("E", 1), ("B", 1), ("F", -1), ("C", -1)}
_SHARP_NAMES = ["C", "C#", "D", "E-", "E", "F", "F#", "G", "A-", "A", "B-", "B"]
_FLAT_NAMES = ["C", "D-", "D", "E-", "E", "F", "G-", "G", "A-", "A", "B-", "B"]


def _plain_spellings(score: stream.Score) -> None:
    """Respell written E♯, B♯, F♭, C♭ and double accidentals as the plain enharmonic.

    Spelling runs at concert pitch; transposing a part can turn a sensible
    concert name into F𝄪 or E♯ on the page. Flats stay flats and sharps sharps.
    """
    for p in (x for el in score.recurse().notes for x in getattr(el, "pitches", ())):
        alter = int(p.accidental.alter) if p.accidental is not None else 0
        if abs(alter) >= 2 or (p.step, alter) in AWKWARD:
            midi = p.midi
            name = (_FLAT_NAMES if alter < 0 else _SHARP_NAMES)[midi % 12]
            q = pitch.Pitch(name)
            q.octave = midi // 12 - 1
            q.octave += (midi - q.midi) // 12
            p.step, p.accidental, p.octave = q.step, q.accidental, q.octave


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
    from .arranger import layer_of_part

    specs = []
    for part in arrangement.lineup.parts:
        notes = [QNote(n.pitch, n.start, n.end, n.onset_s or 0.0, n.offset_s or 0.0, n.confidence,
                       tuple(a.value for a in n.articulations))
                 for n in arrangement.parts.get(part.name, [])]
        layer = layer_of_part(part.name)
        dyn = [(d.tick, d.mark) for d in getattr(comp, "dynamics", []) if d.layer == layer]
        specs.append(PartSpec(part.name, notes, clef=part.instrument.clef, instrument=part.instrument,
                              abbreviation=part.abbreviation, dynamics=dyn))
    meter0 = comp.meters[0].beats if comp.meters else 4
    fifths = comp.keys[0].fifths if comp.keys else None
    changes = [(k.tick, k.fifths) for k in comp.keys[1:]]
    spans = [FreeSpan(r.start, r.end, r.tempo_bpm, r.label) for r in comp.free_regions]
    return build_score(specs, beats_per_bar=meter0, bpm=comp.bpm, title=comp.title, low_confidence=0.7, key_fifths=fifths, key_changes=changes,
                       rehearsal=[(x.tick, x.label) for x in getattr(comp, "sections", [])],
                       free_spans=spans)


def band_sounds(arrangement) -> dict[str, str]:
    return {p.name: p.instrument.sound for p in arrangement.lineup.parts if p.instrument.sound}
