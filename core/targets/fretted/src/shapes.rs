//! Idiomatic chord shapes the solver prefers, as data.
//!
//! Two small tables:
//! - power chords: intervals above the root, played on adjacent strings with the root on the lowest
//!   string. On a guitar in standard tuning this gives `x-3-5-5`. In drop D it gives the one-finger
//!   `5-5-5`, because the tuning, not the table, decides the frets.
//! - open shapes for strummed ukulele and mandolin chords, which play every string and so double
//!   a pitch on a second string (ukulele G is `0-2-3-2`: G4 on strings 4 and 2).

use crate::instrument::{Instrument, Position};

/// Power chords as semitones above the root, lowest string first.
pub const POWER_CHORDS: &[&[i32]] = &[&[0, 7], &[0, 7, 12]];

/// Open shapes for one family of tunings.
pub struct ShapeSet {
    /// Open pitches of the tunings the shapes are for, string 1 first (no capo).
    pub tunings: &'static [&'static [i32]],
    /// Chord name and frets, lowest string first, as players write them.
    pub shapes: &'static [(&'static str, &'static str)],
}

pub const OPEN_SHAPES: &[ShapeSet] = &[
    ShapeSet {
        // Ukulele GCEA, high and low G.
        tunings: &[&[69, 64, 60, 67], &[69, 64, 60, 55]],
        shapes: &[
            ("C", "0003"),
            ("C7", "0001"),
            ("G", "0232"),
            ("G7", "0212"),
            ("Am", "2000"),
            ("A", "2100"),
            ("A7", "0100"),
            ("F", "2010"),
            ("D", "2220"),
            ("Dm", "2210"),
            ("Em", "0432"),
            ("E7", "1202"),
        ],
    },
    ShapeSet {
        // Mandolin GDAE.
        tunings: &[&[76, 69, 62, 55]],
        shapes: &[("G", "0023"), ("C", "0230"), ("D", "2002"), ("Em", "0220"), ("Am", "2230")],
    },
];

/// The open shapes for `inst`'s tuning, as positions relative to its capo.
pub fn open_shapes(inst: &Instrument) -> Vec<(&'static str, Vec<Position>)> {
    let open: Vec<i32> = inst.tuning.strings.iter().map(|s| s.open_pitch).collect();
    let n = open.len();
    OPEN_SHAPES
        .iter()
        .filter(|set| set.tunings.contains(&open.as_slice()))
        .flat_map(|set| set.shapes.iter())
        .filter_map(|(name, frets)| {
            let frets: Vec<u8> = frets.bytes().map(|b| b.wrapping_sub(b'0')).collect();
            if frets.len() != n || frets.iter().any(|&f| f > 9) {
                return None;
            }
            // Lowest string first in the table; string n is the lowest line.
            let positions: Vec<Position> = frets.iter().enumerate().map(|(i, &fret)| Position { string: (n - i) as u8, fret }).collect();
            positions.iter().all(|&p| inst.pitch_at(p).is_some()).then_some((*name, positions))
        })
        .collect()
}

/// Whether notes (pitch, string) starting together form a power chord from [`POWER_CHORDS`]:
/// the listed intervals above the lowest note, each on the next string up from the root's.
pub fn is_power_chord(notes: &[(i32, u8)]) -> bool {
    let mut sorted = notes.to_vec();
    sorted.sort_unstable();
    let Some(&(root, root_string)) = sorted.first() else { return false };
    POWER_CHORDS.iter().any(|shape| {
        shape.len() == sorted.len()
            && sorted.iter().zip(shape.iter()).enumerate().all(|(k, (&(pitch, string), &interval))| pitch - root == interval && i32::from(string) == i32::from(root_string) - k as i32)
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::instrument::preset;

    #[test]
    fn every_open_shape_sounds_its_chord_on_its_tuning() {
        let uke = preset("ukulele-high-g").unwrap();
        let shapes = open_shapes(&uke);
        assert_eq!(shapes.len(), 12);
        let g = &shapes.iter().find(|s| s.0 == "G").unwrap().1;
        let mut pitches: Vec<i32> = g.iter().map(|&p| uke.pitch_at(p).unwrap()).collect();
        pitches.sort_unstable();
        assert_eq!(pitches, vec![62, 67, 67, 71]);
        assert_eq!(open_shapes(&preset("mandolin").unwrap()).len(), 5);
        assert!(open_shapes(&preset("guitar-standard").unwrap()).is_empty());
        // Capo'd shapes keep their frets and sound higher.
        let capo = preset("ukulele-high-g").unwrap().with_capo(2);
        assert_eq!(open_shapes(&capo)[0].1, open_shapes(&uke)[0].1);
    }

    #[test]
    fn power_chords_are_on_adjacent_strings_root_lowest() {
        assert!(is_power_chord(&[(48, 5), (55, 4), (60, 3)]));
        assert!(is_power_chord(&[(43, 6), (50, 5)]));
        assert!(!is_power_chord(&[(48, 5), (55, 3), (60, 2)]));
        assert!(!is_power_chord(&[(48, 5), (55, 4), (64, 3)]));
        assert!(!is_power_chord(&[(48, 5)]));
    }
}
