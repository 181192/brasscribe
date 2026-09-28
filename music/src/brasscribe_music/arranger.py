"""Minimal deterministic brass-band arranger.

Reads a Composition (concert pitch, voices tagged by role) and writes concert
notes per band part:
  melody  -> the lineup's lead, Solo Cornet (octave chosen per phrase to sit in its comfortable range)
  bass    -> the lineup's bass, E♭ Bass (lowest comfortable octave), and its second bass,
             B♭ Bass, an octave lower where comfortable
  harmony -> inner parts, voiced per harmony slot from the chord tones sounding
             at that moment: inside each part's range, under the melody, over
             the bass, no crossing, least movement from the previous chord.
             A four-part lineup (the quartet) voices its two inner parts
             together as alto and tenor with the chorale rules of voice_satb.
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


def _readable(inst, pitch: int) -> bool:
    lo, hi = inst.preferred
    return lo <= pitch <= hi


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


BASS_TARGET = 0.35  # bass lines centre a third of the way up the reading range


def _best_shift(pitches: list[int], lo: int, hi: int, pro: tuple[int, int], prefer_low: bool = False,
                prev: int | None = None, bass_overflow_up: bool = False) -> int | None:
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
        # Bass parts in treble clef read up to the top of their range easily but go onto ledger
        # lines below it, so for bass lines notes above the reading range still count as inside.
        top = pro[1] if prefer_low and bass_overflow_up else hi
        inside = sum(lo <= p <= top for p in shifted)
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


def _leap_cut(phrase: list[Note]) -> int:
    """Index after the phrase's largest leap (ties go to the later leap)."""
    return max((abs(b.pitch - a.pitch), i + 1) for i, (a, b) in enumerate(zip(phrase, phrase[1:])))[1]


def _split_wide(phrase: list[Note], width: int) -> list[list[Note]]:
    """Split a phrase that spans more than `width` semitones at its largest leap, recursively,
    so each piece can take its own octave (the line changes octave where it jumps anyway)."""
    ps = [n.pitch for n in phrase]
    if len(phrase) < 4 or max(ps) - min(ps) <= width:
        return [phrase]
    cut = _leap_cut(phrase)
    return _split_wide(phrase[:cut], width) + _split_wide(phrase[cut:], width)


def _place_line(notes: list[Note], part: Part, warnings: list[str], shift_extra: int = 0, prefer_low: bool = False,
                bass_overflow_up: bool = False) -> list[Note]:
    inst = part.instrument
    placed: list[Note] = []
    phrases = _phrases(notes)
    if bass_overflow_up:
        width = inst.preferred[1] - inst.preferred[0]
        phrases = [q for ph in phrases for q in _split_wide(ph, width)]
    for phrase in phrases:
        _place_phrase(phrase, part, warnings, shift_extra, prefer_low, bass_overflow_up, placed)
    return _hold_small_gaps(placed)


def _place_phrase(phrase: list[Note], part: Part, warnings: list[str], shift_extra: int, prefer_low: bool,
                  bass_overflow_up: bool, placed: list[Note], split: bool = False, keep: int | None = None) -> int | None:
    """Place one phrase at the best single octave; returns the octave shift used (None: per note).

    A tune phrase no octave fits, but no wider than the placement limit, is split at its largest
    leap and each piece placed on its own, keeping the previous piece's shift (`keep`) wherever it
    fits: the line changes octave only where it jumps, so its contour is kept. Bass lines
    (`prefer_low`), wider tune phrases and tune pieces under four notes are fitted note by note at
    the octave nearest the previous note: their wide leaps are mostly tracker octave errors or
    jumps between voices, which this folds back together.
    """
    inst = part.instrument
    lo, hi = inst.placement_limit
    pitches = [n.pitch + shift_extra for n in phrase]
    if keep is not None and all(lo <= p + 12 * keep <= hi for p in pitches):
        k = keep
    else:
        prev = placed[-1].pitch if placed else None
        k = _best_shift(pitches, *inst.preferred, inst.placement_limit, prefer_low, prev, bass_overflow_up=bass_overflow_up)
    if k is not None:
        placed.extend(_moved(n, p + 12 * k) for n, p in zip(phrase, pitches))
        return k
    if not prefer_low and len(phrase) >= 4 and (split or max(pitches) - min(pitches) <= hi - lo):
        if not split:
            warnings.append(f"{part.name}: phrase at tick {phrase[0].start} split at its leaps to fit the range")
        cut = _leap_cut(phrase)
        k = _place_phrase(phrase[:cut], part, warnings, shift_extra, prefer_low, bass_overflow_up, placed, True, keep)
        return _place_phrase(phrase[cut:], part, warnings, shift_extra, prefer_low, bass_overflow_up, placed, True, k)
    for n, p0 in zip(phrase, pitches):
        p = _nearest_octave(p0, [inst.preferred, inst.placement_limit], placed[-1].pitch if placed else None)
        if p is None:
            warnings.append(f"{part.name}: dropped {n.pitch} at tick {n.start} (no playable octave)")
            continue
        placed.append(_moved(n, p))
    warnings.append(f"{part.name}: phrase at tick {phrase[0].start} needed per-note octave fitting")
    return None


def place_as_played(notes: list[Note], part: Part, warnings: list[str]) -> list[Note]:
    """The player's own line written for their part, in the octave they played it.

    A note keeps its octave while it is inside the instrument's professional range. A note outside
    it (almost always a tracker octave error) moves by octaves into the comfortable range, else the
    professional range, and each move is a warning. This writes down the player's notes; _place_line
    arranges a heard line onto a part, which is another thing.
    """
    inst = part.instrument
    lo, hi = inst.pro
    placed = []
    for n in sorted(notes, key=lambda n: n.start):
        p = n.pitch
        if not lo <= p <= hi:
            p = inst.fit_octave(p)
            if not lo <= p <= hi:
                warnings.append(f"{part.name}: dropped {n.pitch} at tick {n.start} (no playable octave)")
                continue
            warnings.append(f"{part.name}: moved {n.pitch} to {p} at tick {n.start} (outside the range)")
        placed.append(_moved(n, p))
    return _hold_small_gaps(placed)


def _hold_small_gaps(notes: list[Note]) -> list[Note]:
    notes.sort(key=lambda n: n.start)
    for a, b in zip(notes, notes[1:]):
        if 0 < b.start - a.end <= MIN_REST_TICKS:
            a.dur = b.start - a.start
    return notes


def _sounding_at(notes: list[Note], tick: int) -> list[Note]:
    return [n for n in notes if n.start <= tick < n.end]


def _voice_slot(pcs: list[int], parts: list[Part], ceiling: int, floor: int, prev: dict[str, int],
                ranges: dict[str, tuple[int, int]] | None = None) -> dict[str, int]:
    """Assign one pitch per inner part (high to low) from the chord's pitch classes
    (inside each part's reading range, or its entry in `ranges`)."""
    chosen: dict[str, int] = {}
    used: list[int] = []
    upper = ceiling
    for part in parts:
        lo, hi = ranges[part.name] if ranges else part.instrument.preferred
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


# ---------------------------------------------------------------------------
# Four-part voicing (quartet): alto and tenor chosen together per harmony slot.
# ---------------------------------------------------------------------------

def chord_root(pcs: list[int], bass_pc: int | None) -> int:
    """Root of a slot's chord: the first pitch class (ascending) with the most of: a triad (third and
    perfect fifth above it), a fifth above it, a third above it, the bass on it."""
    s = set(pcs)
    best, key = pcs[0], None
    for r in sorted(pcs):
        third = (r + 4) % 12 in s or (r + 3) % 12 in s
        fifth = (r + 7) % 12 in s
        k = (int(third and fifth), int(fifth), int(third), int(r == bass_pc))
        if key is None or k > key:
            best, key = r, k
    return best


def _perfect_parallels(prev: list[int | None], cur: list[int | None]) -> int:
    """Pairs of voices (listed high to low) that move in the same direction from one perfect
    fifth or octave (unison) to another of the same kind."""
    n = 0
    for i in range(len(cur)):
        for j in range(i + 1, len(cur)):
            a0, b0, a1, b1 = prev[i], prev[j], cur[i], cur[j]
            if None in (a0, b0, a1, b1):
                continue
            iv0, iv1 = (a0 - b0) % 12, (a1 - b1) % 12
            if iv0 == iv1 and iv0 in (0, 7) and a1 != a0 and b1 != b0 and (a1 > a0) == (b1 > b0):
                n += 1
    return n


def voice_satb(pcs: list[int], soprano: int | None, bass: int | None, prev: list[int | None] | None,
               alto_range: tuple[int, int], tenor_range: tuple[int, int], soprano_top: int | None = None) -> tuple[int, int] | None:
    """(alto, tenor) for one harmony slot under `soprano` and over `bass`, or None when no pair
    keeps the rules.

    Hard rules: S > A >= T > B (only alto and tenor may share a note), S-A and A-T at most an
    octave, both notes chord tones. Among the pairs that keep them, the smallest of (in order):
      1. chord tones left out (the fifth of a triad does not count)
      2. parallel perfect fifths and octaves against the previous slot, over all voice pairs
      3. doubling: 1 for a missing fifth, 1 per extra copy of a tone other than the root and
         the bass's own tone
      4. movement |dA| + |dT| from the previous slot
      5. the higher alto, then the higher tenor
    The order was tuned on the ChoraleBricks chorales (eval/brasscribe_eval/arrange_bench.py)
    and is frozen: the Rust port (arranger.rs) must follow it exactly.
    `prev` is the previous slot's [S, A, T, B] (None where a voice was silent). A lead that moves
    during the slot is given as its lowest note (`soprano`, for crossing) and its highest
    (`soprano_top`, for spacing; default `soprano`).
    """
    s = set(pcs)
    top = soprano if soprano_top is None else soprano_top
    bass_pc = bass % 12 if bass is not None else None
    root = chord_root(sorted(s), bass_pc)
    fifth = (root + 7) % 12 if (root + 7) % 12 in s else None
    best, best_key = None, None
    alo, ahi = alto_range
    tlo, thi = tenor_range
    for a in range(alo, ahi + 1):
        if a % 12 not in s or (soprano is not None and not (a < soprano and top - a <= 12)):
            continue
        for t in range(tlo, thi + 1):
            if t % 12 not in s or t > a or a - t > 12 or (bass is not None and t <= bass):
                continue
            voices = [v for v in (soprano, a, t, bass) if v is not None]
            have = [v % 12 for v in voices]
            missing = [pc for pc in s if pc not in have]
            essential = sum(pc != fifth for pc in missing)
            doubling = int(fifth is not None and fifth in missing)
            for pc in set(have):
                if pc != root and pc != bass_pc:
                    doubling += have.count(pc) - 1
            if prev is not None:
                par = _perfect_parallels(prev, [soprano, a, t, bass])
                move = (abs(a - prev[1]) if prev[1] is not None else 0) + (abs(t - prev[2]) if prev[2] is not None else 0)
            else:
                par = move = 0
            key = (essential, par, doubling, move, -a, -t)
            if best_key is None or key < best_key:
                best, best_key = (a, t), key
    return best


def _voice_satb_slots(arr: Arrangement, slots: list[tuple[int, int, list[int], float]], lead_notes: list[Note],
                      bass_notes: list[Note], difficulty: str) -> None:
    """Alto and tenor of a four-part lineup, slot by slot (start, end, pitch classes, confidence)."""
    from .difficulty import mode_range

    lineup = arr.lineup
    inner = [p for p in lineup.parts if p.name not in (lineup.lead, lineup.bass)]
    inner.sort(key=lambda p: -sum(p.instrument.comfortable))  # high to low
    alto, tenor = inner
    ra, rt = mode_range(alto, difficulty), mode_range(tenor, difficulty)
    for p in inner:
        arr.parts.setdefault(p.name, [])
    prev: list[int | None] | None = None
    prev_named: dict[str, int] = {}
    for start, end, pcs, conf in slots:
        # The inner parts hold through the slot: keep them under the lead's lowest note in it and
        # over the bass's highest, so a moving line never crosses them.
        top = [n.pitch for n in lead_notes if n.start < end and n.end > start]
        bot = [n.pitch for n in bass_notes if n.start < end and n.end > start]
        sop = min(top) if top else None
        bas = max(bot) if bot else None
        pair = voice_satb(pcs, sop, bas, prev, ra, rt, max(top) if top else None)
        if pair is None:
            arr.warnings.append(f"{alto.name}/{tenor.name}: slot at tick {start} voiced without the four-part rules")
            voicing = _voice_slot(pcs, [alto, tenor], sop if sop is not None else 90, bas if bas is not None else 30,
                                  prev_named, {alto.name: ra, tenor.name: rt})
            a, t = voicing.get(alto.name), voicing.get(tenor.name)
        else:
            a, t = pair
        for part, p in ((alto, a), (tenor, t)):
            if p is not None:
                arr.parts[part.name].append(Note(p, start, end - start, conf, ["arranger"]))
                prev_named[part.name] = p
        prev = [sop, a, t, bas]


HARMONY_CONTEXT = " harmony"  # not a part name: the source harmony as chord context for the difficulty modes


def _outer_difficulty(arr: Arrangement, difficulty: str, harmony: list[Note]) -> None:
    """Four-part lineups: the difficulty mode applied to lead and bass before the inner parts are
    voiced against them (so a later change to the outer parts cannot cross an inner one). The
    16th merges read the chord from the other outer part and the source harmony."""
    from .difficulty import apply_difficulty

    names = (arr.lineup.lead, arr.lineup.bass)
    parts = {n: arr.parts[n] for n in names}
    parts[HARMONY_CONTEXT] = harmony
    out = apply_difficulty(parts, arr.lineup, difficulty, only=names)
    for n in names:
        arr.parts[n] = out[n]


def _inner_difficulty(arr: Arrangement, difficulty: str) -> dict[str, list[Note]]:
    """Four-part lineups: the difficulty mode on the inner parts only (voiced in its range already)."""
    from .difficulty import apply_difficulty

    inner = tuple(p.name for p in arr.lineup.parts if p.name not in (arr.lineup.lead, arr.lineup.bass))
    return apply_difficulty(arr.parts, arr.lineup, difficulty, only=inner)


def arrange(comp: Composition, lineup: Lineup = MINIMAL_BAND, difficulty: str = "faithful") -> Arrangement:
    """Melody, bass and harmony voices arranged for `lineup`; `difficulty` as in difficulty.py."""
    from .difficulty import apply_difficulty

    arr = Arrangement(lineup)
    melody = [n for v in comp.voices_with(VoiceRole.MELODY) for n in v.notes]
    bass = [n for v in comp.voices_with(VoiceRole.BASS) for n in v.notes]
    harmony = [n for v in comp.voices if v.role in (VoiceRole.HARMONY, VoiceRole.COUNTERMELODY) for n in v.notes]

    lead = lineup.lead_part
    arr.parts[lead.name] = _place_line(melody, lead, arr.warnings)

    eb, bb = lineup.bass_part, lineup.second_bass_part
    arr.parts[eb.name] = _place_line(bass, eb, arr.warnings, prefer_low=True)
    if bb is not None:
        low = []
        for n in arr.parts[eb.name]:
            p = n.pitch - 12
            # Octave below only where that stays comfortable; pedal notes are a player's choice, not a default.
            low.append(_moved(n, p if _readable(bb.instrument, p) else n.pitch))
        arr.parts[bb.name] = low

    inner = [p for p in lineup.parts if p.name not in (lead.name, eb.name, lineup.second_bass)]
    inner.sort(key=lambda p: -sum(p.instrument.comfortable))  # high to low
    for p in inner:
        arr.parts[p.name] = []
    if lineup.satb:
        _outer_difficulty(arr, difficulty, harmony)
    satb_slots = []
    slots = sorted({n.start for n in harmony})
    ends = {s: e for s, e in zip(slots, slots[1:])}
    prev: dict[str, int] = {}
    for s in slots:
        sounding = _sounding_at(harmony, s) or [n for n in harmony if n.start == s]
        pcs = sorted({n.pitch % 12 for n in sounding}
                     | {n.pitch % 12 for n in _sounding_at(melody, s)}
                     | {n.pitch % 12 for n in _sounding_at(bass, s)})
        top = _sounding_at(arr.parts[lead.name], s) if _tune_on_top(lineup) else []
        bot = _sounding_at(arr.parts[eb.name], s)
        ceiling = top[0].pitch if top else 90
        floor = bot[0].pitch if bot else 30
        nxt = ends.get(s)
        end = max(n.end for n in sounding)
        if nxt is not None:
            # Hold across tiny gaps (performance/MIDI release offsets) instead of writing 64th rests.
            end = nxt if nxt - end <= MIN_REST_TICKS else min(end, nxt)
        conf = min(n.confidence for n in sounding)
        if lineup.satb:
            satb_slots.append((s, end, pcs, conf))
            continue
        voicing = _voice_slot(pcs, inner, ceiling, floor, prev)
        for name, p in voicing.items():
            arr.parts[name].append(Note(p, s, end - s, conf, ["arranger"]))
        prev.update(voicing)
    if lineup.satb:
        _voice_satb_slots(arr, satb_slots, arr.parts[lead.name], arr.parts[eb.name], difficulty)
        arr.parts = _inner_difficulty(arr, difficulty)
        return arr
    arr.parts = apply_difficulty(arr.parts, lineup, difficulty)
    return arr


def arrange_composition(comp: Composition) -> Arrangement:
    """Arrange a Composition the way it was made (as recorded in `comp.arrangement`).

    Voices with layers: the layered arranger with the recorded lineup (default the band) and
    difficulty. Otherwise the minimal-band arranger, or the quartet when that is recorded.
    """
    difficulty = (comp.arrangement or {}).get("difficulty") or "faithful"
    lineup, layered = composition_lineup(comp)
    if not layered:
        return arrange(comp, lineup, difficulty) if lineup is not MINIMAL_BAND else arrange(comp)
    return arrange_layers(comp, lineup, difficulty=difficulty)


def composition_lineup(comp: Composition) -> tuple[Lineup, bool]:
    """The lineup a Composition is arranged for (as recorded in `comp.arrangement`), and whether
    the layered arranger makes it (its voices carry layers)."""
    from .instruments import (BRASS_BAND, QUARTET, lead_lineup, lineup_by_name, lineup_key, seat_lineup, seat_part,
                              with_reading)

    opts = comp.arrangement or {}
    seat, reads = opts.get("seat"), opts.get("reads")
    layered = any(v.layer for v in comp.voices)
    if not layered:
        lineup = QUARTET if opts.get("lineup") == "quartet" else MINIMAL_BAND
    elif seat and is_solo_take(comp):
        return seat_lineup(seat, reads), True
    else:
        try:
            lineup = lineup_by_name(opts.get("lineup"))
        except ValueError:
            # Anything but a known lineup arranges for the band, as before lineups carried their roles.
            lineup = BRASS_BAND
    if seat:
        lineup = with_reading(lineup, seat, seat_part(lineup_key(lineup), seat).part, reads)
        if opts.get("lead") == "seat":
            try:
                lineup = lead_lineup(lineup, seat)
            except ValueError:
                pass  # a lineup the tune cannot move in keeps its own lead
    return lineup, layered


# Where a part's notes come from (part_sources). The UI words never say "transcribed".
YOUR_RECORDING = "your-recording"  # a solo take: the part carries the player's own line
RECORDING = "recording"  # the part follows a line heard in a band recording
ARRANGED = "arranged"  # voiced from the harmony, or doubling the tune
# Nothing to play in this arrangement: the Percussion part of a recording without drums, the Soprano
# Cornet when it has no climax to double (always in faithful mode). No footer.
EMPTY = "empty"


def _empty_parts(comp: Composition, lineup) -> set[str]:
    """The parts of a layered band arrangement that the arranger leaves without notes (see EMPTY)."""
    if lineup.satb or lineup.as_played:
        return set()
    out = set()
    if lineup.has("Percussion") and not _has_notes(comp, "drums"):
        out.add("Percussion")
    difficulty = (comp.arrangement or {}).get("difficulty") or "faithful"
    spans = _climax_spans(comp)
    doubles = difficulty != "faithful" and lineup.lead in BAND_LEADS \
        and any(a <= n.start < b for n in _layer(comp, "solo") for a, b in spans)
    if lineup.has("Soprano Cornet") and not doubles:
        out.add("Soprano Cornet")
    return out


# Languages of the source footer on printed parts.
FOOTER_LANGS = ("en", "nb")
_FOOTERS = {ARRANGED: {"en": "Arranged by Brasscribe from the band's harmony.",
                       "nb": "Arrangert av Brasscribe ut fra harmoniene i bandet."}}


def source_footer(source: str, lang: str = "en") -> str | None:
    """The footer printed on a part from `source` (part_sources), in `lang` ("en" or "nb"; "" = en):
    an arranged part says so; a part from the recording has none."""
    texts = _FOOTERS.get(source)
    return None if texts is None else texts["nb" if lang == "nb" else "en"]


def part_footers(comp: Composition, lang: str = "en") -> dict[str, str]:
    """{part name: footer} for every part of the Composition's arrangement that has one."""
    return {p: f for p, s in part_sources(comp).items() if (f := source_footer(s, lang)) is not None}


def _has_notes(comp: Composition, *layers: str) -> bool:
    return any(v.notes for v in comp.voices if v.layer in layers)


def is_solo_take(comp: Composition) -> bool:
    """A layered Composition with notes in its solo layer only: one player recorded alone."""
    return any(v.layer for v in comp.voices) and _has_notes(comp, "solo") and \
        not any(v.notes for v in comp.voices if v.layer != "solo")


def part_sources(comp: Composition) -> dict[str, str]:
    """Where each part of the Composition's arrangement comes from, in score order.

    Derived, not stored: from the lineup's roles, the arranger that made it (layered or not)
    and which layers have notes. `your-recording`: a solo take's line; `recording`: a line
    heard in the recording (the tune, the bass line and its doublings, the countermelody from
    the strings' top line, the drums); `arranged`: everything voiced from the harmony, and the
    Soprano Cornet's doubling of the tune; `empty`: a part left without notes (no drums, no
    climax to double).
    """
    lineup, layered = composition_lineup(comp)
    heard: set[str] = set()
    if not layered:
        heard |= {lineup.lead, lineup.bass, *([lineup.second_bass] if lineup.second_bass else [])}
    elif is_solo_take(comp):
        return {p.name: YOUR_RECORDING if p.name == lineup.lead else ARRANGED for p in lineup.parts}
    else:
        if _has_notes(comp, "solo"):
            heard.add(lineup.lead)
        if _has_notes(comp, "bass"):
            heard |= {lineup.bass, *([lineup.second_bass] if lineup.second_bass else [])}
            if not lineup.satb and lineup.has("Bass Trombone"):
                heard.add("Bass Trombone")
        if not lineup.satb and _has_notes(comp, "strings") and counter_part(lineup):
            heard.add(counter_part(lineup))
        if not lineup.satb and _has_notes(comp, "drums") and lineup.has("Percussion"):
            heard.add("Percussion")
    empty = _empty_parts(comp, lineup) if layered else set()
    return {p.name: RECORDING if p.name in heard else EMPTY if p.name in empty else ARRANGED for p in lineup.parts}


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
#
# A four-part lineup (the quartet) plays: solo -> lead (1st Cornet), bass ->
# bass (Euphonium), strings + keys + orch. brass -> one set of harmony slots
# voiced as alto and tenor (2nd Cornet, Tenor Horn). It has no countermelody,
# drums or soprano doubling.
# ---------------------------------------------------------------------------

def layer_of_part(lineup: Lineup, name: str) -> str | None:
    """Which source layer a part of `lineup` plays in the layered arrangement (for its dynamics)."""
    if name == lineup.lead:
        return "solo"
    if name in (lineup.bass, lineup.second_bass):
        return "bass"
    if name in BAND_LEADS:  # the band's usual lead, with the tune on the player's part (lead="seat")
        return "strings"
    if lineup.satb:
        return "strings"
    if name in PAD_PARTS or name == "Euphonium":
        return "strings"
    if name in CHOIR_PARTS:
        return "brass"
    if name == "Bass Trombone":
        return "bass"
    if name == "Percussion":
        return "drums"
    return None


BAND_LEADS = ("Solo Cornet",)  # the band lineups' own lead


def counter_part(lineup: Lineup) -> str | None:
    """The part that plays the countermelody: the Euphonium, or with the tune on it, Solo Horn, then 1st Baritone."""
    if lineup.lead != "Euphonium":
        return "Euphonium" if lineup.has("Euphonium") else None
    return next((n for n in ("Solo Horn", "1st Baritone") if lineup.has(n)), None)


def _tune_on_top(lineup: Lineup) -> bool:
    """The tune's part sits on top of the band (a cornet or flugelhorn), so the inner parts go under it."""
    from .instruments import TOP_INSTRUMENTS

    return lineup.lead_part.instrument.id in TOP_INSTRUMENTS


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
    lo, hi = part.instrument.preferred
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


def _figurate(slots, onsets: list[int], min_len: int = 12) -> list[tuple[int, int, list[int]]]:
    """Split harmony slots at the source's own attacks, so the pads play its rhythm.

    A slot is re-attacked at every source onset inside it that lies on the 8th
    grid, at least `min_len` ticks from the previous attack and from the slot end.
    """
    on = sorted({o for o in onsets if o % 12 == 0})
    out = []
    for s, e, pcs in slots:
        cut = s
        for o in on:
            if s < o < e and o - cut >= min_len and e - o >= min_len:
                out.append((cut, o, pcs))
                cut = o
        out.append((cut, e, pcs))
    return out


CLIMAX_MARKS = {"f", "ff"}


def _climax_spans(comp: Composition) -> list[tuple[int, int]]:
    """Tick spans where the solo is at its loudest (ff) while the orchestra plays f or louder."""
    def timeline(layer: str) -> list[tuple[int, str]]:
        return sorted((d.tick, d.mark) for d in comp.dynamics if d.layer == layer)

    def mark_at(tl, t):
        m = None
        for tick, mk in tl:
            if tick <= t:
                m = mk
        return m

    solo, strings = timeline("solo"), timeline("strings")
    edges = sorted({t for t, _ in solo + strings} | {comp.end_tick})
    spans = []
    for a, b in zip(edges, edges[1:]):
        ms, mo = mark_at(solo, a), mark_at(strings, a)
        if ms == "ff" and mo in CLIMAX_MARKS:
            if spans and spans[-1][1] == a:
                spans[-1] = (spans[-1][0], b)
            else:
                spans.append((a, b))
    return spans


def _soprano_doubling(solo: list[Note], part: Part, spans: list[tuple[int, int]]) -> list[Note]:
    """Soprano Cornet doubles the solo an octave up at climaxes (at the unison when the octave is too high)."""
    lo, hi = part.instrument.preferred
    out = []
    for n in solo:
        if not any(a <= n.start < b for a, b in spans):
            continue
        p = n.pitch + 12 if lo <= n.pitch + 12 <= hi else n.pitch if lo <= n.pitch <= hi else None
        if p is not None:
            out.append(_moved(n, p))
    return out


def arrange_layers(comp: Composition, lineup: Lineup | None = None, difficulty: str = "faithful",
                   soprano: bool | None = None, figuration: bool | None = None) -> Arrangement:
    """Layered solo-with-band arrangement.

    `difficulty` (faithful, standard, easier; see difficulty.py) rewrites the
    parts afterwards. `soprano` (Soprano Cornet doubling the solo at climaxes)
    and `figuration` (pads re-attacked with the source's rhythm) default to on
    for every mode but faithful, which reproduces the arranger's plain output.
    Parts missing from `lineup` are simply not written (e.g. MINIMAL_BAND).
    """
    from .difficulty import apply_difficulty
    from .harmony import harmony_slots
    from .instruments import BRASS_BAND

    lineup = lineup or BRASS_BAND
    soprano = difficulty != "faithful" if soprano is None else soprano
    figuration = difficulty != "faithful" if figuration is None else figuration
    names = {p.name for p in lineup.parts}
    arr = Arrangement(lineup)
    for p in lineup.parts:
        arr.parts[p.name] = []
    end = comp.end_tick

    lead = lineup.lead
    solo = _layer(comp, "solo")
    if lineup.as_played:
        # A solo take for the player's seat: their own line in their octave, and nothing else.
        arr.parts[lead] = place_as_played(solo, lineup.lead_part, arr.warnings)
        arr.parts = apply_difficulty(arr.parts, lineup, difficulty)
        return arr
    arr.parts[lead] = _place_line(solo, lineup.lead_part, arr.warnings)

    bass = _layer(comp, "bass")
    eb, bb = lineup.bass_part, lineup.second_bass_part
    # A transposed piece re-fits its bass lines: phrases wider than the reading range are split at their
    # largest leap, and a phrase may spill above the range rather than below it (onto ledger lines).
    # Untransposed arrangements keep their established placement.
    refit = bool(comp.arrangement and comp.arrangement.get("transpose_semitones"))
    arr.parts[eb.name] = _place_line(bass, eb, arr.warnings, prefer_low=True, bass_overflow_up=refit)
    if bb is not None:
        arr.parts[bb.name] = [_moved(n, n.pitch - 12 if _readable(bb.instrument, n.pitch - 12) else n.pitch)
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
    if lineup.satb:
        # One set of harmony slots from the whole accompaniment, voiced as alto and tenor.
        _outer_difficulty(arr, difficulty, strings + keys + brass)
        slots = harmony_slots(strings + keys + brass, end)
        if figuration:
            slots = _figurate(slots, [n.start for n in strings + keys + brass])
        _voice_satb_slots(arr, [(s, e, pcs, 0.8) for s, e, pcs in slots], arr.parts[lead], arr.parts[eb.name], difficulty)
        if _layer(comp, "drums"):
            arr.warnings.append(f"{lineup.name}: drums left out (no percussion part)")
        arr.parts = _inner_difficulty(arr, difficulty)
        return arr
    cm = counter_part(lineup)
    if cm is not None:
        arr.parts[cm] = _place_smooth(counter, lineup.by_name(cm))

    # With the tune on the player's part (lead="seat"), the band's own lead joins the pads, and the
    # inner parts keep under the tune only while it is on top.
    ceiling = arr.parts[lead] if _tune_on_top(lineup) else []
    pads = [p for p in BAND_LEADS if p in names and p != lead] + [p for p in PAD_PARTS if p in names and p not in (lead, cm)]
    pad_slots = harmony_slots(strings + keys, end)
    if figuration:
        pad_slots = _figurate(pad_slots, [n.start for n in strings + keys])
    _voice_layer(arr, pad_slots, pads, ceiling, arr.parts[eb.name], 76, 0.8)

    choir_slots = harmony_slots(brass, end, max_pcs=3)
    if figuration:
        choir_slots = _figurate(choir_slots, [n.start for n in brass])
    _voice_layer(arr, choir_slots, [p for p in CHOIR_PARTS if p in names and p != lead], ceiling, arr.parts[eb.name],
                 79, 0.8)

    # Bass trombone reinforces the bass line only while the brass choir is playing.
    if "Bass Trombone" in names:
        btb = lineup.by_name("Bass Trombone")
        active = [(s, e) for s, e, _ in choir_slots]
        tutti = [n for n in bass if any(s <= n.start < e for s, e in active)]
        arr.parts[btb.name] = _place_line(tutti, btb, arr.warnings, prefer_low=True)

    if soprano and "Soprano Cornet" in names and lead in BAND_LEADS:
        arr.parts["Soprano Cornet"] = _soprano_doubling(arr.parts[lead], lineup.by_name("Soprano Cornet"),
                                                        _climax_spans(comp))

    drums = _layer(comp, "drums")
    if drums and "Percussion" in names:
        arr.parts["Percussion"] = sorted(drums, key=lambda n: n.start)
    arr.parts = apply_difficulty(arr.parts, lineup, difficulty)
    return arr
