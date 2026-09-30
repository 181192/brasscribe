//! Playing techniques that constrain where a note can go.

use brasscribe_core::model::Note;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum Technique {
    /// Slid into from the previous note: same string.
    Slide,
    /// Hammered on from the previous note: same string.
    HammerOn,
    /// Pulled off from the previous note: same string.
    PullOff,
    /// Bent up from the previous note's string: same string, and fretted (an open string cannot
    /// be bent).
    Bend,
    /// No constraint on the position yet.
    Vibrato,
    /// Rings until its written end: no later note may use its string while it sounds.
    LetRing,
}

impl Technique {
    /// Whether the note must stay on the string of the note before it.
    pub fn keeps_string(self) -> bool {
        matches!(self, Technique::Slide | Technique::HammerOn | Technique::PullOff | Technique::Bend)
    }

    /// Whether the note must be fretted.
    pub fn needs_fret(self) -> bool {
        self == Technique::Bend
    }
}

/// A technique on one note of the input.
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TechniqueMark {
    /// Index of the note in the input.
    pub note: usize,
    pub technique: Technique,
}

/// The note a slide, hammer-on, pull-off or bend on note `i` comes from: among the notes starting
/// most recently before it, the closest in pitch (the lower index on a tie). None when nothing
/// starts earlier.
pub fn previous_note(notes: &[Note], i: usize) -> Option<usize> {
    let start = notes[i].start;
    let prev = notes.iter().map(|n| n.start).filter(|&s| s < start).max()?;
    (0..notes.len()).filter(|&j| notes[j].start == prev).min_by_key(|&j| ((notes[j].pitch - notes[i].pitch).abs(), j))
}
