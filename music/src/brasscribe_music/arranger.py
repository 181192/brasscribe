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

from dataclasses import dataclass, field

from .instruments import MINIMAL_BAND, Lineup, Part
from .score_model import Composition, Note, VoiceRole

PHRASE_GAP_TICKS = 48  # a rest of two beats or more starts a new phrase
MIN_REST_TICKS = 6  # gaps up to a 16th inside a harmony part are held over


@dataclass
class Arrangement:
    lineup: Lineup
    parts: dict[str, list[Note]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


def _phrases(notes: list[Note]) -> list[list[Note]]:
    out: list[list[Note]] = []
    for n in sorted(notes, key=lambda n: n.start):
        if out and n.start - max(m.end for m in out[-1]) < PHRASE_GAP_TICKS:
            out[-1].append(n)
        else:
            out.append([n])
    return out


def _best_shift(pitches: list[int], lo: int, hi: int, pro: tuple[int, int], prefer_low: bool = False) -> int | None:
    """Octave shift that puts the most notes in [lo, hi] and none outside the pro range.

    Ties go to the octave nearest the middle of the range, or the lowest one for
    bass lines (brass-band basses sit low and leave room for the inner parts).
    """
    best, score = None, None
    for k in range(-4, 5):
        shifted = [p + 12 * k for p in pitches]
        if any(not pro[0] <= p <= pro[1] for p in shifted):
            continue
        inside = sum(lo <= p <= hi for p in shifted)
        mean = sum(shifted) / len(shifted)
        cand = (inside, -mean if prefer_low else -abs(mean - (lo + hi) / 2))
        if score is None or cand > score:
            best, score = k, cand
    return best


def _place_line(notes: list[Note], part: Part, warnings: list[str], shift_extra: int = 0, prefer_low: bool = False) -> list[Note]:
    inst = part.instrument
    placed = []
    for phrase in _phrases(notes):
        k = _best_shift([n.pitch + shift_extra for n in phrase], *inst.comfortable, inst.pro, prefer_low)
        if k is None:
            # No single octave fits the whole phrase: fall back to per-note octave fitting.
            for n in phrase:
                p = inst.fit_octave(n.pitch + shift_extra)
                if inst.check(p) == "impossible":
                    warnings.append(f"{part.name}: dropped {n.pitch} at tick {n.start} (no playable octave)")
                    continue
                placed.append(Note(p, n.start, n.dur, n.confidence, n.sources, n.onset_s, n.offset_s))
            warnings.append(f"{part.name}: phrase at tick {phrase[0].start} needed per-note octave fitting")
            continue
        for n in phrase:
            placed.append(Note(n.pitch + shift_extra + 12 * k, n.start, n.dur, n.confidence, n.sources, n.onset_s, n.offset_s))
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
        target = prev.get(part.name, (lo + hi) // 2)
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
        low.append(Note(p if bb.instrument.check(p) == "ok" else n.pitch, n.start, n.dur, n.confidence, n.sources))
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
