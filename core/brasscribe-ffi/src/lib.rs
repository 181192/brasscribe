//! Bindings of brasscribe-core for the native apps.
//!
//! * UniFFI (Swift, Kotlin): the `#[uniffi::export]` functions below; generate
//!   the foreign code with `core/scripts/bindings.sh`.
//! * C ABI (C#, anything with a C FFI): the `bc_*` functions in [`c_api`];
//!   header in `core/bindings/c/brasscribe.h` (cbindgen).
//!
//! Inputs and outputs are plain data: MIDI file bytes, beat tables as text,
//! Composition JSON and MusicXML strings. Nothing here touches the file system.

use brasscribe_core::arranger::{arrange, arrange_layers};
use brasscribe_core::durations::Contour;
use brasscribe_core::midi::{MidiFile, RawNote};
use brasscribe_core::model::Composition;
use brasscribe_core::musicxml::{band_score, write_score};
use brasscribe_core::pipeline::{self, Beats, Layers, LayersOptions, SongInputs};
use brasscribe_core::quantize::{choose_level, fill_gaps, quantize};

pub mod c_api;

uniffi::setup_scaffolding!();

#[derive(Debug, uniffi::Error)]
pub enum CoreError {
    /// Input could not be read (bad JSON, MIDI or beat table).
    Invalid { reason: String },
    /// A pipeline step failed on valid input.
    Failed { reason: String },
}

impl std::error::Error for CoreError {}

impl std::fmt::Display for CoreError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            CoreError::Invalid { reason } => write!(f, "invalid input: {reason}"),
            CoreError::Failed { reason } => write!(f, "{reason}"),
        }
    }
}

fn invalid(e: impl ToString) -> CoreError {
    CoreError::Invalid { reason: e.to_string() }
}

fn failed(e: impl ToString) -> CoreError {
    CoreError::Failed { reason: e.to_string() }
}

/// Version of the core library.
#[uniffi::export]
pub fn core_version() -> String {
    brasscribe_core::VERSION.to_string()
}

/// Parse and re-serialise a Composition (the canonical composition.json text).
#[uniffi::export]
pub fn normalize_composition(json: String) -> Result<String, CoreError> {
    let c = Composition::from_json_str(&json).map_err(invalid)?;
    Ok(c.to_json_string())
}

/// Arrange a Composition for brass band and return MusicXML (written pitch).
///
/// `arranger`: "layers" (solo with band), "minimal" (minimal band) or "auto"
/// (layers when the voices carry textural layers).
#[uniffi::export]
pub fn arrange_musicxml(composition_json: String, arranger: String) -> Result<String, CoreError> {
    arrange_impl(&composition_json, &arranger)
}

pub(crate) fn arrange_impl(composition_json: &str, arranger: &str) -> Result<String, CoreError> {
    let comp = Composition::from_json_str(composition_json).map_err(invalid)?;
    let layered = match arranger {
        "layers" => true,
        "minimal" => false,
        "auto" | "" => comp.voices.iter().any(|v| v.layer.is_some()),
        other => return Err(invalid(format!("unknown arranger {other}"))),
    };
    let arr = if layered { arrange_layers(&comp) } else { arrange(&comp) };
    Ok(write_score(&band_score(&arr, &comp)))
}

/// Composition and MusicXML of one arrangement.
#[derive(Debug, Clone, uniffi::Record)]
pub struct SongOutput {
    pub composition_json: String,
    pub musicxml: String,
}

/// Transcribed layers of a recording as MIDI file bytes.
#[derive(Debug, Clone, uniffi::Record)]
pub struct LayerMidi {
    pub solo_swiftf0: Vec<u8>,
    pub solo_muscriptor: Vec<u8>,
    pub solo_basic_pitch: Vec<u8>,
    pub bass: Vec<u8>,
    pub orchestra: Vec<u8>,
    pub drums: Vec<u8>,
}

/// Frame-level pitch contour of the solo stem (SwiftF0).
#[derive(Debug, Clone, uniffi::Record)]
pub struct SoloContour {
    pub times: Vec<f64>,
    pub pitch_hz: Vec<f64>,
    pub loudness_db: Vec<f64>,
}

fn midi(b: &[u8]) -> Result<MidiFile, CoreError> {
    MidiFile::parse(b).map_err(invalid)
}

/// Solo-with-band arrangement from layer transcriptions and a beat table
/// (`time position` per line, position 1 = downbeat).
#[uniffi::export]
pub fn arrange_layers_song(
    layers: LayerMidi,
    beats_text: String,
    title: String,
    solo_contour: Option<SoloContour>,
    free_time: bool,
    free_tempo: Option<f64>,
) -> Result<SongOutput, CoreError> {
    let l = Layers {
        solo_sw: midi(&layers.solo_swiftf0)?,
        solo_mus: midi(&layers.solo_muscriptor)?,
        solo_bp: midi(&layers.solo_basic_pitch)?,
        bass: midi(&layers.bass)?,
        orchestra: midi(&layers.orchestra)?,
        drums: midi(&layers.drums)?,
    };
    let beats = Beats::parse(&beats_text).map_err(invalid)?;
    let opts = LayersOptions {
        solo_contour: solo_contour.map(|c| Contour::from_hz(c.times, &c.pitch_hz, c.loudness_db)),
        no_free_time: !free_time,
        free_tempo,
    };
    let r = pipeline::arrange_layers_song(&l, &beats, &title, &opts).map_err(failed)?;
    Ok(SongOutput { composition_json: r.composition.to_json_string(), musicxml: r.musicxml })
}

/// Minimal-band arrangement from melody, optional melody support, bass and harmony transcriptions.
#[uniffi::export]
pub fn arrange_song(
    melody: Vec<u8>,
    melody_support: Option<Vec<u8>>,
    bass: Vec<u8>,
    harmony: Vec<Vec<u8>>,
    beats_text: String,
    title: String,
) -> Result<SongOutput, CoreError> {
    let inp = SongInputs {
        melody: midi(&melody)?,
        melody_support: melody_support.map(|b| midi(&b)).transpose()?,
        bass: midi(&bass)?,
        harmony: harmony.iter().map(|b| midi(b)).collect::<Result<_, _>>()?,
    };
    let beats = Beats::parse(&beats_text).map_err(invalid)?;
    let r = pipeline::arrange_song(&inp, &beats, &title).map_err(failed)?;
    Ok(SongOutput { composition_json: r.composition.to_json_string(), musicxml: r.musicxml })
}

/// A performed note (seconds).
#[derive(Debug, Clone, uniffi::Record)]
pub struct PerformedNote {
    pub pitch: i32,
    pub onset: f64,
    pub offset: f64,
    pub confidence: Option<f64>,
}

/// A note on the tick grid (24 ticks per beat).
#[derive(Debug, Clone, uniffi::Record)]
pub struct GridNote {
    pub pitch: i32,
    pub start: i64,
    pub end: i64,
    pub confidence: f64,
}

/// Quantize performed notes onto a beat grid; optionally keep one voice and
/// hold notes across gaps up to `fill_gap_ticks` (0 = no gap filling).
#[uniffi::export]
pub fn quantize_notes(notes: Vec<PerformedNote>, beat_times: Vec<f64>, monophonic: bool, auto_level: bool, fill_gap_ticks: i64) -> Result<Vec<GridNote>, CoreError> {
    if beat_times.len() < 2 {
        return Err(invalid("need at least two beats"));
    }
    let raw: Vec<RawNote> = notes.iter().map(|n| RawNote { pitch: n.pitch, onset: n.onset, offset: n.offset, confidence: n.confidence }).collect();
    let mut q = quantize(&raw, &beat_times, monophonic, auto_level);
    if fill_gap_ticks > 0 {
        q = fill_gaps(q, fill_gap_ticks, 0.0);
    }
    Ok(q.into_iter().map(|x| GridNote { pitch: x.pitch, start: x.start, end: x.end, confidence: x.confidence }).collect())
}

/// Beat times at the notated metrical level (doubled when the tracker locked onto half notes).
#[uniffi::export]
pub fn choose_metrical_level(beat_times: Vec<f64>, onsets: Vec<f64>) -> Vec<f64> {
    if beat_times.len() < 2 {
        return beat_times;
    }
    choose_level(&beat_times, &onsets)
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct SpelledPitch {
    /// "C".."B"
    pub step: String,
    pub alter: i32,
    pub octave: i32,
}

/// Spell MIDI pitches (ps13) from their context; onsets in beats.
#[uniffi::export]
pub fn spell_pitches(onsets_beats: Vec<f64>, pitches: Vec<i32>) -> Vec<SpelledPitch> {
    brasscribe_core::spelling::spell(&onsets_beats, &pitches)
        .into_iter()
        .map(|s| SpelledPitch { step: s.step.to_string(), alter: s.alter, octave: s.octave })
        .collect()
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct KeyEstimate {
    /// "F", "Dm", ...
    pub name: String,
    pub fifths: i32,
}

/// Krumhansl-Kessler key estimate from note durations (beats) and pitches.
#[uniffi::export]
pub fn estimate_key(durations_beats: Vec<f64>, pitches: Vec<i32>) -> KeyEstimate {
    let (name, fifths) = brasscribe_core::spelling::key_of(&durations_beats, &pitches);
    KeyEstimate { name: name.to_string(), fifths }
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct InstrumentInfo {
    pub id: String,
    pub name: String,
    pub short_name: String,
    /// Sounding minus written, semitones.
    pub chromatic: i32,
    pub diatonic: i32,
    pub clef: String,
    pub pro_low: i32,
    pub pro_high: i32,
    pub comfortable_low: i32,
    pub comfortable_high: i32,
    pub gm_program: i32,
    pub sound: String,
}

/// The brass-band instrument table (ranges are sounding MIDI pitches).
#[uniffi::export]
pub fn instruments() -> Vec<InstrumentInfo> {
    brasscribe_core::instruments::INSTRUMENTS
        .iter()
        .map(|i| InstrumentInfo {
            id: i.id.into(),
            name: i.name.into(),
            short_name: i.short.into(),
            chromatic: i.chromatic,
            diatonic: i.diatonic,
            clef: i.clef.as_str().into(),
            pro_low: i.pro.0,
            pro_high: i.pro.1,
            comfortable_low: i.comfortable.0,
            comfortable_high: i.comfortable.1,
            gm_program: i.gm_program,
            sound: i.sound.into(),
        })
        .collect()
}
