//! Tablature fingering for fretted instruments: a string and a fret for every note.
//!
//! The input is the shared symbolic model's notes (concert MIDI pitch, start and length in ticks).
//! [`assign`] chooses a playable position for each, [`check`] lists hard playability violations,
//! [`suggest_tunings`] ranks the tunings of an instrument by fit, and [`json`] wraps them for
//! callers outside Rust. Pitches are never changed: a note no string can sound is flagged out of
//! range and left where it is.

pub mod check;
pub mod instrument;
pub mod json;
pub mod shapes;
pub mod solve;
pub mod suggest;
pub mod technique;

pub use check::{check, Violation};
pub use instrument::{family_presets, fret_distance_mm, preset, preset_family, ukulele, Instrument, Position, StringSpec, Tuning, UkuleleSize, PRESET_IDS};
pub use solve::{assign, Fingering, HandLimits, NotePlace, Options, Pin, Style};
pub use suggest::{suggest_tunings, TuningFit};
pub use technique::{Technique, TechniqueMark};
