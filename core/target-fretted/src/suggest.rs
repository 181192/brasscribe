//! Tuning suggestion: which preset of an instrument family fits the notes best.
//!
//! Most whole-song wrongness in tab is a wrong tuning (drop D, E♭ standard), so "Check the song"
//! offers the best fit, and the player confirms it.

use brasscribe_core::model::Note;
use serde::{Deserialize, Serialize};

use crate::instrument::{family_presets, preset};

/// A note whose lowest possible fret is above this counts as a high-fret note.
pub const HIGH_FRET: u8 = 12;

/// How well one preset tuning fits a passage.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct TuningFit {
    pub preset: String,
    /// The tuning's display name, e.g. "Drop D".
    pub tuning: String,
    /// Notes no string can sound.
    pub out_of_range: usize,
    /// Notes that can only be played above fret [`HIGH_FRET`].
    pub high_frets: usize,
    /// Semitones between this tuning's open strings and the family's standard tuning, summed.
    pub distance: i32,
}

/// Every preset of `family` ranked by fit to `notes`, best first: fewest out-of-range notes, then
/// fewest high-fret notes, then closest to the standard tuning, then preset order. Frets are counted
/// with `capo`. Empty for an unknown family.
pub fn suggest_tunings(family: &str, notes: &[Note], capo: u8) -> Vec<TuningFit> {
    let ids = family_presets(family);
    let Some(standard) = ids.first().and_then(|id| preset(id)) else { return Vec::new() };
    let mut fits: Vec<(usize, TuningFit)> = ids
        .iter()
        .enumerate()
        .filter_map(|(order, id)| {
            let inst = preset(id)?.with_capo(capo);
            if inst.validate().is_err() {
                return None;
            }
            let mut out_of_range = 0;
            let mut high_frets = 0;
            for n in notes {
                match inst.positions(n.pitch).iter().map(|p| p.fret).min() {
                    None => out_of_range += 1,
                    Some(f) if f > HIGH_FRET => high_frets += 1,
                    Some(_) => {}
                }
            }
            let distance = inst.tuning.strings.iter().zip(&standard.tuning.strings).map(|(a, b)| (a.open_pitch - b.open_pitch).abs()).sum();
            Some((order, TuningFit { preset: id.to_string(), tuning: inst.tuning.name.clone(), out_of_range, high_frets, distance }))
        })
        .collect();
    fits.sort_by_key(|(order, f)| (f.out_of_range, f.high_frets, f.distance, *order));
    fits.into_iter().map(|(_, f)| f).collect()
}
