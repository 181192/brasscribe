//! The shared core: the symbolic half of the pipeline, for every app and every kind of instrument.
//!
//! Composition model and JSON, beat-grid quantization, free-time planning,
//! written durations, pitch spelling and key, harmony reduction, note voting
//! and the MusicXML writer. It reproduces the Python reference
//! (`brasscribe_music` and the eval entry points) exactly; `core/conformance`
//! checks that.
//!
//! It knows no instruments. What turns notes into one kind of output (arranging for a brass band in
//! `target-brass`, placing notes on strings in `target-fretted`) lives in a target crate that
//! depends on this one; this crate depends on no target, and targets do not depend on each other
//! (`tests/crate_graph.rs`). A target hands the writer what it needs as data:
//! [`notation::score::InstrumentSpec`] for a part's instrument.

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
