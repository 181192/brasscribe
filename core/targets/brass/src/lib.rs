//! The brass-band target: what turns the shared core's notes into a band score.
//!
//! Instrument knowledge (the band's instruments, lineups, the players' seats), the two brass-band
//! arrangers, the difficulty levels, the band score handed to the core's MusicXML writer, and the
//! entry points that go from transcriptions to an arranged band. It reproduces the Python reference
//! (`brasscribe_music` and the eval entry points) exactly; `core/conformance` checks that.
//!
//! It depends on the shared core (`scribe-core`) and on no other target.

pub mod arranger;
pub mod difficulty;
pub mod instruments;
pub mod musicxml;
pub mod pipeline;
