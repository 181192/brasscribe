"""Minimal deterministic brass-band arranger.

Reads a Composition (concert pitch, voices tagged by role) and writes concert
notes per band part:
  melody  -> Solo Cornet (octave chosen per phrase to sit in its comfortable range)
  bass    -> E♭ Bass (lowest comfortable octave), B♭ Bass an octave lower where comfortable
  harmony -> inner parts, voiced per harmony slot from the chord tones sounding
             at that moment: inside each part's range, under the melody, over
             the bass, no crossing, least movement from the previous chord.
Hard limits come from instruments.py and are never violated; anything that
cannot be placed is left out and reported instead.
"""

from __future__ import annotations

from dataclasses import dataclass, field, replace

from .instruments import MINIMAL_BAND, Lineup, Part
from .score_model import Composition, Note, VoiceRole

PHRASE_GAP_TICKS = 48  # a rest of two beats or more starts a new phrase
MIN_REST_TICKS = 6  # gaps up to a 16th inside a harmony part are held over


@dataclass
class Arrangement:
    lineup: Lineup
    parts: dict[str, list[Note]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _moved(n: Note, pitch: int) -> Note:
    """Copy of a source note at another pitch (timing, confidence and articulations kept)."""
    return replace(n, pitch=pitch, sources=list(n.sources), articulations=list(n.articulations))


def _phrases(notes: list[Note]) -> list[list[Note]]:
    out: list[list[Note]] = []
    for n in sorted(notes, key=lambda n: n.start):
        if out and n.start - max(m.end for m in out[-1]) < PHRASE_GAP_TICKS:
            out[-1].append(n)
        else:
            out.append([n])
    return out


BASS_TARGET = 0.35  # bass lines centre a third of the way up the comfortable range


def _best_shift(pitches: list[int], lo: int, hi: int, pro: tuple[int, int], prefer_low: bool = False,
                prev: int | None = None) -> int | None:
    """Octave shift that puts the most notes in [lo, hi] and none outside the pro range.

    Ties go to the octave nearest the middle of the range (a third of the way
    up for bass lines, which sit low and leave room for the inner parts but
    should not live on ledger lines), and nearest the previous phrase's last
    note, so the line stays continuous.
    """
    target = lo + BASS_TARGET * (hi - lo) if prefer_low else (lo + hi) / 2
    best, score = None, None
    for k in range(-4, 5):
        shifted = [p + 12 * k for p in pitches]
        if any(not pro[0] <= p <= pro[1] for p in shifted):
            continue
        inside = sum(lo <= p <= hi for p in shifted)
        mean = sum(shifted) / len(shifted)
        jump = abs(shifted[0] - prev) if prev is not None else 0
        cand = (inside, -(abs(mean - target) + jump))
        if score is None or cand > score:
            best, score = k, cand
    return best


def _nearest_octave(pitch: int, ranges: list[tuple[int, int]], prev: int | None) -> int | None:
    """The octave of `pitch` inside the first range that has one, nearest `prev` (or the range middle)."""
    for lo, hi in ranges:
        opts = [pitch % 12 + 12 * k for k in range(11) if lo <= pitch % 12 + 12 * k <= hi]
        if opts:
            ref = prev if prev is not None else (lo + hi) / 2
            return min(opts, key=lambda x: (abs(x - ref), x))
    return None


def _place_line(notes: list[Note], part: Part, warnings: list[str], shift_extra: int = 0, prefer_low: bool = False) -> list[Note]:
    inst = part.instrument
    placed = []
    for phrase in _phrases(notes):
        prev = placed[-1].pitch if placed else None
        k = _best_shift([n.pitch + shift_extra for n in phrase], *inst.comfortable, inst.pro, prefer_low, prev)
        if k is None:
            # No single octave fits the whole phrase: per note, the octave nearest the previous note.
            for n in phrase:
                p = _nearest_octave(n.pitch + shift_extra, [inst.comfortable, inst.pro], placed[-1].pitch if placed else None)
                if p is None:
                    warnings.append(f"{part.name}: dropped {n.pitch} at tick {n.start} (no playable octave)")
                    continue
                placed.append(_moved(n, p))
            warnings.append(f"{part.name}: phrase at tick {phrase[0].start} needed per-note octave fitting")
            continue
        for n in phrase:
            placed.append(_moved(n, n.pitch + shift_extra + 12 * k))
    return _hold_small_gaps(placed)


def _hold_small_gaps(notes: list[Note]) -> list[Note]:
    notes.sort(key=lambda n: n.start)
    for a, b in zip(notes, notes[1:]):
        if 0 < b.start - a.end <= MIN_REST_TICKS:
            a.dur = b.start - a.start
    return notes


def _sounding_at(notes: list[Note], tick: int) -> list[Note]:
    return [n for n in notes if n.start <= tick < n.end]


def _voice_slot(pcs: list[int], parts: list[Part], ceiling: int, floor: int, prev: dict[str, int]) -> dict[str, int]:
    """Assign one pitch per inner part (high to low) from the chord's pitch classes."""
    chosen: dict[str, int] = {}
    used: list[int] = []
    upper = ceiling
    for part in parts:
        lo, hi = part.instrument.comfortable
        hi = min(hi, upper - 1)
        lo = max(lo, floor + 1)
        options = [p for p in range(lo, hi + 1) if p % 12 in pcs]
        if not options:
            continue
        missing = [p for p in options if p % 12 not in {u % 12 for u in used}]
        # When every chord tone is taken, double in another octave rather than at the unison.
        pool = missing or [p for p in options if p not in used] or options
        # Close position: start just under the part above; afterwards follow the part's own previous note.
        target = prev.get(part.name, min(hi, upper - 3) if upper < 200 else (lo + hi) // 2)
        p = min(pool, key=lambda x: (abs(x - target), -x))
        chosen[part.name] = p
        used.append(p)
        upper = p + 1  # next part may double at the unison but not cross above
    return chosen


def arrange(comp: Composition, lineup: Lineup = MINIMAL_BAND) -> Arrangement:
    arr = Arrangement(lineup)
    melody = [n for v in comp.voices_with(VoiceRole.MELODY) for n in v.notes]
    bass = [n for v in comp.voices_with(VoiceRole.BASS) for n in v.notes]
    harmony = [n for v in comp.voices if v.role in (VoiceRole.HARMONY, VoiceRole.COUNTERMELODY) for n in v.notes]

    lead = lineup.by_name("Solo Cornet")
    arr.parts[lead.name] = _place_line(melody, lead, arr.warnings)

    eb, bb = lineup.by_name("E♭ Bass"), lineup.by_name("B♭ Bass")
    arr.parts[eb.name] = _place_line(bass, eb, arr.warnings, prefer_low=True)
    low = []
    for n in arr.parts[eb.name]:
        p = n.pitch - 12
        # Octave below only where that stays comfortable; pedal notes are a player's choice, not a default.
        low.append(_moved(n, p if bb.instrument.check(p) == "ok" else n.pitch))
    arr.parts[bb.name] = low

    inner = [p for p in lineup.parts if p.name not in (lead.name, eb.name, bb.name)]
    inner.sort(key=lambda p: -sum(p.instrument.comfortable))  # high to low
    for p in inner:
        arr.parts[p.name] = []
    slots = sorted({n.start for n in harmony})
    ends = {s: e for s, e in zip(slots, slots[1:])}
    prev: dict[str, int] = {}
    for s in slots:
        sounding = _sounding_at(harmony, s) or [n for n in harmony if n.start == s]
        pcs = sorted({n.pitch % 12 for n in sounding}
                     | {n.pitch % 12 for n in _sounding_at(melody, s)}
                     | {n.pitch % 12 for n in _sounding_at(bass, s)})
        top = _sounding_at(arr.parts[lead.name], s)
        bot = _sounding_at(arr.parts[eb.name], s)
        ceiling = top[0].pitch if top else 90
        floor = bot[0].pitch if bot else 30
        nxt = ends.get(s)
        end = max(n.end for n in sounding)
        if nxt is not None:
            # Hold across tiny gaps (performance/MIDI release offsets) instead of writing 64th rests.
            end = nxt if nxt - end <= MIN_REST_TICKS else min(end, nxt)
        conf = min(n.confidence for n in sounding)
        voicing = _voice_slot(pcs, inner, ceiling, floor, prev)
        for name, p in voicing.items():
            arr.parts[name].append(Note(p, s, end - s, conf, ["arranger"]))
        prev.update(voicing)
    return arr


# ---------------------------------------------------------------------------
# Layered arrangement: solo feature with band accompaniment.
#
# Each source layer maps to the band section that plays that texture:
#   solo            -> Solo Cornet (the featured part)
#   strings (line)  -> Euphonium countermelody (top moving line of the strings)
#   strings + keys  -> sustained pads: Flugelhorn, horns, baritones
#   orch. brass     -> brass choir: Repiano, 2nd/3rd Cornets, 1st/2nd Trombones
#   bass            -> E♭ Bass, B♭ Bass (octave below where comfortable),
#                      Bass Trombone doubling while the brass choir plays
#   drums           -> Percussion (drum kit, unpitched)
# The Soprano Cornet is left tacet: the source has no part in its register.
# ---------------------------------------------------------------------------

def layer_of_part(name: str) -> str | None:
    """Which source layer a band part plays in the layered arrangement (for its dynamics)."""
    if name == "Solo Cornet":
        return "solo"
    if name in PAD_PARTS or name == "Euphonium":
        return "strings"
    if name in CHOIR_PARTS:
        return "brass"
    if name in ("E♭ Bass", "B♭ Bass", "Bass Trombone"):
        return "bass"
    if name == "Percussion":
        return "drums"
    return None


PAD_PARTS = ["Flugelhorn", "Solo Horn", "1st Horn", "2nd Horn", "1st Baritone", "2nd Baritone"]
CHOIR_PARTS = ["Repiano Cornet", "2nd Cornet", "3rd Cornet", "1st Trombone", "2nd Trombone"]
COUNTER_MIN_MOVE = 2  # a strings note shorter than this many beats counts as melodic movement


def _layer(comp: Composition, name: str) -> list[Note]:
    return [n for v in comp.voices if v.layer == name for n in v.notes]


def _voice_layer(arr: Arrangement, slots, part_names: list[str], ceiling_notes: list[Note],
                 floor_notes: list[Note], default_ceiling: int, conf: float) -> None:
    parts = [arr.lineup.by_name(n) for n in part_names]
    parts.sort(key=lambda p: -sum(p.instrument.comfortable))
    prev: dict[str, int] = {}
    for p in parts:
        arr.parts.setdefault(p.name, [])
    for start, end, pcs in slots:
        top = _sounding_at(ceiling_notes, start)
        bot = _sounding_at(floor_notes, start)
        ceiling = top[0].pitch if top else default_ceiling
        # Pads may sit below a bass line that climbs into the tenor register.
        floor = min(bot[0].pitch, 43) if bot else 30
        voicing = _voice_slot(pcs, parts, ceiling, floor, prev)
        for name, p in voicing.items():
            arr.parts[name].append(Note(p, start, end - start, conf, ["arranger"]))
        prev.update(voicing)


def _place_smooth(notes: list[Note], part: Part) -> list[Note]:
    """Octave per note nearest the previous note (inside the comfortable range).

    Used for lines pulled from a dense texture, where the source hops between
    voices and a single octave shift per phrase would leave large leaps.
    """
    lo, hi = part.instrument.comfortable
    prev = (lo + hi) // 2
    out = []
    for n in sorted(notes, key=lambda n: n.start):
        opts = [n.pitch % 12 + 12 * k for k in range(11) if lo <= n.pitch % 12 + 12 * k <= hi]
        if not opts:
            continue
        p = min(opts, key=lambda x: abs(x - prev))
        out.append(_moved(n, p))
        prev = p
    return _hold_small_gaps(out)


def arrange_layers(comp: Composition, lineup: Lineup | None = None) -> Arrangement:
    from .harmony import harmony_slots
    from .instruments import BRASS_BAND

    lineup = lineup or BRASS_BAND
    arr = Arrangement(lineup)
    for p in lineup.parts:
        arr.parts[p.name] = []
    end = comp.end_tick

    solo = _layer(comp, "solo")
    arr.parts["Solo Cornet"] = _place_line(solo, lineup.by_name("Solo Cornet"), arr.warnings)

    bass = _layer(comp, "bass")
    eb, bb = lineup.by_name("E♭ Bass"), lineup.by_name("B♭ Bass")
    arr.parts[eb.name] = _place_line(bass, eb, arr.warnings, prefer_low=True)
    arr.parts[bb.name] = [_moved(n, n.pitch - 12 if bb.instrument.check(n.pitch - 12) == "ok" else n.pitch)
                          for n in arr.parts[eb.name]]

    strings = _layer(comp, "strings")
    keys = _layer(comp, "keys")
    brass = _layer(comp, "brass")

    # Countermelody: the top strings line where it moves (long held tops belong to the pad).
    top = []
    for n in sorted(strings, key=lambda n: n.start):
        if top and n.start - top[-1].start < 6:
            if n.pitch > top[-1].pitch:
                top[-1] = n
            continue
        top.append(n)
    counter = [n for n in top if n.dur < COUNTER_MIN_MOVE * comp.ticks_per_beat]
    euph = lineup.by_name("Euphonium")
    arr.parts[euph.name] = _place_smooth(counter, euph)

    pad_slots = harmony_slots(strings + keys, end)
    _voice_layer(arr, pad_slots, PAD_PARTS, arr.parts["Solo Cornet"], arr.parts[eb.name], 76, 0.8)

    choir_slots = harmony_slots(brass, end, max_pcs=3)
    _voice_layer(arr, choir_slots, CHOIR_PARTS, arr.parts["Solo Cornet"], arr.parts[eb.name], 79, 0.8)

    # Bass trombone reinforces the bass line only while the brass choir is playing.
    btb = lineup.by_name("Bass Trombone")
    active = [(s, e) for s, e, _ in choir_slots]
    tutti = [n for n in bass if any(s <= n.start < e for s, e in active)]
    arr.parts[btb.name] = _place_line(tutti, btb, arr.warnings, prefer_low=True)

    drums = _layer(comp, "drums")
    if drums and "Percussion" in [p.name for p in lineup.parts]:
        arr.parts["Percussion"] = sorted(drums, key=lambda n: n.start)
    return arr
