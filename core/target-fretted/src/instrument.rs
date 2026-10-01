//! Instruments and tunings as data: open pitches per string, fret count, scale length and capo.
//!
//! Strings are numbered from 1, the highest-sounding line in tab. Pitch order is never assumed from
//! the string number: a re-entrant ukulele has its 4th string higher than its 3rd, and every rule
//! here reads the per-string open pitch.
//!
//! Frets in a [`Position`] are relative to the capo (0 = the open string, capo'd or not). Internally
//! the neck is addressed by the physical fret counted from the nut, in `i32`.

use serde::{Deserialize, Serialize};

/// The most strings (or courses) an instrument may have.
pub const MAX_STRINGS: usize = 12;

/// One string (or course of paired strings) as it sounds open.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct StringSpec {
    /// Concert MIDI pitch of the open string without a capo.
    pub open_pitch: i32,
    /// The neck fret the string starts at: 0 for a full-length string, 5 for a banjo's short 5th
    /// string. Frets 1 to `first_fret` do not exist on that string; fret numbers above it are counted
    /// as on the full neck, so the short string's first fret is written `first_fret + 1`.
    #[serde(default)]
    pub first_fret: u8,
}

impl StringSpec {
    pub fn new(open_pitch: i32) -> Self {
        StringSpec { open_pitch, first_fret: 0 }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Tuning {
    pub name: String,
    /// String 1 first: the highest line in tab.
    pub strings: Vec<StringSpec>,
}

impl Tuning {
    /// A tuning from open pitches, string 1 first.
    pub fn from_pitches(name: &str, pitches: &[i32]) -> Self {
        Tuning { name: name.into(), strings: pitches.iter().map(|&p| StringSpec::new(p)).collect() }
    }
}

/// The clef an instrument is written in on a notation staff. Pitches are written as they sound;
/// the `8vb` clefs carry the octave an instrument is written above its sound.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum NotationClef {
    Treble,
    /// Treble clef sounding an octave lower: guitar.
    #[serde(rename = "treble-8vb")]
    Treble8vb,
    /// Bass clef sounding an octave lower: bass guitar.
    #[serde(rename = "bass-8vb")]
    Bass8vb,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Instrument {
    pub name: String,
    pub tuning: Tuning,
    /// Frets on the neck, counted from the nut.
    pub frets: u8,
    /// Nut to saddle, in millimetres; hand spans are measured on it.
    pub scale_length_mm: f64,
    /// Capo fret; 0 = no capo. It raises every full-length string by this many semitones.
    #[serde(default)]
    pub capo: u8,
    /// The clef of the notation staff. None (a custom instrument that does not say) picks one from
    /// the open strings: see [`Instrument::notation_clef`].
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub notation: Option<NotationClef>,
}

/// Where a note is played: string (1 = highest tab line) and fret relative to the capo (0 = open).
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, PartialOrd, Ord, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Position {
    pub string: u8,
    pub fret: u8,
}

/// Distance from the nut to neck fret `fret` on a string of `scale_mm`, by twelve-tone equal
/// temperament: `L * (1 - 2^(-f/12))`.
pub fn fret_distance_mm(scale_mm: f64, fret: f64) -> f64 {
    scale_mm * (1.0 - (-fret / 12.0).exp2())
}

impl Instrument {
    pub fn new(name: &str, tuning: Tuning, frets: u8, scale_length_mm: f64) -> Self {
        Instrument { name: name.into(), tuning, frets, scale_length_mm, capo: 0, notation: None }
    }

    pub fn with_notation(mut self, clef: NotationClef) -> Self {
        self.notation = Some(clef);
        self
    }

    /// The notation clef: the instrument's own, or else from the open strings: bass clef 8vb when
    /// the highest open string is below E3, treble 8vb when the lowest is below C3, else treble.
    pub fn notation_clef(&self) -> NotationClef {
        if let Some(clef) = self.notation {
            return clef;
        }
        let open = || self.tuning.strings.iter().map(|s| s.open_pitch);
        match (open().min(), open().max()) {
            (_, Some(hi)) if hi < 52 => NotationClef::Bass8vb,
            (Some(lo), _) if lo < 48 => NotationClef::Treble8vb,
            _ => NotationClef::Treble,
        }
    }

    pub fn with_capo(mut self, capo: u8) -> Self {
        self.capo = capo;
        self
    }

    pub fn with_scale_length_mm(mut self, mm: f64) -> Self {
        self.scale_length_mm = mm;
        self
    }

    pub fn string_count(&self) -> usize {
        self.tuning.strings.len()
    }

    /// Err when the instrument cannot be fingered: no strings or more than [`MAX_STRINGS`], no
    /// frets, a capo at or past the last fret, a short string starting at or past it, or a scale
    /// length that is not a positive number.
    pub fn validate(&self) -> Result<(), String> {
        let n = self.tuning.strings.len();
        if n == 0 || n > MAX_STRINGS {
            return Err(format!("an instrument has 1 to {MAX_STRINGS} strings, not {n}"));
        }
        if self.frets == 0 {
            return Err("an instrument needs at least one fret".into());
        }
        if self.capo >= self.frets {
            return Err(format!("a capo at fret {} leaves no frets on a {}-fret neck", self.capo, self.frets));
        }
        if !(self.scale_length_mm.is_finite() && self.scale_length_mm > 0.0) {
            return Err(format!("the scale length must be a positive number of millimetres, not {}", self.scale_length_mm));
        }
        for (i, s) in self.tuning.strings.iter().enumerate() {
            if s.first_fret >= self.frets {
                return Err(format!("string {} starts at fret {}, past the last fret {}", i + 1, s.first_fret, self.frets));
            }
            if !(0..=127).contains(&s.open_pitch) {
                return Err(format!("string {} is tuned to {}, outside MIDI 0-127", i + 1, s.open_pitch));
            }
        }
        Ok(())
    }

    fn spec(&self, string: u8) -> Option<&StringSpec> {
        (string as usize).checked_sub(1).and_then(|i| self.tuning.strings.get(i))
    }

    /// The neck fret where `string` stops when played open: the capo or the start of a short string.
    pub(crate) fn nut_fret(&self, string: u8) -> Option<i32> {
        self.spec(string).map(|s| i32::from(self.capo).max(i32::from(s.first_fret)))
    }

    /// Sounding pitch of `string` played open, capo included.
    pub fn open_pitch(&self, string: u8) -> Option<i32> {
        let s = self.spec(string)?;
        Some(s.open_pitch + (i32::from(self.capo) - i32::from(s.first_fret)).max(0))
    }

    /// The neck fret (from the nut) of a position; 0 for an open string. None when the position
    /// does not exist on this instrument.
    pub fn neck_fret(&self, pos: Position) -> Option<i32> {
        let nut = self.nut_fret(pos.string)?;
        if pos.fret == 0 {
            return Some(0);
        }
        let neck = i32::from(pos.fret) + i32::from(self.capo);
        (neck > nut && neck <= i32::from(self.frets)).then_some(neck)
    }

    /// The pitch a position sounds, or None when it does not exist.
    pub fn pitch_at(&self, pos: Position) -> Option<i32> {
        let s = self.spec(pos.string)?;
        match self.neck_fret(pos)? {
            0 => self.open_pitch(pos.string),
            neck => Some(s.open_pitch + neck - i32::from(s.first_fret)),
        }
    }

    /// Every position that sounds `pitch`, by string.
    pub fn positions(&self, pitch: i32) -> Vec<Position> {
        let mut out = Vec::new();
        for (i, s) in self.tuning.strings.iter().enumerate() {
            let string = (i + 1) as u8;
            let (Some(open), Some(nut)) = (self.open_pitch(string), self.nut_fret(string)) else { continue };
            if pitch == open {
                out.push(Position { string, fret: 0 });
                continue;
            }
            let neck = pitch - s.open_pitch + i32::from(s.first_fret);
            if neck > nut && neck <= i32::from(self.frets) {
                let fret = neck - i32::from(self.capo);
                out.push(Position { string, fret: fret as u8 });
            }
        }
        out
    }

    /// Distance from the nut to a neck fret, in millimetres.
    pub fn fret_mm(&self, neck_fret: i32) -> f64 {
        fret_distance_mm(self.scale_length_mm, f64::from(neck_fret))
    }

    /// Lowest and highest pitch the instrument can sound.
    pub fn range(&self) -> (i32, i32) {
        let strings = 1..=self.string_count() as u8;
        let lo = strings.clone().filter_map(|s| self.open_pitch(s)).min().unwrap_or(0);
        let hi = strings
            .filter_map(|s| {
                let spec = self.spec(s)?;
                Some(spec.open_pitch + i32::from(self.frets) - i32::from(spec.first_fret))
            })
            .max()
            .unwrap_or(0);
        (lo, hi)
    }

    /// A preset by id (see [`PRESET_IDS`]).
    pub fn preset(id: &str) -> Option<Instrument> {
        preset(id)
    }
}

// MIDI numbers of the open strings used below.
const A0: i32 = 21;
const D1: i32 = 26;
const E1: i32 = 28;
const F_SHARP2: i32 = 42;
const B0: i32 = 23;
const F_SHARP1: i32 = 30;
const B1: i32 = 35;
const C2: i32 = 36;
const D2: i32 = 38;
const E2: i32 = 40;
const G2: i32 = 43;
const A2: i32 = 45;
const B2: i32 = 47;
const C3: i32 = 48;
const D3: i32 = 50;
const E3: i32 = 52;
const F3: i32 = 53;
const F_SHARP3: i32 = 54;
const G3: i32 = 55;
const G_SHARP3: i32 = 56;
const A3: i32 = 57;
const B3: i32 = 59;
const C4: i32 = 60;
const C_SHARP4: i32 = 61;
const D4: i32 = 62;
const E4: i32 = 64;
const G4: i32 = 67;
const A4: i32 = 69;
const E5: i32 = 76;
const A1: i32 = 33;

pub const GUITAR_SCALE_MM: f64 = 648.0;
pub const EXTENDED_GUITAR_SCALE_MM: f64 = 686.0;
pub const BASS_SCALE_MM: f64 = 864.0;
pub const MANDOLIN_SCALE_MM: f64 = 350.0;
pub const BARITONE_UKULELE_SCALE_MM: f64 = 483.0;

/// Ukulele body sizes, which differ in scale length and fret count.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum UkuleleSize {
    Soprano,
    Concert,
    Tenor,
}

impl UkuleleSize {
    pub fn scale_length_mm(self) -> f64 {
        match self {
            UkuleleSize::Soprano => 330.0,
            UkuleleSize::Concert => 380.0,
            UkuleleSize::Tenor => 432.0,
        }
    }

    pub fn frets(self) -> u8 {
        match self {
            UkuleleSize::Soprano => 12,
            UkuleleSize::Concert => 18,
            UkuleleSize::Tenor => 19,
        }
    }
}

/// A GCEA ukulele: re-entrant (G4 on string 4) unless `low_g` (G3).
pub fn ukulele(size: UkuleleSize, low_g: bool) -> Instrument {
    let (name, g) = if low_g { ("Ukulele (low G)", G3) } else { ("Ukulele (high G)", G4) };
    Instrument::new(name, Tuning::from_pitches(if low_g { "GCEA low G" } else { "GCEA high G" }, &[A4, E4, C4, g]), size.frets(), size.scale_length_mm()).with_notation(NotationClef::Treble)
}

fn guitar(tuning: &str, pitches: &[i32]) -> Instrument {
    Instrument::new("Guitar", Tuning::from_pitches(tuning, pitches), 22, GUITAR_SCALE_MM).with_notation(NotationClef::Treble8vb)
}

fn guitar7(tuning: &str, pitches: &[i32]) -> Instrument {
    Instrument::new("7-string guitar", Tuning::from_pitches(tuning, pitches), 24, GUITAR_SCALE_MM).with_notation(NotationClef::Treble8vb)
}

fn bass(name: &str, tuning: &str, pitches: &[i32]) -> Instrument {
    let frets = if pitches.len() > 4 { 24 } else { 21 };
    Instrument::new(name, Tuning::from_pitches(tuning, pitches), frets, BASS_SCALE_MM).with_notation(NotationClef::Bass8vb)
}

/// Ids of the built-in instruments, in menu order. Within a family the standard tuning comes first.
pub const PRESET_IDS: &[&str] = &[
    "guitar-standard",
    "guitar-eb-standard",
    "guitar-d-standard",
    "guitar-c-standard",
    "guitar-drop-d",
    "guitar-drop-c",
    "guitar-drop-b",
    "guitar-dadgad",
    "guitar-open-g",
    "guitar-open-d",
    "guitar-open-e",
    "guitar-7-standard",
    "guitar-7-eb-standard",
    "guitar-8-standard",
    "bass-4-standard",
    "bass-4-eb-standard",
    "bass-4-d-standard",
    "bass-4-drop-d",
    "bass-4-bead",
    "bass-5-standard",
    "bass-5-drop-a",
    "bass-6-standard",
    "ukulele-high-g",
    "ukulele-low-g",
    "ukulele-baritone",
    "mandolin",
];

/// The family a preset belongs to. Presets of one family are the same instrument (string count and
/// neck) in different tunings, and are what a tuning suggestion chooses between. The first preset
/// of a family in [`PRESET_IDS`] is its standard tuning.
pub fn preset_family(id: &str) -> Option<&'static str> {
    // Longer prefixes first, so "guitar-7-..." is not taken for "guitar".
    const FAMILIES: &[&str] = &["guitar-7", "guitar-8", "bass-4", "bass-5", "bass-6", "ukulele-baritone", "ukulele", "mandolin", "guitar"];
    if !PRESET_IDS.contains(&id) {
        return None;
    }
    FAMILIES.iter().copied().find(|f| id == *f || id.strip_prefix(f).is_some_and(|rest| rest.starts_with('-')))
}

/// Preset ids of a family, standard tuning first.
pub fn family_presets(family: &str) -> Vec<&'static str> {
    PRESET_IDS.iter().copied().filter(|id| preset_family(id) == Some(family)).collect()
}

/// A built-in instrument by id; None for an unknown id.
pub fn preset(id: &str) -> Option<Instrument> {
    let std6 = [E4, B3, G3, D3, A2, E2];
    let std7 = [E4, B3, G3, D3, A2, E2, B1];
    let bass4 = [G2, D2, A1, E1];
    Some(match id {
        "guitar-standard" => guitar("Standard", &std6),
        "guitar-eb-standard" => guitar("E\u{266d} standard", &std6.map(|p| p - 1)),
        "guitar-d-standard" => guitar("D standard", &std6.map(|p| p - 2)),
        "guitar-c-standard" => guitar("C standard", &std6.map(|p| p - 4)),
        "guitar-drop-d" => guitar("Drop D", &[E4, B3, G3, D3, A2, D2]),
        "guitar-drop-c" => guitar("Drop C", &[D4, A3, F3, C3, G2, C2]),
        "guitar-drop-b" => guitar("Drop B", &[C_SHARP4, G_SHARP3, E3, B2, F_SHARP2, B1]),
        "guitar-dadgad" => guitar("DADGAD", &[D4, A3, G3, D3, A2, D2]),
        "guitar-open-g" => guitar("Open G", &[D4, B3, G3, D3, G2, D2]),
        "guitar-open-d" => guitar("Open D", &[D4, A3, F_SHARP3, D3, A2, D2]),
        "guitar-open-e" => guitar("Open E", &[E4, B3, G_SHARP3, E3, B2, E2]),
        "guitar-7-standard" => guitar7("B standard", &std7),
        "guitar-7-eb-standard" => guitar7("E\u{266d} standard", &std7.map(|p| p - 1)),
        "guitar-8-standard" => Instrument::new(
            "8-string guitar",
            Tuning::from_pitches("F\u{266f} standard", &[E4, B3, G3, D3, A2, E2, B1, F_SHARP1]),
            24,
            EXTENDED_GUITAR_SCALE_MM,
        )
        .with_notation(NotationClef::Treble8vb),
        "bass-4-standard" => bass("Bass", "Standard", &bass4),
        "bass-4-eb-standard" => bass("Bass", "E\u{266d} standard", &bass4.map(|p| p - 1)),
        "bass-4-d-standard" => bass("Bass", "D standard", &bass4.map(|p| p - 2)),
        "bass-4-drop-d" => bass("Bass", "Drop D", &[G2, D2, A1, D1]),
        "bass-4-bead" => bass("Bass", "BEAD", &[D2, A1, E1, B0]),
        "bass-5-standard" => bass("5-string bass", "Standard", &[G2, D2, A1, E1, B0]),
        "bass-5-drop-a" => bass("5-string bass", "Drop A", &[G2, D2, A1, E1, A0]),
        "bass-6-standard" => bass("6-string bass", "Standard", &[C3, G2, D2, A1, E1, B0]),
        "ukulele-high-g" => ukulele(UkuleleSize::Concert, false),
        "ukulele-low-g" => ukulele(UkuleleSize::Concert, true),
        "ukulele-baritone" => Instrument::new("Baritone ukulele", Tuning::from_pitches("DGBE", &[E4, B3, G3, D3]), 19, BARITONE_UKULELE_SCALE_MM).with_notation(NotationClef::Treble8vb),
        "mandolin" => Instrument::new("Mandolin", Tuning::from_pitches("GDAE", &[E5, A4, D4, G3]), 20, MANDOLIN_SCALE_MM).with_notation(NotationClef::Treble),
        _ => return None,
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    fn pos(string: u8, fret: u8) -> Position {
        Position { string, fret }
    }

    #[test]
    fn every_preset_is_valid() {
        for id in PRESET_IDS {
            preset(id).unwrap().validate().unwrap_or_else(|e| panic!("{id}: {e}"));
        }
        assert!(preset("banjo").is_none());
    }

    #[test]
    fn guitar_positions_of_e4() {
        let g = preset("guitar-standard").unwrap();
        assert_eq!(g.positions(64), vec![pos(1, 0), pos(2, 5), pos(3, 9), pos(4, 14), pos(5, 19)]);
        assert_eq!(g.positions(39), vec![]);
        assert_eq!(g.range(), (40, 64 + 22));
    }

    #[test]
    fn capo_raises_open_strings_and_frets_are_relative() {
        let g = preset("guitar-standard").unwrap().with_capo(2);
        assert_eq!(g.open_pitch(6), Some(42));
        assert_eq!(g.positions(40), vec![]);
        assert_eq!(g.positions(42), vec![pos(6, 0)]);
        assert_eq!(g.positions(43)[0], pos(6, 1));
        assert_eq!(g.neck_fret(pos(6, 1)), Some(3));
        assert_eq!(g.pitch_at(pos(6, 20)), Some(62));
        assert_eq!(g.pitch_at(pos(6, 21)), None);
    }

    #[test]
    fn reentrant_ukulele_string_four_is_higher_than_string_three() {
        let u = preset("ukulele-high-g").unwrap();
        assert!(u.open_pitch(4) > u.open_pitch(3));
        assert!(u.positions(67).contains(&pos(4, 0)));
        assert!(u.positions(67).contains(&pos(3, 7)));
        assert!(u.positions(59).is_empty(), "B3 is below a high-G ukulele");
        assert_eq!(preset("ukulele-low-g").unwrap().positions(55), vec![pos(4, 0)]);
    }

    #[test]
    fn short_string_has_no_low_frets() {
        // A banjo in open G: the 5th string starts at the 5th fret and is tuned to G4.
        let mut strings: Vec<StringSpec> = [D4, B3, G3, D3].iter().map(|&p| StringSpec::new(p)).collect();
        strings.push(StringSpec { open_pitch: G4, first_fret: 5 });
        let banjo = Instrument::new("Banjo", Tuning { name: "Open G".into(), strings }, 22, 660.0);
        banjo.validate().unwrap();
        for pitch in 40..100 {
            for p in banjo.positions(pitch).into_iter().filter(|p| p.string == 5) {
                assert!(p.fret == 0 || p.fret > 5, "{pitch}: {p:?}");
                assert_eq!(banjo.pitch_at(p), Some(pitch));
            }
        }
        assert_eq!(banjo.pitch_at(pos(5, 6)), Some(G4 + 1));
        assert_eq!(banjo.pitch_at(pos(5, 3)), None);
    }

    #[test]
    fn fret_distances_follow_equal_temperament() {
        assert!((fret_distance_mm(648.0, 12.0) - 324.0).abs() < 1e-9);
        assert_eq!(fret_distance_mm(648.0, 0.0), 0.0);
        let g = preset("guitar-standard").unwrap();
        // The first-position box (frets 1 to 4) is under 100 mm; frets 1 to 6 are not.
        assert!(g.fret_mm(4) - g.fret_mm(1) < 100.0);
        assert!(g.fret_mm(6) - g.fret_mm(1) > 140.0);
    }

    #[test]
    fn refuses_instruments_that_cannot_be_fingered() {
        let g = preset("guitar-standard").unwrap();
        assert!(g.clone().with_capo(22).validate().is_err());
        assert!(g.clone().with_scale_length_mm(f64::NAN).validate().is_err());
        assert!(g.clone().with_scale_length_mm(0.0).validate().is_err());
        let mut none = g.clone();
        none.tuning.strings.clear();
        assert!(none.validate().is_err());
        let mut zero = g;
        zero.frets = 0;
        assert!(zero.validate().is_err());
    }

    #[test]
    fn preset_tunings() {
        let open = |id: &str| -> Vec<i32> {
            let i = preset(id).unwrap();
            (1..=i.string_count() as u8).map(|s| i.open_pitch(s).unwrap()).collect()
        };
        assert_eq!(open("guitar-drop-d"), vec![64, 59, 55, 50, 45, 38]);
        assert_eq!(open("guitar-eb-standard"), vec![63, 58, 54, 49, 44, 39]);
        assert_eq!(open("bass-5-standard"), vec![43, 38, 33, 28, 23]);
        assert_eq!(open("mandolin"), vec![76, 69, 62, 55]);
        assert_eq!(open("guitar-8-standard"), vec![64, 59, 55, 50, 45, 40, 35, 30]);
        assert_eq!(open("ukulele-baritone"), vec![64, 59, 55, 50]);
        assert_eq!(open("guitar-drop-b"), vec![61, 56, 52, 47, 42, 35]);
        assert_eq!(open("guitar-d-standard"), vec![62, 57, 53, 48, 43, 38]);
        assert_eq!(open("guitar-c-standard"), vec![60, 55, 51, 46, 41, 36]);
        assert_eq!(open("guitar-7-eb-standard"), vec![63, 58, 54, 49, 44, 39, 34]);
        assert_eq!(open("bass-4-drop-d"), vec![43, 38, 33, 26]);
        assert_eq!(open("bass-4-eb-standard"), vec![42, 37, 32, 27]);
        assert_eq!(open("bass-4-d-standard"), vec![41, 36, 31, 26]);
        assert_eq!(open("bass-4-bead"), vec![38, 33, 28, 23]);
        assert_eq!(open("bass-5-drop-a"), vec![43, 38, 33, 28, 21]);
    }

    #[test]
    fn presets_group_into_families_with_standard_first() {
        for id in PRESET_IDS {
            let family = preset_family(id).unwrap_or_else(|| panic!("{id} has no family"));
            let first = preset(family_presets(family)[0]).unwrap();
            assert_eq!(first.string_count(), preset(id).unwrap().string_count(), "{id}");
        }
        assert_eq!(family_presets("bass-4")[0], "bass-4-standard");
        assert_eq!(family_presets("guitar")[0], "guitar-standard");
        assert!(family_presets("guitar").contains(&"guitar-drop-b"));
        assert!(!family_presets("guitar").contains(&"guitar-7-standard"));
        assert_eq!(family_presets("ukulele"), vec!["ukulele-high-g", "ukulele-low-g"]);
        assert_eq!(preset_family("banjo"), None);
    }
}
