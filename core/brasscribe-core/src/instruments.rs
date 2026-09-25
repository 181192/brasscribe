//! Brass-band instrument knowledge: transposition, clefs, ranges, roles.
//!
//! All pitches are MIDI numbers. Ranges are sounding (concert) pitch, taken
//! from MuseScore's instruments.xml: `pro` is the professional range (hard
//! limit), `comfortable` the amateur range (soft preference). `chromatic` is
//! sounding minus written, so written = sounding - chromatic.

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub enum Role {
    Melody,
    Countermelody,
    UpperHarmony,
    InnerHarmony,
    RhythmicSupport,
    Bass,
    Pedal,
    Solo,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Clef {
    Treble,
    Bass,
    Percussion,
}

impl Clef {
    pub fn as_str(self) -> &'static str {
        match self {
            Clef::Treble => "treble",
            Clef::Bass => "bass",
            Clef::Percussion => "percussion",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum RangeCheck {
    Ok,
    Uncomfortable,
    Impossible,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Instrument {
    pub id: &'static str,
    pub name: &'static str,
    pub short: &'static str,
    /// Sounding minus written, semitones.
    pub chromatic: i32,
    /// Sounding minus written, staff steps (MusicXML <diatonic>).
    pub diatonic: i32,
    pub clef: Clef,
    pub pro: (i32, i32),
    pub comfortable: (i32, i32),
    pub roles: &'static [Role],
    /// 0-based General MIDI program for playback.
    pub gm_program: i32,
    pub musescore_id: &'static str,
    pub section: &'static str,
    /// MusicXML <instrument-sound> id (MuseScore sound library naming).
    pub sound: &'static str,
}

impl Instrument {
    pub fn written(&self, sounding: i32) -> i32 {
        sounding - self.chromatic
    }

    pub fn sounding(&self, written: i32) -> i32 {
        written + self.chromatic
    }

    pub fn check(&self, sounding: i32) -> RangeCheck {
        let (lo, hi) = self.pro;
        if !(lo <= sounding && sounding <= hi) {
            return RangeCheck::Impossible;
        }
        let (clo, chi) = self.comfortable;
        if clo <= sounding && sounding <= chi {
            RangeCheck::Ok
        } else {
            RangeCheck::Uncomfortable
        }
    }

    /// Octave-displace a pitch into the comfortable range if possible, else the pro range.
    pub fn fit_octave(&self, sounding: i32) -> i32 {
        for (lo, hi) in [self.comfortable, self.pro] {
            let mut p = sounding;
            while p < lo {
                p += 12;
            }
            while p > hi {
                p -= 12;
            }
            if lo <= p && p <= hi {
                return p;
            }
        }
        sounding
    }

    pub fn is_percussion(&self) -> bool {
        self.clef == Clef::Percussion
    }
}

use Role::*;

pub static SOPRANO_CORNET: Instrument = Instrument {
    id: "eb-soprano-cornet", name: "Soprano Cornet in E♭", short: "Sop. Cnt.", chromatic: 3, diatonic: 2, clef: Clef::Treble,
    pro: (57, 87), comfortable: (57, 84), roles: &[Melody, UpperHarmony, Solo], gm_program: 56, musescore_id: "eb-cornet",
    section: "cornets", sound: "brass.cornet.soprano",
};
pub static CORNET: Instrument = Instrument {
    id: "bb-cornet", name: "Cornet in B♭", short: "Cnt.", chromatic: -2, diatonic: -1, clef: Clef::Treble,
    pro: (52, 82), comfortable: (52, 79), roles: &[Melody, Countermelody, UpperHarmony, InnerHarmony, RhythmicSupport, Solo],
    gm_program: 56, musescore_id: "bb-cornet", section: "cornets", sound: "brass.cornet",
};
pub static FLUGELHORN: Instrument = Instrument {
    id: "flugelhorn", name: "Flugelhorn in B♭", short: "Flug.", chromatic: -2, diatonic: -1, clef: Clef::Treble,
    pro: (52, 82), comfortable: (52, 79), roles: &[Melody, Countermelody, InnerHarmony, Solo], gm_program: 56,
    musescore_id: "flugelhorn", section: "horns", sound: "brass.flugelhorn",
};
pub static TENOR_HORN: Instrument = Instrument {
    id: "eb-tenor-horn", name: "Tenor Horn in E♭", short: "Hn.", chromatic: -9, diatonic: -5, clef: Clef::Treble,
    pro: (45, 75), comfortable: (45, 72), roles: &[Countermelody, InnerHarmony, RhythmicSupport, Melody, Solo], gm_program: 60,
    musescore_id: "eb-alto-horn", section: "horns", sound: "brass.alto-horn",
};
pub static BARITONE: Instrument = Instrument {
    id: "baritone", name: "Baritone in B♭", short: "Bar.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (40, 70), comfortable: (40, 67), roles: &[InnerHarmony, Countermelody, RhythmicSupport], gm_program: 58,
    musescore_id: "baritone-horn-treble", section: "baritones", sound: "brass.baritone-horn",
};
pub static TENOR_TROMBONE: Instrument = Instrument {
    id: "tenor-trombone", name: "Trombone in B♭", short: "Tbn.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (36, 74), comfortable: (40, 71), roles: &[InnerHarmony, RhythmicSupport, Countermelody, Melody], gm_program: 57,
    musescore_id: "trombone-treble", section: "trombones", sound: "brass.trombone",
};
pub static BASS_TROMBONE: Instrument = Instrument {
    id: "bass-trombone", name: "Bass Trombone", short: "B. Tbn.", chromatic: 0, diatonic: 0, clef: Clef::Bass,
    pro: (21, 77), comfortable: (32, 65), roles: &[Bass, InnerHarmony, RhythmicSupport], gm_program: 57,
    musescore_id: "bass-trombone", section: "trombones", sound: "brass.trombone.bass",
};
pub static EUPHONIUM: Instrument = Instrument {
    id: "euphonium", name: "Euphonium in B♭", short: "Euph.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (34, 74), comfortable: (40, 70), roles: &[Countermelody, Melody, Solo, InnerHarmony, Bass], gm_program: 58,
    musescore_id: "euphonium-treble", section: "euphoniums", sound: "brass.euphonium",
};
pub static EB_BASS: Instrument = Instrument {
    id: "eb-bass", name: "E♭ Tuba", short: "E♭ Bass", chromatic: -21, diatonic: -12, clef: Clef::Treble,
    pro: (24, 72), comfortable: (26, 64), roles: &[Bass, Pedal, RhythmicSupport], gm_program: 58,
    musescore_id: "eb-tuba-treble", section: "basses", sound: "brass.tuba",
};
pub static BB_BASS: Instrument = Instrument {
    id: "bb-bass", name: "B♭ Tuba", short: "B♭ Bass", chromatic: -26, diatonic: -15, clef: Clef::Treble,
    pro: (22, 72), comfortable: (28, 58), roles: &[Bass, Pedal], gm_program: 58, musescore_id: "bb-tuba-treble",
    section: "basses", sound: "brass.tuba",
};
pub static PERCUSSION: Instrument = Instrument {
    id: "drum-kit", name: "Drum Kit", short: "Dr.", chromatic: 0, diatonic: 0, clef: Clef::Percussion,
    pro: (0, 127), comfortable: (0, 127), roles: &[RhythmicSupport], gm_program: 0, musescore_id: "drumset",
    section: "percussion", sound: "drum.group.set",
};

pub static INSTRUMENTS: [&Instrument; 11] = [
    &SOPRANO_CORNET, &CORNET, &FLUGELHORN, &TENOR_HORN, &BARITONE, &TENOR_TROMBONE, &BASS_TROMBONE, &EUPHONIUM, &EB_BASS,
    &BB_BASS, &PERCUSSION,
];

pub fn instrument(id: &str) -> Option<&'static Instrument> {
    INSTRUMENTS.iter().copied().find(|i| i.id == id)
}

#[derive(Debug, Clone, PartialEq)]
pub struct Part {
    pub name: &'static str,
    pub instrument: &'static Instrument,
    pub players: u32,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Lineup {
    pub name: &'static str,
    pub parts: Vec<Part>,
}

impl Lineup {
    pub fn by_name(&self, name: &str) -> &Part {
        self.parts.iter().find(|p| p.name == name).unwrap_or_else(|| panic!("no part {name}"))
    }

    pub fn has(&self, name: &str) -> bool {
        self.parts.iter().any(|p| p.name == name)
    }
}

fn p(name: &'static str, inst: &'static Instrument, players: u32) -> Part {
    Part { name, instrument: inst, players }
}

/// Standard British/Norwegian contest band, in conventional score order.
pub fn brass_band() -> Lineup {
    Lineup {
        name: "Brass band",
        parts: vec![
            p("Soprano Cornet", &SOPRANO_CORNET, 1),
            p("Solo Cornet", &CORNET, 4),
            p("Repiano Cornet", &CORNET, 1),
            p("2nd Cornet", &CORNET, 2),
            p("3rd Cornet", &CORNET, 2),
            p("Flugelhorn", &FLUGELHORN, 1),
            p("Solo Horn", &TENOR_HORN, 1),
            p("1st Horn", &TENOR_HORN, 1),
            p("2nd Horn", &TENOR_HORN, 1),
            p("1st Baritone", &BARITONE, 1),
            p("2nd Baritone", &BARITONE, 1),
            p("1st Trombone", &TENOR_TROMBONE, 1),
            p("2nd Trombone", &TENOR_TROMBONE, 1),
            p("Bass Trombone", &BASS_TROMBONE, 1),
            p("Euphonium", &EUPHONIUM, 2),
            p("E♭ Bass", &EB_BASS, 2),
            p("B♭ Bass", &BB_BASS, 2),
            p("Percussion", &PERCUSSION, 1),
        ],
    }
}

/// Reduced ensemble for the minimal arranger.
pub fn minimal_band() -> Lineup {
    Lineup {
        name: "Minimal brass",
        parts: vec![
            p("Solo Cornet", &CORNET, 1),
            p("2nd Cornet", &CORNET, 1),
            p("Flugelhorn", &FLUGELHORN, 1),
            p("Solo Horn", &TENOR_HORN, 1),
            p("1st Trombone", &TENOR_TROMBONE, 1),
            p("Euphonium", &EUPHONIUM, 1),
            p("E♭ Bass", &EB_BASS, 1),
            p("B♭ Bass", &BB_BASS, 1),
        ],
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct RangeIssue {
    pub part: String,
    pub index: usize,
    pub sounding: i32,
    pub written: i32,
    pub level: RangeCheck,
}

pub fn validate_range(part: &Part, sounding: &[i32]) -> Vec<RangeIssue> {
    sounding
        .iter()
        .enumerate()
        .filter_map(|(i, &p)| {
            let level = part.instrument.check(p);
            (level != RangeCheck::Ok).then(|| RangeIssue { part: part.name.to_string(), index: i, sounding: p, written: part.instrument.written(p), level })
        })
        .collect()
}
