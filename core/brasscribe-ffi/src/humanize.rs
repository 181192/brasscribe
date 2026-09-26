//! Humanization of score notes for playback (sounds/README.md, "Humanization").

use std::sync::Arc;

use brasscribe_core::humanize as h;

use crate::{invalid, CoreError};

/// One part note: score position in Composition ticks (24 per beat) plus its
/// score-tempo seconds. `pitch` is concert MIDI.
#[derive(Debug, Clone, uniffi::Record)]
pub struct ScoreNote {
    pub tick: i64,
    pub dur_tick: i64,
    pub start_s: f64,
    pub end_s: f64,
    pub pitch: i32,
    pub velocity: i64,
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct PlayedNote {
    pub start: f64,
    pub end: f64,
    pub pitch: i32,
    pub velocity: i64,
    pub staccato: bool,
    /// Timing came from the Composition (not jitter alone).
    pub from_composition: bool,
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct HumanizeStats {
    /// Composition voice the part matched, if any.
    pub voice: Option<String>,
    pub own_timing: u64,
    pub ensemble_timing: u64,
    pub jitter_only: u64,
    pub lag_ms: f64,
    pub detune_cents: f64,
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct HumanizedPart {
    pub notes: Vec<PlayedNote>,
    /// Detune for the whole player in cents (one pitch bend at the start).
    pub detune_cents: f64,
    pub stats: HumanizeStats,
}

/// What a Composition says about how the music was played (performed beat
/// map, per-tick ensemble deviations, voices). Build once, use for every part.
#[derive(uniffi::Object)]
pub struct Performance {
    inner: h::Performance,
}

#[uniffi::export]
impl Performance {
    #[uniffi::constructor]
    pub fn new(composition_json: String) -> Result<Arc<Self>, CoreError> {
        Ok(Arc::new(Performance { inner: h::Performance::from_json_str(&composition_json).map_err(invalid)? }))
    }
}

/// Humanize one player's notes. `performed_timing` follows the recording's
/// rubato (needs `performance`); otherwise the score tempo is kept.
#[uniffi::export]
pub fn humanize_part(
    notes: Vec<ScoreNote>,
    part: String,
    player: i64,
    seed: String,
    performance: Option<Arc<Performance>>,
    performed_timing: bool,
) -> Result<HumanizedPart, CoreError> {
    let notes: Vec<h::ScoreNote> = notes
        .into_iter()
        .map(|n| h::ScoreNote { tick: n.tick, dur_tick: n.dur_tick, start_s: n.start_s, end_s: n.end_s, pitch: n.pitch, velocity: n.velocity })
        .collect();
    let timing = if performed_timing { h::Timing::Performed } else { h::Timing::Score };
    let seed = if seed.is_empty() { "brasscribe".to_string() } else { seed };
    let r = h::humanize(&notes, &part, player, &seed, performance.as_ref().map(|p| &p.inner), timing).map_err(invalid)?;
    Ok(convert(r))
}

pub(crate) fn convert(r: h::Humanized) -> HumanizedPart {
    HumanizedPart {
        notes: r
            .notes
            .into_iter()
            .map(|n| PlayedNote { start: n.start, end: n.end, pitch: n.pitch, velocity: n.velocity, staccato: n.staccato, from_composition: n.from_composition })
            .collect(),
        detune_cents: r.detune,
        stats: HumanizeStats {
            voice: r.stats.voice,
            own_timing: r.stats.own_timing as u64,
            ensemble_timing: r.stats.ensemble_timing as u64,
            jitter_only: r.stats.jitter_only as u64,
            lag_ms: r.stats.lag_ms,
            detune_cents: r.stats.detune_cents,
        },
    }
}

/// U(key) in [0, 1): the keyed uniform the humanizer draws from.
#[uniffi::export]
pub fn humanize_uniform(key: String) -> f64 {
    h::uniform(&key)
}
