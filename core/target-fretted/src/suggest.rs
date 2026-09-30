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
    /// The lowest open string is exactly the lowest note (same MIDI pitch): the notes give evidence
    /// for this tuning, as a drop or down-tuned riff on its open bottom string does.
    /// around the passage's bottom note, as a drop or down-tuned riff is.
    pub low_string_fits: bool,
    /// Notes an open string can play.
    pub open_notes: usize,
    /// Notes that can only be played above fret [`HIGH_FRET`].
    pub high_frets: usize,
    /// Semitones between this tuning's open strings and the family's standard tuning, summed.
    pub distance: i32,
}

/// Every preset of `family` ranked by fit to `notes`, best first:
/// 1. fewest out-of-range notes;
/// 2. the lowest open string is exactly the lowest note;
/// 3. closest to the standard tuning;
/// 4. most notes on open strings, fewest high-fret notes, then preset order.
///
/// Standard tuning wins unless the notes give evidence against it.
///
/// Frets are counted with `capo`. Empty for an unknown family.
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
            let mut open_notes = 0;
            for n in notes {
                match inst.positions(n.pitch).iter().map(|p| p.fret).min() {
                    None => out_of_range += 1,
                    Some(0) => open_notes += 1,
                    Some(f) if f > HIGH_FRET => high_frets += 1,
                    Some(_) => {}
                }
            }
            let lowest_open = (1..=inst.string_count() as u8).filter_map(|s| inst.open_pitch(s)).min();
            let lowest_note = notes.iter().map(|n| n.pitch).min();
            let low_string_fits = matches!((lowest_open, lowest_note), (Some(o), Some(n)) if n == o);
            let distance = inst.tuning.strings.iter().zip(&standard.tuning.strings).map(|(a, b)| (a.open_pitch - b.open_pitch).abs()).sum();
            Some((order, TuningFit { preset: id.to_string(), tuning: inst.tuning.name.clone(), out_of_range, low_string_fits, open_notes, high_frets, distance }))
        })
        .collect();
    fits.sort_by_key(|(order, f)| (f.out_of_range, !f.low_string_fits, f.distance, std::cmp::Reverse(f.open_notes), f.high_frets, *order));
    fits.into_iter().map(|(_, f)| f).collect()
}
