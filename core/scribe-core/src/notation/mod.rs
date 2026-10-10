//! Notation layer: measures, ties, accidentals, beams, tuplets and
//! transposition, reproducing the reference's MusicXML output (which it gets
//! from music21's `makeNotation` and MusicXML exporter) for the scores the
//! arrangers produce.

pub mod beams;
pub mod duration;
pub mod parts;
pub mod pitch;
pub mod score;
pub mod xml;
