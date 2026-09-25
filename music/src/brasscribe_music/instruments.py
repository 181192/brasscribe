"""Brass-band instrument knowledge: transposition, clefs, ranges, roles.

All pitches are MIDI numbers. Ranges are *sounding* (concert) pitch for a
British-style brass band: `pro` is the extreme range (hard limit), `comfortable`
the range an amateur player reads and tunes easily (soft preference). They are
the written ranges of qa/tools/musicxml_readability.py (RANGES) converted to
concert pitch, e.g. cornet and horn comfortable from written A3 rather than the
bottom valve note F♯3, and E♭/B♭ Bass comfortable up to written D5. Those
ranges are heuristic defaults still to be confirmed by players. Transposition follows the
MuseScore/MusicXML convention: `chromatic` is sounding minus written, so
written = sounding - chromatic. Everything here is deterministic; nothing
about transposition or range should ever be left to a model.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class Role(str, Enum):
    MELODY = "melody"
    COUNTERMELODY = "countermelody"
    UPPER_HARMONY = "upperHarmony"
    INNER_HARMONY = "innerHarmony"
    RHYTHMIC_SUPPORT = "rhythmicSupport"
    BASS = "bass"
    PEDAL = "pedal"
    SOLO = "solo"


@dataclass(frozen=True)
class Instrument:
    id: str
    name: str
    short: str
    chromatic: int  # sounding - written, semitones
    diatonic: int  # sounding - written, staff steps (MusicXML <diatonic>)
    clef: str  # "treble" | "bass"
    pro: tuple[int, int]  # sounding, hard limit
    comfortable: tuple[int, int]  # sounding, soft preference
    roles: frozenset[Role]
    gm_program: int  # 0-based General MIDI program for playback
    musescore_id: str
    section: str
    sound: str = ""  # MusicXML <instrument-sound> id (MuseScore sound library naming)

    def written(self, sounding: int) -> int:
        return sounding - self.chromatic

    def sounding(self, written: int) -> int:
        return written + self.chromatic

    def check(self, sounding: int) -> str:
        """'ok', 'uncomfortable' (outside comfortable, inside pro) or 'impossible'."""
        lo, hi = self.pro
        if not lo <= sounding <= hi:
            return "impossible"
        clo, chi = self.comfortable
        return "ok" if clo <= sounding <= chi else "uncomfortable"

    def fit_octave(self, sounding: int) -> int:
        """Octave-displace a pitch into the comfortable range if possible, else the pro range."""
        for lo, hi in (self.comfortable, self.pro):
            p = sounding
            while p < lo:
                p += 12
            while p > hi:
                p -= 12
            if lo <= p <= hi:
                return p
        return sounding


R = Role
_INSTRUMENTS = [
    Instrument("eb-soprano-cornet", "Soprano Cornet in E♭", "Sop. Cnt.", 3, 2, "treble", (57, 87), (63, 84),
               frozenset({R.MELODY, R.UPPER_HARMONY, R.SOLO}), 56, "eb-cornet", "cornets", "brass.cornet.soprano"),
    Instrument("bb-cornet", "Cornet in B♭", "Cnt.", -2, -1, "treble", (52, 84), (55, 79),
               frozenset({R.MELODY, R.COUNTERMELODY, R.UPPER_HARMONY, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.SOLO}), 56, "bb-cornet", "cornets", "brass.cornet"),
    Instrument("flugelhorn", "Flugelhorn in B♭", "Flug.", -2, -1, "treble", (52, 82), (55, 77),
               frozenset({R.MELODY, R.COUNTERMELODY, R.INNER_HARMONY, R.SOLO}), 56, "flugelhorn", "horns", "brass.flugelhorn"),
    Instrument("eb-tenor-horn", "Tenor Horn in E♭", "Hn.", -9, -5, "treble", (45, 75), (48, 70),
               frozenset({R.COUNTERMELODY, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.MELODY, R.SOLO}), 60, "eb-alto-horn", "horns", "brass.alto-horn"),
    Instrument("baritone", "Baritone in B♭", "Bar.", -14, -8, "treble", (40, 70), (43, 65),
               frozenset({R.INNER_HARMONY, R.COUNTERMELODY, R.RHYTHMIC_SUPPORT}), 58, "baritone-horn-treble", "baritones", "brass.baritone-horn"),
    Instrument("tenor-trombone", "Trombone in B♭", "Tbn.", -14, -8, "treble", (40, 72), (43, 67),
               frozenset({R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.COUNTERMELODY, R.MELODY}), 57, "trombone-treble", "trombones", "brass.trombone"),
    Instrument("bass-trombone", "Bass Trombone", "B. Tbn.", 0, 0, "bass", (28, 65), (36, 60),
               frozenset({R.BASS, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT}), 57, "bass-trombone", "trombones", "brass.trombone.bass"),
    Instrument("euphonium", "Euphonium in B♭", "Euph.", -14, -8, "treble", (34, 72), (40, 67),
               frozenset({R.COUNTERMELODY, R.MELODY, R.SOLO, R.INNER_HARMONY, R.BASS}), 58, "euphonium-treble", "euphoniums", "brass.euphonium"),
    Instrument("eb-bass", "E♭ Tuba", "E♭ Bass", -21, -12, "treble", (27, 58), (33, 53),
               frozenset({R.BASS, R.PEDAL, R.RHYTHMIC_SUPPORT}), 58, "eb-tuba-treble", "basses", "brass.tuba"),
    Instrument("bb-bass", "B♭ Tuba", "B♭ Bass", -26, -15, "treble", (22, 53), (28, 48),
               frozenset({R.BASS, R.PEDAL}), 58, "bb-tuba-treble", "basses", "brass.tuba"),
]
PERCUSSION = Instrument("drum-kit", "Drum Kit", "Dr.", 0, 0, "percussion", (0, 127), (0, 127),
                        frozenset({R.RHYTHMIC_SUPPORT}), 0, "drumset", "percussion", "drum.group.set")
_INSTRUMENTS.append(PERCUSSION)
INSTRUMENTS: dict[str, Instrument] = {i.id: i for i in _INSTRUMENTS}


@dataclass(frozen=True)
class Part:
    name: str
    instrument: Instrument
    players: int = 1
    short: str = ""  # staff label after the first system; distinct per part (default: the instrument's)

    @property
    def abbreviation(self) -> str:
        return self.short or self.instrument.short


@dataclass
class Lineup:
    name: str
    parts: list[Part] = field(default_factory=list)

    def by_name(self, name: str) -> Part:
        return next(p for p in self.parts if p.name == name)


def _p(name: str, inst: str, players: int = 1, short: str = "") -> Part:
    return Part(name, INSTRUMENTS[inst], players, short)


# Standard British/Norwegian contest band, in conventional score order.
BRASS_BAND = Lineup("Brass band", [
    _p("Soprano Cornet", "eb-soprano-cornet", 1, "Sop. Cnt."),
    _p("Solo Cornet", "bb-cornet", 4, "Solo Cnt."),
    _p("Repiano Cornet", "bb-cornet", 1, "Rep."),
    _p("2nd Cornet", "bb-cornet", 2, "2nd Cnt."),
    _p("3rd Cornet", "bb-cornet", 2, "3rd Cnt."),
    _p("Flugelhorn", "flugelhorn", 1, "Flug."),
    _p("Solo Horn", "eb-tenor-horn", 1, "Solo Hn."),
    _p("1st Horn", "eb-tenor-horn", 1, "1st Hn."),
    _p("2nd Horn", "eb-tenor-horn", 1, "2nd Hn."),
    _p("1st Baritone", "baritone", 1, "1st Bar."),
    _p("2nd Baritone", "baritone", 1, "2nd Bar."),
    _p("1st Trombone", "tenor-trombone", 1, "1st Tbn."),
    _p("2nd Trombone", "tenor-trombone", 1, "2nd Tbn."),
    _p("Bass Trombone", "bass-trombone", 1, "B. Tbn."),
    _p("Euphonium", "euphonium", 2, "Euph."),
    _p("E♭ Bass", "eb-bass", 2, "E♭ Bass"),
    _p("B♭ Bass", "bb-bass", 2, "B♭ Bass"),
    _p("Percussion", "drum-kit", 1, "Perc."),
])

# Reduced ensemble for the first arranger milestone.
MINIMAL_BAND = Lineup("Minimal brass", [
    _p("Solo Cornet", "bb-cornet"),
    _p("2nd Cornet", "bb-cornet"),
    _p("Flugelhorn", "flugelhorn"),
    _p("Solo Horn", "eb-tenor-horn"),
    _p("1st Trombone", "tenor-trombone"),
    _p("Euphonium", "euphonium"),
    _p("E♭ Bass", "eb-bass"),
    _p("B♭ Bass", "bb-bass"),
])


@dataclass(frozen=True)
class RangeIssue:
    part: str
    index: int
    sounding: int
    written: int
    level: str  # "uncomfortable" | "impossible"


def validate_range(part: Part, sounding_pitches: list[int]) -> list[RangeIssue]:
    issues = []
    for i, p in enumerate(sounding_pitches):
        level = part.instrument.check(p)
        if level != "ok":
            issues.append(RangeIssue(part.name, i, p, part.instrument.written(p), level))
    return issues
