//! brasscribe core: the symbolic half of the pipeline, shared by every app.
//!
//! Composition model and JSON, beat-grid quantization, free-time planning,
//! written durations, pitch spelling and key, harmony reduction, instrument
//! knowledge, the two brass-band arrangers, note voting and the MusicXML
//! writer. It reproduces the Python reference (`brasscribe_music` and the
//! eval entry points) exactly; `core/conformance` checks that.

pub mod arranger;
pub mod structure;
pub mod separation;
pub mod keys;
pub mod energy;
pub mod dynamics;
pub mod beats;
pub mod consensus;
pub mod difficulty;
pub mod durations;
pub mod freetime;
pub mod harmony;
pub mod humanize;
pub mod instruments;
pub mod lines;
pub mod midi;
pub mod model;
pub mod musicxml;
pub mod notation;
pub mod pipeline;
pub mod py;
pub mod pyjson;
pub mod quantize;
pub mod rhythm_spelling;
pub mod spelling;
pub mod talking_score;

pub use model::Composition;

pub const VERSION: &str = env!("CARGO_PKG_VERSION");
