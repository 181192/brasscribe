//! Tablature fingering for fretted instruments: a string and a fret for every note.
//!
//! The input is the shared symbolic model's notes (concert MIDI pitch, start and length in ticks).
//! [`assign`] chooses a playable position for each, [`check`] lists hard playability violations,
//! [`suggest_tunings`] ranks the tunings of an instrument by fit, and [`json`] wraps them for
//! callers outside Rust. [`write_tab_musicxml`] writes the result as tablature in MusicXML,
//! [`write_tab_text`] as a plain-text tab and [`write_playing_instructions`] as sentences for a
//! screen reader. Pitches are never changed: a note no string can sound is flagged out of range and
//! left where it is.

pub mod check;
pub mod instructions;
pub mod instrument;
pub mod json;
pub mod shapes;
pub mod solve;
pub mod suggest;
pub mod tab;
pub mod technique;
pub mod text;

pub use check::{check, check_with_techniques, Violation};
pub use instructions::{instructions_language, write_playing_instructions};
pub use instrument::{family_presets, fret_distance_mm, preset, preset_family, ukulele, Instrument, NotationClef, Position, StringSpec, Tuning, UkuleleSize, PRESET_IDS};
pub use solve::{assign, assign_with_techniques, Fingering, HandLimits, NotePlace, Options, Pin, Style, MAX_NOTES};
pub use suggest::{suggest_tunings, TuningFit};
pub use tab::{header_text, CapoEncoding, write_tab_musicxml, Layout, TabDocument, TabNote, TabOptions, TabScore, CONFIDENCE, DOUBT_BELOW, DOUBT_COLOR, NOTE_INDEX};
pub use text::{write_tab_text, TextOptions, MAX_TEXT_WIDTH, MIN_TEXT_WIDTH, TEXT_WIDTH};
pub use technique::{previous_note, previous_notes, Technique, LEGATO_REACH, SLIDE_REACH};
