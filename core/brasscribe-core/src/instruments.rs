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
    /// Sounding, preferred placement (easy to read); default comfortable.
    pub reading: Option<(i32, i32)>,
    /// Sounding, placement never goes past this; default pro.
    pub reading_limit: Option<(i32, i32)>,
}

impl Instrument {
    /// Where the arranger places notes by preference.
    pub fn preferred(&self) -> (i32, i32) {
        self.reading.unwrap_or(self.comfortable)
    }

    /// The range placement never leaves.
    pub fn placement_limit(&self) -> (i32, i32) {
        self.reading_limit.unwrap_or(self.pro)
    }

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
    section: "cornets", sound: "brass.cornet.soprano",    reading: Some((63, 84)), reading_limit: None,
};
pub static CORNET: Instrument = Instrument {
    id: "bb-cornet", name: "Cornet in B♭", short: "Cnt.", chromatic: -2, diatonic: -1, clef: Clef::Treble,
    pro: (52, 82), comfortable: (52, 79), roles: &[Melody, Countermelody, UpperHarmony, InnerHarmony, RhythmicSupport, Solo],
    gm_program: 56, musescore_id: "bb-cornet", section: "cornets", sound: "brass.cornet",    reading: Some((55, 79)), reading_limit: Some((52, 84)),
};
pub static FLUGELHORN: Instrument = Instrument {
    id: "flugelhorn", name: "Flugelhorn in B♭", short: "Flug.", chromatic: -2, diatonic: -1, clef: Clef::Treble,
    pro: (52, 82), comfortable: (52, 79), roles: &[Melody, Countermelody, InnerHarmony, Solo], gm_program: 56,
    musescore_id: "flugelhorn", section: "horns", sound: "brass.flugelhorn",    reading: Some((55, 77)), reading_limit: None,
};
pub static TENOR_HORN: Instrument = Instrument {
    id: "eb-tenor-horn", name: "Tenor Horn in E♭", short: "Hn.", chromatic: -9, diatonic: -5, clef: Clef::Treble,
    pro: (45, 75), comfortable: (45, 72), roles: &[Countermelody, InnerHarmony, RhythmicSupport, Melody, Solo], gm_program: 60,
    musescore_id: "eb-alto-horn", section: "horns", sound: "brass.alto-horn",    reading: Some((48, 70)), reading_limit: None,
};
pub static BARITONE: Instrument = Instrument {
    id: "baritone", name: "Baritone in B♭", short: "Bar.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (40, 70), comfortable: (40, 67), roles: &[InnerHarmony, Countermelody, RhythmicSupport], gm_program: 58,
    musescore_id: "baritone-horn-treble", section: "baritones", sound: "brass.baritone-horn",    reading: Some((43, 65)), reading_limit: None,
};
pub static TENOR_TROMBONE: Instrument = Instrument {
    id: "tenor-trombone", name: "Trombone in B♭", short: "Tbn.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (36, 74), comfortable: (40, 71), roles: &[InnerHarmony, RhythmicSupport, Countermelody, Melody], gm_program: 57,
    musescore_id: "trombone-treble", section: "trombones", sound: "brass.trombone",    reading: Some((43, 67)), reading_limit: Some((40, 72)),
};
pub static BASS_TROMBONE: Instrument = Instrument {
    id: "bass-trombone", name: "Bass Trombone", short: "B. Tbn.", chromatic: 0, diatonic: 0, clef: Clef::Bass,
    pro: (21, 77), comfortable: (32, 65), roles: &[Bass, InnerHarmony, RhythmicSupport], gm_program: 57,
    musescore_id: "bass-trombone", section: "trombones", sound: "brass.trombone.bass",    reading: Some((36, 60)), reading_limit: Some((28, 65)),
};
pub static EUPHONIUM: Instrument = Instrument {
    id: "euphonium", name: "Euphonium in B♭", short: "Euph.", chromatic: -14, diatonic: -8, clef: Clef::Treble,
    pro: (34, 74), comfortable: (40, 70), roles: &[Countermelody, Melody, Solo, InnerHarmony, Bass], gm_program: 58,
    musescore_id: "euphonium-treble", section: "euphoniums", sound: "brass.euphonium",    reading: Some((40, 67)), reading_limit: Some((34, 72)),
};
pub static EB_BASS: Instrument = Instrument {
    id: "eb-bass", name: "E♭ Tuba", short: "E♭ Bass", chromatic: -21, diatonic: -12, clef: Clef::Treble,
    pro: (24, 72), comfortable: (26, 64), roles: &[Bass, Pedal, RhythmicSupport], gm_program: 58,
    musescore_id: "eb-tuba-treble", section: "basses", sound: "brass.tuba",    reading: Some((33, 53)), reading_limit: Some((27, 58)),
};
pub static BB_BASS: Instrument = Instrument {
    id: "bb-bass", name: "B♭ Tuba", short: "B♭ Bass", chromatic: -26, diatonic: -15, clef: Clef::Treble,
    pro: (22, 72), comfortable: (28, 58), roles: &[Bass, Pedal], gm_program: 58, musescore_id: "bb-tuba-treble",
    section: "basses", sound: "brass.tuba",    reading: Some((28, 48)), reading_limit: Some((22, 53)),
};
pub static PERCUSSION: Instrument = Instrument {
    id: "drum-kit", name: "Drum Kit", short: "Dr.", chromatic: 0, diatonic: 0, clef: Clef::Percussion,
    pro: (0, 127), comfortable: (0, 127), roles: &[RhythmicSupport], gm_program: 0, musescore_id: "drumset",
    section: "percussion", sound: "drum.group.set",    reading: None, reading_limit: None,
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
    /// Staff label after the first system; distinct per part (default: the instrument's).
    pub short: &'static str,
    /// 1-based MusicXML <midi-bank> of this part's preset in the band SoundFont.
    pub midi_bank: Option<i64>,
}

impl Part {
    pub fn abbreviation(&self) -> &'static str {
        if self.short.is_empty() {
            self.instrument.short
        } else {
            self.short
        }
    }
}

/// An ensemble in score order, with the roles the arrangers need.
///
/// `lead` plays the melody (the solo layer), `bass` the bass line and
/// `second_bass`, if any, the bass an octave lower where that stays readable.
/// With `satb` the lineup is a four-part group: the parts between lead and
/// bass are voiced together as alto and tenor (`arranger::voice_satb`).
#[derive(Debug, Clone, PartialEq)]
pub struct Lineup {
    pub name: &'static str,
    pub parts: Vec<Part>,
    pub lead: &'static str,
    pub bass: &'static str,
    pub second_bass: Option<&'static str>,
    pub satb: bool,
}

impl Lineup {
    pub fn lead_part(&self) -> &Part {
        self.by_name(self.lead)
    }

    pub fn bass_part(&self) -> &Part {
        self.by_name(self.bass)
    }

    pub fn second_bass_part(&self) -> Option<&Part> {
        self.second_bass.map(|n| self.by_name(n))
    }

    pub fn by_name(&self, name: &str) -> &Part {
        self.parts.iter().find(|p| p.name == name).unwrap_or_else(|| panic!("no part {name}"))
    }

    pub fn has(&self, name: &str) -> bool {
        self.parts.iter().any(|p| p.name == name)
    }
}

fn p(name: &'static str, inst: &'static Instrument, players: u32) -> Part {
    Part { name, instrument: inst, players, short: "", midi_bank: None }
}

fn ps(name: &'static str, inst: &'static Instrument, players: u32, short: &'static str, bank: Option<i64>) -> Part {
    Part { name, instrument: inst, players, short, midi_bank: bank }
}

/// Standard British/Norwegian contest band, in conventional score order.
pub fn brass_band() -> Lineup {
    Lineup {
        name: "Brass band",
        parts: vec![
            ps("Soprano Cornet", &SOPRANO_CORNET, 1, "Sop. Cnt.", Some(2)),
            ps("Solo Cornet", &CORNET, 4, "Solo Cnt.", Some(1)),
            ps("Repiano Cornet", &CORNET, 1, "Rep.", Some(3)),
            ps("2nd Cornet", &CORNET, 2, "2nd Cnt.", Some(4)),
            ps("3rd Cornet", &CORNET, 2, "3rd Cnt.", Some(5)),
            ps("Flugelhorn", &FLUGELHORN, 1, "Flug.", Some(6)),
            ps("Solo Horn", &TENOR_HORN, 1, "Solo Hn.", Some(1)),
            ps("1st Horn", &TENOR_HORN, 1, "1st Hn.", Some(2)),
            ps("2nd Horn", &TENOR_HORN, 1, "2nd Hn.", Some(3)),
            ps("1st Baritone", &BARITONE, 1, "1st Bar.", Some(4)),
            ps("2nd Baritone", &BARITONE, 1, "2nd Bar.", Some(5)),
            ps("1st Trombone", &TENOR_TROMBONE, 1, "1st Tbn.", Some(1)),
            ps("2nd Trombone", &TENOR_TROMBONE, 1, "2nd Tbn.", Some(2)),
            ps("Bass Trombone", &BASS_TROMBONE, 1, "B. Tbn.", Some(3)),
            ps("Euphonium", &EUPHONIUM, 2, "Euph.", Some(3)),
            ps("E♭ Bass", &EB_BASS, 2, "E♭ Bass", Some(1)),
            ps("B♭ Bass", &BB_BASS, 2, "B♭ Bass", Some(2)),
            ps("Percussion", &PERCUSSION, 1, "Perc.", None),
        ],
        lead: "Solo Cornet",
        bass: "E♭ Bass",
        second_bass: Some("B♭ Bass"),
        satb: false,
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
        lead: "Solo Cornet",
        bass: "E♭ Bass",
        second_bass: Some("B♭ Bass"),
        satb: false,
    }
}

/// Brass quartet of the British brass-band tradition: one player per part, melody on top, the
/// Euphonium as the bass, 2nd Cornet and Tenor Horn voiced as alto and tenor.
pub fn quartet() -> Lineup {
    Lineup {
        name: "Brass quartet",
        parts: vec![
            ps("1st Cornet", &CORNET, 1, "1st Cnt.", Some(1)),
            ps("2nd Cornet", &CORNET, 1, "2nd Cnt.", Some(4)),
            ps("Tenor Horn", &TENOR_HORN, 1, "Ten. Hn.", Some(1)),
            ps("Euphonium", &EUPHONIUM, 1, "Euph.", Some(3)),
        ],
        lead: "1st Cornet",
        bass: "Euphonium",
        second_bass: None,
        satb: true,
    }
}

/// Lineup option values: "band" (the default; "full" and "" are aliases), "minimal" and "quartet".
pub const LINEUP_KEYS: [&str; 3] = ["band", "minimal", "quartet"];

/// The canonical option value of a lineup name ("full" and "" -> "band").
pub fn lineup_key(name: &str) -> Result<&'static str, String> {
    match name {
        "" | "band" | "full" => Ok("band"),
        "minimal" => Ok("minimal"),
        "quartet" => Ok("quartet"),
        other => Err(format!("unknown lineup {other}")),
    }
}

/// The lineup for an option value (see [`lineup_key`]).
pub fn lineup_by_name(name: &str) -> Result<Lineup, String> {
    Ok(match lineup_key(name)? {
        "minimal" => minimal_band(),
        "quartet" => quartet(),
        _ => brass_band(),
    })
}

/// 1-based MusicXML <midi-bank> per part name, over every lineup. A part name
/// means the same preset in every lineup, so one table serves any
/// arrangement; parts of a lineup without their own bank take the band's.
pub fn part_banks() -> Vec<(&'static str, i64)> {
    let mut out: Vec<(&'static str, i64)> = Vec::new();
    for key in LINEUP_KEYS {
        for p in lineup_by_name(key).expect("known lineup").parts {
            if let Some(b) = p.midi_bank {
                if !out.iter().any(|(n, _)| *n == p.name) {
                    out.push((p.name, b));
                }
            }
        }
    }
    out
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
