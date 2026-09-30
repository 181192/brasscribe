//! Tablature fingering for fretted instruments: a string and a fret for every note.

pub mod instrument;

pub use instrument::{fret_distance_mm, preset, ukulele, Instrument, Position, StringSpec, Tuning, UkuleleSize, PRESET_IDS};
