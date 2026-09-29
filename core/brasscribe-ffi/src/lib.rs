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
use brasscribe_core::energy::Audio;
use brasscribe_core::midi::{MidiFile, RawNote};
use brasscribe_core::model::Composition;
use brasscribe_core::musicxml::{band_score, write_score};
use brasscribe_core::pipeline::{self, Beats, Layers, LayersOptions, SongInputs};
use brasscribe_core::quantize::{choose_level, fill_gaps, quantize};

pub mod c_api;
pub mod humanize;
pub mod talking;

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

/// Options of [`arrange_musicxml_with`].
#[derive(Debug, Clone, uniffi::Record)]
pub struct ArrangeOptions {
    /// "band" (= "full", the 18-part contest band), "minimal" (8 parts) or "quartet"
    /// (1st Cornet, 2nd Cornet, Tenor Horn, Euphonium). A composition without layers
    /// (a whole-band recording) is arranged for the minimal band or the quartet; "band"
    /// gives the minimal band there.
    #[uniffi(default = "band")]
    pub lineup: String,
    /// "faithful", "standard" or "easier".
    #[uniffi(default = "faithful")]
    pub difficulty: String,
    /// Target concert key of the first key signature (Bb, F#, Am or FIFTHS[:MODE]).
    #[uniffi(default = None)]
    pub key: Option<String>,
    /// Transposition from the recording in semitones (instead of `key`): the total, as the
    /// composition's `arrangement.transpose_semitones` records it, so a composition that is
    /// already transposed by that much is not moved again.
    #[uniffi(default = None)]
    pub transpose: Option<i32>,
    /// The player's seat (`seats()` ids, e.g. "euphonium"): a solo take is written for it (one
    /// part, the seat's, in the octave played); a band take's notes do not change. None: no seat.
    #[uniffi(default = None)]
    pub seat: Option<String>,
    /// "treble" or "bass": the clef the seat's part is written in (bass: at concert pitch, no
    /// transposition); None: the brass-band part's own.
    #[uniffi(default = None)]
    pub reads: Option<String>,
    /// Who plays the tune: "lineup" (None: the lineup's lead) or "seat" (the seat's part; band
    /// lineups only, the quartet keeps its 1st Cornet). A solo take with a seat is always "seat".
    #[uniffi(default = None)]
    pub lead: Option<String>,
}

impl Default for ArrangeOptions {
    fn default() -> Self {
        ArrangeOptions { lineup: "band".into(), difficulty: "faithful".into(), key: None, transpose: None, seat: None, reads: None, lead: None }
    }
}

/// Re-arrange a Composition for a lineup and difficulty (optionally transposed) and
/// return MusicXML (written pitch). A take with layers (solo with band) can have any
/// lineup; a whole-band take gets the minimal band or the quartet. The arrangers read the
/// options from the composition's `arrangement`, which is set from them for this call
/// only (the composition itself is not returned).
#[uniffi::export]
pub fn arrange_musicxml_with(composition_json: String, options: ArrangeOptions) -> Result<String, CoreError> {
    arrange_with_impl(&composition_json, &options)
}

pub(crate) fn arrange_with_impl(composition_json: &str, o: &ArrangeOptions) -> Result<String, CoreError> {
    use brasscribe_core::instruments::{check_reads, lead_lineup, lineup_by_name, lineup_key, seat_by_id, LEADS};

    let mut comp = Composition::from_json_str(composition_json).map_err(invalid)?;
    let key = lineup_key(&o.lineup).map_err(invalid)?;
    let difficulty = if o.difficulty.is_empty() { "faithful" } else { o.difficulty.as_str() };
    if !brasscribe_core::difficulty::MODES.contains(&difficulty) {
        return Err(invalid(format!("difficulty must be one of {:?}", brasscribe_core::difficulty::MODES)));
    }
    if o.key.is_some() && o.transpose.is_some() {
        return Err(invalid("give a key or a transposition, not both"));
    }
    let lead = o.lead.as_deref().filter(|l| !l.is_empty()).unwrap_or("lineup");
    if !LEADS.contains(&lead) {
        return Err(invalid(format!("lead must be one of {LEADS:?}")));
    }
    match &o.seat {
        Some(s) => {
            seat_by_id(s).map_err(invalid)?;
        }
        None if lead == "seat" => return Err(invalid("lead seat needs a seat")),
        None => {}
    }
    check_reads(o.seat.as_deref(), o.reads.as_deref()).map_err(invalid)?;
    let before = comp.arrangement.as_ref().and_then(|a| a.get("transpose_semitones")).and_then(|v| v.as_i64()).unwrap_or(0) as i32;
    let shift = match (&o.transpose, &o.key) {
        (Some(t), _) => *t - before,
        (None, Some(k)) => {
            let first = comp.keys.first().ok_or_else(|| invalid("composition has no key"))?;
            brasscribe_core::keys::semitones_to(first, k).map_err(invalid)?
        }
        _ => 0,
    };
    if shift != 0 {
        comp = comp.transposed(shift);
    }
    let layered = comp.voices.iter().any(|v| v.layer.is_some());
    // Only the layered arranger writes the full band.
    let key = if !layered && key == "band" { "minimal" } else { key };
    let mut a = serde_json::Map::new();
    a.insert("lineup".into(), key.into());
    a.insert("difficulty".into(), difficulty.into());
    a.insert("transpose_semitones".into(), (before + shift).into());
    let solo_take = brasscribe_core::arranger::is_solo_take(&comp);
    if let Some(s) = &o.seat {
        if solo_take && seat_by_id(s).map_err(invalid)?.reads.is_empty() {
            return Err(invalid(brasscribe_core::instruments::PERCUSSION_SOLO));
        }
        a.insert("seat".into(), s.as_str().into());
        if let Some(r) = &o.reads {
            a.insert("reads".into(), r.as_str().into());
        }
        if lead == "seat" || solo_take {
            a.insert("lead".into(), "seat".into());
        }
        if lead == "seat" && !solo_take {
            lead_lineup(lineup_by_name(key).map_err(invalid)?, s).map_err(invalid)?;
        }
    }
    comp.arrangement = Some(serde_json::Value::Object(a));
    // The lineup as the composition now records it (seat, reading and lead included).
    let lineup = brasscribe_core::arranger::composition_lineup(&comp).0;
    let arr = if layered {
        brasscribe_core::arranger::arrange_layers_opts(&comp, lineup, &brasscribe_core::arranger::LayersArrangeOptions { difficulty: difficulty.into(), ..Default::default() })
    } else {
        brasscribe_core::arranger::arrange_opts(&comp, lineup, difficulty)
    }
    .map_err(failed)?;
    Ok(write_score(&band_score(&arr, &comp)))
}

pub(crate) fn arrange_impl(composition_json: &str, arranger: &str) -> Result<String, CoreError> {
    let comp = Composition::from_json_str(composition_json).map_err(invalid)?;
    let layered = match arranger {
        "layers" => true,
        "minimal" => false,
        "auto" | "" => comp.voices.iter().any(|v| v.layer.is_some()),
        other => return Err(invalid(format!("unknown arranger {other}"))),
    };
    let arr = if layered && comp.arrangement.is_some() {
        pipeline::arrange_composition(&comp).map_err(invalid)?
    } else if layered {
        arrange_layers(&comp)
    } else {
        arrange(&comp)
    };
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
    /// SwiftF0 voicing confidence per frame (for the notes' calibrated confidence).
    #[uniffi(default = None)]
    pub confidence: Option<Vec<f64>>,
}

fn midi(b: &[u8]) -> Result<MidiFile, CoreError> {
    MidiFile::parse(b).map_err(invalid)
}

/// WAV file bytes of the separated stems (PCM 16/24/32-bit or float32). Each is
/// optional; the energy gate, separation check, dynamics and rehearsal marks
/// use whichever are given.
#[derive(Debug, Clone, Default, uniffi::Record)]
pub struct LayerStems {
    #[uniffi(default = None)]
    pub solo: Option<Vec<u8>>,
    #[uniffi(default = None)]
    pub bass: Option<Vec<u8>>,
    #[uniffi(default = None)]
    pub drums: Option<Vec<u8>>,
    #[uniffi(default = None)]
    pub orchestra: Option<Vec<u8>>,
}

/// Options of the solo-with-band arrangement (defaults: everything on).
#[derive(Debug, Clone, uniffi::Record)]
pub struct LayersSongOptions {
    /// SwiftF0 contour of the solo stem: where sustained solo notes really end.
    pub solo_contour: Option<SoloContour>,
    /// Detect free-time (ad lib.) passages.
    pub free_time: bool,
    /// Notate free-time passages at this BPM instead of estimating one.
    pub free_tempo: Option<f64>,
    /// Drop layer notes where the layer's stem is silent.
    pub gate: bool,
    /// Clean up the tracked beats (tempo agreement, downbeat phase).
    pub beat_cleanup: bool,
    /// Allow key changes (otherwise one key for the whole piece).
    pub key_changes: bool,
    /// "band" (the 18-part contest band), "minimal" (8 parts) or "quartet"
    /// (1st Cornet, 2nd Cornet, Tenor Horn, Euphonium, one player each).
    pub lineup: String,
    /// "faithful", "standard" or "easier".
    pub difficulty: String,
    /// Target concert key of the first key signature (Bb, F#, Am or FIFTHS[:MODE]).
    pub key: Option<String>,
    /// Transpose the whole arrangement by this many semitones (instead of `key`).
    pub transpose: Option<i32>,
    /// The player's seat (`seats()` ids, e.g. "euphonium"): a solo take is written for it (one
    /// part, the seat's, in the octave played); a band take's notes do not change. None: no seat.
    #[uniffi(default = None)]
    pub seat: Option<String>,
    /// "treble" or "bass": the clef the seat's part is written in (bass: at concert pitch, no
    /// transposition); None: the brass-band part's own.
    #[uniffi(default = None)]
    pub reads: Option<String>,
    /// Who plays the tune: "lineup" (None: the lineup's lead) or "seat" (the seat's part; band
    /// lineups only, the quartet keeps its 1st Cornet). A solo take with a seat is always "seat".
    #[uniffi(default = None)]
    pub lead: Option<String>,
    /// Language of the footer on the arranged parts ("Arranged by Brasscribe from the band's
    /// harmony."): "en" (None) or "nb".
    #[uniffi(default = None)]
    pub lang: Option<String>,
}

impl Default for LayersSongOptions {
    fn default() -> Self {
        LayersSongOptions {
            solo_contour: None,
            free_time: true,
            free_tempo: None,
            gate: true,
            beat_cleanup: true,
            key_changes: true,
            lineup: "band".into(),
            difficulty: "faithful".into(),
            key: None,
            transpose: None,
            seat: None,
            reads: None,
            lead: None,
            lang: None,
        }
    }
}

/// One part of the band as its own MusicXML file.
#[derive(Debug, Clone, uniffi::Record)]
pub struct PartScore {
    pub file_name: String,
    pub musicxml: String,
}

/// Everything the band arrangement writes.
#[derive(Debug, Clone, uniffi::Record)]
pub struct BandOutput {
    pub composition_json: String,
    pub musicxml: String,
    pub parts: Vec<PartScore>,
    /// `separation-check.json` text, when stems were given.
    pub separation_check_json: Option<String>,
}

fn stem(b: Option<&[u8]>) -> Result<Option<Audio>, CoreError> {
    b.map(|b| Audio::from_wav(b).map_err(invalid)).transpose()
}

/// The layer inputs as borrowed bytes: six MIDI files (solo SwiftF0, solo MuScriptor, solo Basic
/// Pitch, bass, orchestra, drums) and four optional WAV stems (solo, bass, drums, orchestra). The
/// C ABI builds this straight from the caller's buffers, so no stem is copied before it is decoded.
pub(crate) struct LayerBytes<'a> {
    pub midi: [&'a [u8]; 6],
    pub stems: [Option<&'a [u8]>; 4],
}

impl LayerMidi {
    fn bytes(&self) -> [&[u8]; 6] {
        [&self.solo_swiftf0, &self.solo_muscriptor, &self.solo_basic_pitch, &self.bass, &self.orchestra, &self.drums]
    }
}

impl LayerStems {
    fn bytes(&self) -> [Option<&[u8]>; 4] {
        [self.solo.as_deref(), self.bass.as_deref(), self.drums.as_deref(), self.orchestra.as_deref()]
    }
}

pub(crate) fn band_impl(layers: &LayerMidi, stems: &LayerStems, beats_text: &str, title: &str, mut o: LayersSongOptions) -> Result<BandOutput, CoreError> {
    let contour = o.solo_contour.take().map(|c| Contour::from_hz(c.times, &c.pitch_hz, c.loudness_db).with_confidence(c.confidence));
    band_bytes(&LayerBytes { midi: layers.bytes(), stems: stems.bytes() }, beats_text, title, o, contour)
}

/// [`band_impl`] on borrowed inputs, with the solo contour already built (`o.solo_contour` is not read).
pub(crate) fn band_bytes(b: &LayerBytes, beats_text: &str, title: &str, o: LayersSongOptions, contour: Option<Contour>) -> Result<BandOutput, CoreError> {
    let [solo_sw, solo_mus, solo_bp, bass, orchestra, drums] = b.midi;
    let [solo_audio, bass_audio, drums_audio, orchestra_audio] = b.stems;
    let l = Layers {
        solo_sw: midi(solo_sw)?,
        solo_mus: midi(solo_mus)?,
        solo_bp: midi(solo_bp)?,
        bass: midi(bass)?,
        orchestra: midi(orchestra)?,
        drums: midi(drums)?,
        solo_audio: stem(solo_audio)?,
        bass_audio: stem(bass_audio)?,
        drums_audio: stem(drums_audio)?,
        orchestra_audio: stem(orchestra_audio)?,
    };
    let beats = Beats::parse(beats_text).map_err(invalid)?;
    let opts = LayersOptions {
        solo_contour: contour,
        no_free_time: !o.free_time,
        free_tempo: o.free_tempo,
        no_gate: !o.gate,
        no_beat_cleanup: !o.beat_cleanup,
        single_key: !o.key_changes,
        lineup: o.lineup,
        difficulty: o.difficulty,
        key: o.key,
        transpose: o.transpose,
        seat: o.seat,
        reads: o.reads,
        lead: o.lead.unwrap_or_default(),
        lang: o.lang.unwrap_or_default(),
    };
    let r = pipeline::arrange_layers_song(&l, &beats, title, &opts).map_err(failed)?;
    Ok(BandOutput {
        composition_json: r.composition.to_json_string(),
        musicxml: r.musicxml,
        parts: r.parts.into_iter().map(|(file_name, musicxml)| PartScore { file_name, musicxml }).collect(),
        separation_check_json: r.separation_check,
    })
}

/// Solo-with-band arrangement from layer transcriptions, the stems' audio and
/// a beat table (`time position` per line, position 1 = downbeat): the score,
/// every part, the Composition and the separation check.
#[uniffi::export]
pub fn arrange_layers_band(layers: LayerMidi, stems: LayerStems, beats_text: String, title: String, options: LayersSongOptions) -> Result<BandOutput, CoreError> {
    band_impl(&layers, &stems, &beats_text, &title, options)
}

/// Default options of [`arrange_layers_band`].
#[uniffi::export]
pub fn layers_song_defaults() -> LayersSongOptions {
    LayersSongOptions::default()
}

/// Solo-with-band arrangement from layer transcriptions and a beat table,
/// without stems (no energy gate, dynamics or rehearsal marks).
#[uniffi::export]
pub fn arrange_layers_song(
    layers: LayerMidi,
    beats_text: String,
    title: String,
    solo_contour: Option<SoloContour>,
    free_time: bool,
    free_tempo: Option<f64>,
) -> Result<SongOutput, CoreError> {
    let o = LayersSongOptions { solo_contour, free_time, free_tempo, ..Default::default() };
    let r = band_impl(&layers, &LayerStems::default(), &beats_text, &title, o)?;
    Ok(SongOutput { composition_json: r.composition_json, musicxml: r.musicxml })
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
    let raw: Vec<RawNote> = notes.iter().map(|n| RawNote { pitch: n.pitch, onset: n.onset, offset: n.offset, confidence: n.confidence, split: false }).collect();
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

/// The player's part in a lineup for their seat.
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SeatPart {
    /// The lineup's part name for the seat; None: the lineup has none (percussion outside the band).
    pub part: Option<String>,
    /// The seat's own part.
    pub exact: bool,
    /// The part is in the seat's key (transposition), so it reads without transposing.
    pub same_key: bool,
    /// The lineup's part the seat's own part replaces ("Solo Cornet" for a trumpet in the bands): the
    /// score writes `part` in its place. None for every band seat.
    pub takes: Option<String>,
}

/// Which part of `lineup` ("band", "minimal" or "quartet") is the player's, for `seat`. One table in
/// the core for every app.
#[uniffi::export]
pub fn seat_part(lineup: String, seat: String) -> Result<SeatPart, CoreError> {
    let sp = brasscribe_core::instruments::seat_part(&lineup, &seat).map_err(invalid)?;
    Ok(SeatPart { part: sp.part.map(String::from), exact: sp.exact, same_key: sp.same_key, takes: sp.takes.map(String::from) })
}

/// Where one part comes from: "your-recording" (a solo take's own line), "recording" (a line heard
/// in the recording) or "arranged" (voiced from the band's harmony).
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct PartSource {
    pub part: String,
    pub source: String,
}

/// Where each part of a Composition's arrangement comes from, in score order.
#[uniffi::export]
pub fn part_sources(composition_json: String) -> Result<Vec<PartSource>, CoreError> {
    let comp = Composition::from_json_str(&composition_json).map_err(invalid)?;
    Ok(brasscribe_core::arranger::part_sources(&comp).into_iter().map(|(part, s)| PartSource { part, source: s.into() }).collect())
}

/// A part's name in Norwegian («Solokornett», «Solo althorn», «1. kornett», «Althorn»): the core's one
/// table, covering the band, small band and quartet parts. Names it doesn't know come back unchanged.
#[uniffi::export]
pub fn part_name_nb(name: String) -> String {
    brasscribe_core::talking_score::nb_part_name(&name).to_string()
}

/// One seat of the contest band, for the "What do you play?" picker.
#[derive(Debug, Clone, PartialEq, uniffi::Record)]
pub struct SeatInfo {
    /// Stable id (the `seat` option).
    pub id: String,
    /// The part's English name ("2nd Cornet"), as the band score prints it.
    pub name: String,
    /// The part's Norwegian name («2. kornett», «Solo althorn»): the core's one table.
    pub nb_name: String,
    /// Instrument id (`instruments()`).
    pub instrument: String,
    /// The part's own clef: "treble", "bass" or "percussion".
    pub clef: String,
    /// Clefs the player may read it in (the `reads` option), the part's own first; empty for percussion.
    pub reads: Vec<String>,
    /// The part can carry the tune (Role Melody or Solo, not the bass line): the seats offered
    /// "Who plays the tune?" (the `lead` option "seat").
    pub tune: bool,
}

/// The seats: the 18 of the contest band in score order, then the trumpet (it takes the lead part).
#[uniffi::export]
pub fn seats() -> Vec<SeatInfo> {
    brasscribe_core::instruments::SEATS
        .iter()
        .map(|s| {
            let inst = s.own_part().instrument;
            SeatInfo {
                id: s.id.into(),
                name: s.part.into(),
                nb_name: brasscribe_core::talking_score::nb_part_name(s.part).into(),
                instrument: inst.id.into(),
                clef: inst.clef.as_str().into(),
                reads: s.reads.iter().map(|r| r.to_string()).collect(),
                tune: s.tune(),
            }
        })
        .collect()
}
