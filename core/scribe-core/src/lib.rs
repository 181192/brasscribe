//! The shared core: the symbolic half of the pipeline, for every app.
//!
//! Composition model and JSON, beat-grid quantization, free-time planning,
//! written durations, pitch spelling and key, harmony reduction, note voting,
//! the transcription that puts them together ([`transcription`]: transcriptions
//! and beats in, a Composition out) and the MusicXML writer. It reproduces the Python reference
//! (`brasscribe_music` and the eval entry points) exactly; `core/conformance`
//! checks that.
//!
//! What turns notes into one kind of output (arranging for a brass band in `target-brass`, placing
//! notes on strings in `target-fretted`) lives in a target crate that depends on this one; this crate
//! depends on no target, and targets do not depend on each other (`tests/crate_graph.rs`).
//!
//! The shared core knows no instruments (`tests/instrument_words.rs`). A target hands it what it needs
//! to know of one: [`notation::score::InstrumentSpec`] for the instrument a part is written for,
//! [`talking_score::Names`] for what parts and instruments are called when a score is read aloud, and
//! the range a line is taken in ([`transcription`]).

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
pub mod transcription;
pub mod trills;

pub use model::Composition;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
