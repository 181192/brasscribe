//! The shared core: the symbolic half of the pipeline, for every app.
//!
//! Composition model and JSON, beat-grid quantization, free-time planning,
//! written durations, pitch spelling and key, harmony reduction, note voting
//! and the MusicXML writer. It reproduces the Python reference
//! (`brasscribe_music` and the eval entry points) exactly; `core/conformance`
//! checks that.
//!
//! What turns notes into one kind of output (arranging for a brass band in `target-brass`, placing
//! notes on strings in `target-fretted`) lives in a target crate that depends on this one; this crate
//! depends on no target, and targets do not depend on each other (`tests/crate_graph.rs`). A target
//! hands the writer what it needs as data: [`notation::score::InstrumentSpec`] for a part's instrument.
//!
//! The core is not free of instruments yet. [`talking_score`] still holds the Norwegian names of the
//! brass band's parts and instruments (`tests/shared_boundary.rs` keeps the other modules from using
//! it), the writer's comments still speak of the band, and the transcription that every target needs
//! sits in `target-brass`'s `pipeline` (docs/plan/scribe-platform.md, steps 2b and 2c).

pub mod structure;
pub mod separation;
pub mod keys;
pub mod energy;
pub mod dynamics;
pub mod beats;
pub mod confidence;
pub mod consensus;
pub mod durations;
pub mod freetime;
pub mod harmony;
pub mod humanize;
pub mod lines;
pub mod midi;
pub mod model;
pub mod notation;
pub mod onsets;
pub mod py;
pub mod pyjson;
pub mod quantize;
pub mod rhythm_spelling;
pub mod spelling;
pub mod talking_score;
pub mod trills;

pub use model::Composition;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
