//! Playing techniques that constrain where a note can go.

use brasscribe_core::model::Note;
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "kebab-case")]
pub enum Technique {
    /// Slid into from the previous note: same string, at most [`SLIDE_REACH`] frets away.
    Slide,
    /// Hammered on from the previous note: same string, at most [`LEGATO_REACH`] frets away.
    HammerOn,
    /// Pulled off from the previous note: same string, at most [`LEGATO_REACH`] frets away.
    PullOff,
    /// Bent up from the previous note's string: same string, and fretted (an open string cannot
    /// be bent).
    Bend,
    /// No constraint on the position yet.
    Vibrato,
    /// Rings until its written end: no later note may use its string while it sounds.
    LetRing,
}

/// The farthest a slide travels along the string, in frets.
pub const SLIDE_REACH: i32 = 12;
/// The farthest a hammer-on or pull-off reaches from the note it comes from, in frets.
pub const LEGATO_REACH: i32 = 5;

impl Technique {
    /// Whether the note must stay on the string of the note before it.
    pub fn keeps_string(self) -> bool {
        matches!(self, Technique::Slide | Technique::HammerOn | Technique::PullOff | Technique::Bend)
    }

    /// Whether the note must be fretted.
    pub fn needs_fret(self) -> bool {
        self == Technique::Bend
    }

    /// The most frets between this note and the note it comes from, for techniques that keep the
    /// string; None when there is no limit.
    pub fn reach(self) -> Option<i32> {
        match self {
            Technique::Slide => Some(SLIDE_REACH),
            Technique::HammerOn | Technique::PullOff => Some(LEGATO_REACH),
            _ => None,
        }
    }
}

/// For a note's techniques: None when none keeps the string, else the tightest reach (i32::MAX
/// when unlimited).
pub fn string_link(techniques: &[Technique]) -> Option<i32> {
    techniques.iter().filter(|t| t.keeps_string()).map(|t| t.reach().unwrap_or(i32::MAX)).min()
}

/// The note a slide, hammer-on, pull-off or bend on note `i` comes from: among the notes starting
/// most recently before it, the closest in pitch (the lower index on a tie). None when nothing
/// starts earlier.
pub fn previous_note(notes: &[Note], i: usize) -> Option<usize> {
    let start = notes[i].start;
    let prev = notes.iter().map(|n| n.start).filter(|&s| s < start).max()?;
    (0..notes.len()).filter(|&j| notes[j].start == prev).min_by_key(|&j| ((notes[j].pitch - notes[i].pitch).abs(), j))
}

/// Techniques per note, checked against the notes: empty (no techniques) or one list per note.
pub(crate) fn per_note(techniques: &[Vec<Technique>], notes: usize) -> Result<Vec<Vec<Technique>>, String> {
    match techniques.len() {
        0 => Ok(vec![Vec::new(); notes]),
        n if n == notes => Ok(techniques.to_vec()),
        n => Err(format!("techniques are given for {n} notes, not the {notes} notes of the passage")),
    }
}
