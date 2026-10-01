//! Tablature fingering for fretted instruments: a string and a fret for every note.
//!
//! The input is the shared symbolic model's notes (concert MIDI pitch, start and length in ticks).
//! [`assign`] chooses a playable position for each, [`check`] lists hard playability violations,
//! and [`json`] wraps both for callers outside Rust. Pitches are never changed: a note no string
//! can sound is flagged out of range and left where it is.

pub mod check;
pub mod instrument;
pub mod json;
pub mod solve;

pub use check::{check, Violation};
pub use instrument::{fret_distance_mm, preset, ukulele, Instrument, Position, StringSpec, Tuning, UkuleleSize, PRESET_IDS};
pub use solve::{assign, Fingering, HandLimits, NotePlace, Options, Pin, Style};
