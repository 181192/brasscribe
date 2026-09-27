"""Brass-band instrument knowledge: transposition, clefs, ranges, roles.

All pitches are MIDI numbers. Ranges are *sounding* (concert) pitch, taken from
MuseScore's instruments.xml: `pro` is its professional range (hard limit),
`comfortable` its amateur range (what a player can play; range checks use it).
`reading` is narrower: where the arranger places notes by preference, so parts
stay off the ledger lines, and `reading_limit` bounds its placement (the
extreme reading range). They are the written comfort and extreme ranges of
qa/tools/musicxml_readability.py (RANGES) at concert pitch, e.g. cornet and horn
from written A3 rather than the bottom valve note F♯3, E♭/B♭ Bass up to written
D5; heuristic defaults still to be confirmed by players. Transposition follows the
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
    reading: tuple[int, int] | None = None  # sounding, preferred placement (easy to read); default comfortable
    reading_limit: tuple[int, int] | None = None  # sounding, placement never goes past this; default pro

    @property
    def preferred(self) -> tuple[int, int]:
        return self.reading or self.comfortable

    @property
    def placement_limit(self) -> tuple[int, int]:
        return self.reading_limit or self.pro

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
    Instrument("eb-soprano-cornet", "Soprano Cornet in E♭", "Sop. Cnt.", 3, 2, "treble", (57, 87), (57, 84),
               frozenset({R.MELODY, R.UPPER_HARMONY, R.SOLO}), 56, "eb-cornet", "cornets", "brass.cornet.soprano", reading=(63, 84)),
    Instrument("bb-cornet", "Cornet in B♭", "Cnt.", -2, -1, "treble", (52, 82), (52, 79),
               frozenset({R.MELODY, R.COUNTERMELODY, R.UPPER_HARMONY, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.SOLO}), 56, "bb-cornet", "cornets", "brass.cornet", reading=(55, 79), reading_limit=(52, 84)),
    Instrument("flugelhorn", "Flugelhorn in B♭", "Flug.", -2, -1, "treble", (52, 82), (52, 79),
               frozenset({R.MELODY, R.COUNTERMELODY, R.INNER_HARMONY, R.SOLO}), 56, "flugelhorn", "horns", "brass.flugelhorn", reading=(55, 77)),
    Instrument("eb-tenor-horn", "Tenor Horn in E♭", "Hn.", -9, -5, "treble", (45, 75), (45, 72),
               frozenset({R.COUNTERMELODY, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.MELODY, R.SOLO}), 60, "eb-alto-horn", "horns", "brass.alto-horn", reading=(48, 70)),
    Instrument("baritone", "Baritone in B♭", "Bar.", -14, -8, "treble", (40, 70), (40, 67),
               frozenset({R.INNER_HARMONY, R.COUNTERMELODY, R.RHYTHMIC_SUPPORT}), 58, "baritone-horn-treble", "baritones", "brass.baritone-horn", reading=(43, 65)),
    Instrument("tenor-trombone", "Trombone in B♭", "Tbn.", -14, -8, "treble", (36, 74), (40, 71),
               frozenset({R.INNER_HARMONY, R.RHYTHMIC_SUPPORT, R.COUNTERMELODY, R.MELODY}), 57, "trombone-treble", "trombones", "brass.trombone", reading=(43, 67), reading_limit=(40, 72)),
    Instrument("bass-trombone", "Bass Trombone", "B. Tbn.", 0, 0, "bass", (21, 77), (32, 65),
               frozenset({R.BASS, R.INNER_HARMONY, R.RHYTHMIC_SUPPORT}), 57, "bass-trombone", "trombones", "brass.trombone.bass", reading=(36, 60), reading_limit=(28, 65)),
    Instrument("euphonium", "Euphonium in B♭", "Euph.", -14, -8, "treble", (34, 74), (40, 70),
               frozenset({R.COUNTERMELODY, R.MELODY, R.SOLO, R.INNER_HARMONY, R.BASS}), 58, "euphonium-treble", "euphoniums", "brass.euphonium", reading=(40, 67), reading_limit=(34, 72)),
    Instrument("eb-bass", "E♭ Tuba", "E♭ Bass", -21, -12, "treble", (24, 72), (26, 64),
               frozenset({R.BASS, R.PEDAL, R.RHYTHMIC_SUPPORT}), 58, "eb-tuba-treble", "basses", "brass.tuba", reading=(33, 53), reading_limit=(27, 58)),
    Instrument("bb-bass", "B♭ Tuba", "B♭ Bass", -26, -15, "treble", (22, 72), (28, 58),
               frozenset({R.BASS, R.PEDAL}), 58, "bb-tuba-treble", "basses", "brass.tuba", reading=(28, 48), reading_limit=(22, 53)),
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
    midi_bank: int | None = None  # 1-based MusicXML <midi-bank> of this part's preset in the band SoundFont

    @property
    def abbreviation(self) -> str:
        return self.short or self.instrument.short


@dataclass
class Lineup:
    """An ensemble in score order, with the roles the arrangers need.

    `lead` plays the melody (the solo layer), `bass` the bass line and
    `second_bass`, if any, the bass an octave lower where that stays readable.
    With `satb` the lineup is a four-part group: the parts between lead and
    bass are voiced together as alto and tenor (arranger.voice_satb).
    """

    name: str
    parts: list[Part] = field(default_factory=list)
    lead: str = "Solo Cornet"
    bass: str = "E♭ Bass"
    second_bass: str | None = "B♭ Bass"
    satb: bool = False

    def by_name(self, name: str) -> Part:
        return next(p for p in self.parts if p.name == name)

    def has(self, name: str) -> bool:
        return any(p.name == name for p in self.parts)

    @property
    def lead_part(self) -> Part:
        return self.by_name(self.lead)

    @property
    def bass_part(self) -> Part:
        return self.by_name(self.bass)

    @property
    def second_bass_part(self) -> Part | None:
        return self.by_name(self.second_bass) if self.second_bass else None


def _p(name: str, inst: str, players: int = 1, short: str = "", bank: int | None = None) -> Part:
    return Part(name, INSTRUMENTS[inst], players, short, bank)


# Standard British/Norwegian contest band, in conventional score order.
BRASS_BAND = Lineup("Brass band", [
    # Banks: the part's preset in the band SoundFont (sounds/mapping.json band_soundfont.musicxml).
    _p("Soprano Cornet", "eb-soprano-cornet", 1, "Sop. Cnt.", 2),
    _p("Solo Cornet", "bb-cornet", 4, "Solo Cnt.", 1),
    _p("Repiano Cornet", "bb-cornet", 1, "Rep.", 3),
    _p("2nd Cornet", "bb-cornet", 2, "2nd Cnt.", 4),
    _p("3rd Cornet", "bb-cornet", 2, "3rd Cnt.", 5),
    _p("Flugelhorn", "flugelhorn", 1, "Flug.", 6),
    _p("Solo Horn", "eb-tenor-horn", 1, "Solo Hn.", 1),
    _p("1st Horn", "eb-tenor-horn", 1, "1st Hn.", 2),
    _p("2nd Horn", "eb-tenor-horn", 1, "2nd Hn.", 3),
    _p("1st Baritone", "baritone", 1, "1st Bar.", 4),
    _p("2nd Baritone", "baritone", 1, "2nd Bar.", 5),
    _p("1st Trombone", "tenor-trombone", 1, "1st Tbn.", 1),
    _p("2nd Trombone", "tenor-trombone", 1, "2nd Tbn.", 2),
    _p("Bass Trombone", "bass-trombone", 1, "B. Tbn.", 3),
    _p("Euphonium", "euphonium", 2, "Euph.", 3),
    _p("E♭ Bass", "eb-bass", 2, "E♭ Bass", 1),
    _p("B♭ Bass", "bb-bass", 2, "B♭ Bass", 2),
    _p("Percussion", "drum-kit", 1, "Perc."),
], lead="Solo Cornet", bass="E♭ Bass", second_bass="B♭ Bass")

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
], lead="Solo Cornet", bass="E♭ Bass", second_bass="B♭ Bass")

# Brass quartet of the British brass-band tradition: one player per part, melody on top,
# the Euphonium as the bass, 2nd Cornet and Tenor Horn voiced as alto and tenor.
QUARTET = Lineup("Brass quartet", [
    _p("1st Cornet", "bb-cornet", 1, "1st Cnt.", 1),
    _p("2nd Cornet", "bb-cornet", 1, "2nd Cnt.", 4),
    _p("Tenor Horn", "eb-tenor-horn", 1, "Ten. Hn.", 1),
    _p("Euphonium", "euphonium", 1, "Euph.", 3),
], lead="1st Cornet", bass="Euphonium", second_bass=None, satb=True)

LINEUPS: dict[str, Lineup] = {"band": BRASS_BAND, "minimal": MINIMAL_BAND, "quartet": QUARTET}
LINEUP_ALIASES = {"full": "band"}


def lineup_by_name(name: str | None) -> Lineup:
    """The lineup for an option value: band (= full, the default), minimal, quartet."""
    key = LINEUP_ALIASES.get(name or "band", name or "band")
    if key not in LINEUPS:
        raise ValueError(f"unknown lineup {name}; one of {', '.join([*LINEUPS, *LINEUP_ALIASES])}")
    return LINEUPS[key]


def lineup_key(lineup: Lineup) -> str:
    """The option value of a lineup (band, minimal, quartet)."""
    return next(k for k, v in LINEUPS.items() if v is lineup)


def part_banks() -> dict[str, int]:
    """1-based MusicXML <midi-bank> per part name, over every lineup.

    A part name means the same preset in every lineup (tests check that no
    name maps to two banks), so one table serves any arrangement. Parts of a
    lineup without their own bank (the minimal band) take the band's.
    """
    banks: dict[str, int] = {}
    for lineup in LINEUPS.values():
        for p in lineup.parts:
            if p.midi_bank is not None:
                banks.setdefault(p.name, p.midi_bank)
    return banks


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
