//! From transcriptions to an arranged band, mirroring the reference scripts:
//!
//! * [`arrange_layers_song`]: layer transcriptions + beats -> solo-with-band score
//! * [`arrange_song`]: melody/support/bass/harmony transcriptions + beats -> minimal band score
//! * [`arrange_reference`]: notated reference notes -> minimal band score (arranger benchmark)
//! * [`arrange_composition`]: an existing Composition, arranged the way it was made
//!
//! The transcription itself is the shared core's (`scribe_core::transcription`): it gives the
//! Composition, and is told what only the band knows (the range of the instrument that takes the
//! tune, what a key change costs at a difficulty). Here the Composition is arranged and written.
//!
//! Inputs are in-memory (parsed MIDI files, beat tables); nothing here touches the file system.

use serde_json::Value;

use crate::arranger::Arrangement;
use crate::musicxml::{band_score, write_score};
use scribe_core::durations::Contour;
use scribe_core::model::{Composition, KeySig};
use scribe_core::notation::score::write_score_with_parts;
use scribe_core::transcription::{composition_from_reference, transcribe_layers, transcribe_song, Beats, LayerOptions, Layers, SongInputs, FREE_TEMPO_RANGE};

#[derive(Debug, Clone)]
pub struct BandResult {
    pub composition: Composition,
    pub arrangement: Arrangement,
    pub musicxml: String,
    /// Individual parts: (file name, MusicXML), for the layered arrangement.
    pub parts: Vec<(String, String)>,
    /// `separation-check.json` text, when the layer audio was given.
    pub separation_check: Option<String>,
}

/// Options of the solo-with-band arrangement.
#[derive(Debug, Clone, Default)]
pub struct LayersOptions {
    /// Frame-level SwiftF0 contour of the solo stem: where sustained solo notes really end.
    pub solo_contour: Option<Contour>,
    /// Keep the beat grid through free-time passages.
    pub no_free_time: bool,
    /// Notate free-time passages at this BPM instead of estimating one.
    pub free_tempo: Option<f64>,
    /// Keep layer notes where the layer's audio is silent.
    pub no_gate: bool,
    /// Use the tracked beats as they are.
    pub no_beat_cleanup: bool,
    /// One key signature for the whole piece.
    pub single_key: bool,
    /// "band" (= "full", the 18-part contest band) or "minimal" (8 parts); empty = band.
    pub lineup: String,
    /// "faithful" (default when empty), "standard" or "easier".
    pub difficulty: String,
    /// Faithful: write sustained two-note alternations as trills (standard and easier always do).
    pub trills: bool,
    /// Target concert key of the first key signature: Bb, F#, Am or FIFTHS[:MODE].
    pub key: Option<String>,
    /// Transpose the whole arrangement by this many semitones (instead of `key`).
    pub transpose: Option<i32>,
    /// The player's seat (instruments::SEATS): a solo take is written for it (one part, its range, as played).
    pub seat: Option<String>,
    /// "treble" or "bass": the clef the seat's part is written in (bass: at concert pitch); None = the band's.
    pub reads: Option<String>,
    /// Who plays the tune: "lineup" (default when empty) or "seat" (a solo take always the seat).
    pub lead: String,
    /// Language of the source footer on the parts: "en" (default when empty) or "nb".
    pub lang: String,
    /// The drum kit the Percussion part plays (instruments::KITS): "band" (default when empty) or "pop".
    pub kit: String,
}

/// The solo line's window without a seat: a cornet or trumpet soloist, E3-E6.
pub const SOLO_WINDOW: (i32, i32) = (52, 88);

/// Err when an option of [`arrange_layers_song`] has no meaning (an unknown lineup, difficulty,
/// seat, clef, lead, language, kit or key, a key and a transposition together, a transposition
/// beyond [`MAX_TRANSPOSE`](scribe_core::model::MAX_TRANSPOSE) semitones, a free-time tempo outside
/// [`FREE_TEMPO_RANGE`]). Checked before anything is read, so the apps can tell a bad option
/// from a recording that could not be arranged.
pub fn check_layers_options(opts: &LayersOptions) -> Result<(), String> {
    let difficulty = if opts.difficulty.is_empty() { "faithful" } else { opts.difficulty.as_str() };
    if !crate::difficulty::MODES.contains(&difficulty) {
        return Err(format!("difficulty must be one of {:?}", crate::difficulty::MODES));
    }
    crate::instruments::lineup_key(&opts.lineup)?;
    let lang = if opts.lang.is_empty() { "en" } else { opts.lang.as_str() };
    if !crate::arranger::FOOTER_LANGS.contains(&lang) {
        return Err(format!("lang must be one of {:?}", crate::arranger::FOOTER_LANGS));
    }
    let lead = if opts.lead.is_empty() { "lineup" } else { opts.lead.as_str() };
    if !crate::instruments::LEADS.contains(&lead) {
        return Err(format!("lead must be one of {:?}", crate::instruments::LEADS));
    }
    if let Some(s) = &opts.seat {
        crate::instruments::seat_by_id(s)?;
    } else if lead == "seat" {
        return Err("lead seat needs a seat".into());
    }
    crate::instruments::check_reads(opts.seat.as_deref(), opts.reads.as_deref())?;
    if opts.key.is_some() && opts.transpose.is_some() {
        return Err("give a key or a transposition, not both".into());
    }
    if let Some(k) = &opts.key {
        // The key's syntax; the shift itself depends on the key the music turns out to be in.
        scribe_core::keys::semitones_to(&KeySig { tick: 0, fifths: 0, mode: "major".into() }, k)?;
    }
    if let Some(t) = opts.transpose {
        scribe_core::model::check_transpose(t as i64)?;
    }
    if let Some(bpm) = opts.free_tempo {
        if !(FREE_TEMPO_RANGE.0..=FREE_TEMPO_RANGE.1).contains(&bpm) {
            return Err(format!("the free-time tempo must be {} to {} BPM", FREE_TEMPO_RANGE.0, FREE_TEMPO_RANGE.1));
        }
    }
    crate::instruments::kit_program(&opts.kit)?;
    Ok(())
}

/// Solo-with-band arrangement from textural layers: the shared transcription of the layers
/// ([`transcribe_layers`]), then the arrangement for the lineup, the score and the parts.
pub fn arrange_layers_song(layers: &Layers, beats: &Beats, title: &str, opts: &LayersOptions) -> Result<BandResult, String> {
    check_layers_options(opts)?;
    let difficulty = if opts.difficulty.is_empty() { "faithful" } else { opts.difficulty.as_str() };
    let lineup_name = crate::instruments::lineup_key(&opts.lineup)?;
    let lang = if opts.lang.is_empty() { "en" } else { opts.lang.as_str() };
    let lead = if opts.lead.is_empty() { "lineup" } else { opts.lead.as_str() };
    let heard = LayerOptions {
        solo_contour: opts.solo_contour.as_ref(),
        no_free_time: opts.no_free_time,
        free_tempo: opts.free_tempo,
        no_gate: opts.no_gate,
        no_beat_cleanup: opts.no_beat_cleanup,
        single_key: opts.single_key,
        // Faithful keeps the solo's fast notes; standard and easier keep the simpler line.
        fast_notes: difficulty == "faithful",
        key_change_penalty: crate::difficulty::key_change_penalty(difficulty),
        key: opts.key.as_deref(),
        transpose: opts.transpose,
        solo_hint: "trumpet/cornet",
    };
    let mut solo_take = false;
    let t = transcribe_layers(layers, beats, title, &heard, |solo_only| {
        // A solo take (no other layer has notes) for a seat keeps the seat instrument's range; otherwise
        // the solo line is the soloist's, a cornet or trumpet (E3-E6).
        solo_take = opts.seat.is_some() && solo_only;
        if let Some(s) = opts.seat.as_deref().filter(|_| solo_take) {
            if crate::instruments::seat_by_id(s)?.reads.is_empty() {
                return Err(crate::instruments::PERCUSSION_SOLO.into());
            }
        }
        let window = match &opts.seat {
            Some(s) if solo_take => crate::instruments::seat_by_id(s)?.own_part().instrument.pro,
            _ => SOLO_WINDOW,
        };
        if let (Some(s), false) = (&opts.seat, solo_take) {
            if lead == "seat" {
                crate::instruments::lead_lineup(crate::instruments::lineup_by_name(lineup_name)?, s).map_err(|e| format!("--lead seat: {e}"))?;
            }
        }
        Ok(window)
    })?;
    let (mut comp, shift) = (t.composition, t.transposed);
    // Arrangement options: lineup, difficulty, transposition to a concert key.
    let kit = if crate::instruments::kit_program(&opts.kit)? == 0 { "band" } else { opts.kit.as_str() };
    if lineup_name != "band" || difficulty != "faithful" || shift != 0 || opts.seat.is_some() || opts.trills || kit != "band" {
        let mut a = serde_json::Map::new();
        a.insert("lineup".into(), lineup_name.into());
        a.insert("difficulty".into(), difficulty.into());
        a.insert("transpose_semitones".into(), shift.into());
        if opts.trills {
            a.insert("trills".into(), true.into());
        }
        if let Some(s) = &opts.seat {
            // The seat's options, like the others; the arrangers read them back (composition_lineup).
            a.insert("seat".into(), s.as_str().into());
            if let Some(r) = &opts.reads {
                a.insert("reads".into(), r.as_str().into());
            }
            if solo_take || lead == "seat" {
                a.insert("lead".into(), "seat".into());
            }
        }
        if kit != "band" {
            a.insert("kit".into(), kit.into());
        }
        comp.arrangement = Some(serde_json::Value::Object(a));
    }
    let lineup = crate::arranger::composition_lineup(&comp).0;
    let trills = if opts.trills { Some(true) } else { None };
    let arrangement = crate::arranger::arrange_layers_opts(&comp, lineup, &crate::arranger::LayersArrangeOptions { difficulty: difficulty.into(), trills, ..Default::default() })?;
    let (musicxml, parts) = write_score_with_parts(&band_score(&arrangement, &comp), &crate::arranger::part_footers(&comp, lang));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts, separation_check: t.separation_check })
}

/// The trill option a Composition was arranged with (`arrangement.trills`); None: the difficulty's default.
pub fn recorded_trills(comp: &Composition) -> Option<bool> {
    comp.arrangement.as_ref().and_then(|a| a.get("trills")).and_then(|v| v.as_bool())
}

/// Arrange an existing Composition the way it was made: the layered arranger
/// when its voices carry layers (with the lineup and difficulty recorded in
/// `arrangement`), else the minimal arranger.
pub fn arrange_composition(comp: &Composition) -> Result<Arrangement, String> {
    let opt = |k: &str| comp.arrangement.as_ref().and_then(|a| a.get(k)).and_then(|v| v.as_str()).map(String::from);
    let (lineup, layered) = crate::arranger::composition_lineup(comp);
    if !layered {
        if lineup != crate::instruments::minimal_band() {
            let difficulty = opt("difficulty").filter(|d| !d.is_empty()).unwrap_or_else(|| "faithful".into());
            return crate::arranger::arrange_opts_trills(comp, lineup, &difficulty, recorded_trills(comp));
        }
        return crate::arranger::arrange_opts_trills(comp, crate::instruments::minimal_band(), "faithful", recorded_trills(comp));
    }
    let difficulty = opt("difficulty").unwrap_or_else(|| "faithful".into());
    crate::arranger::arrange_layers_opts(comp, lineup, &crate::arranger::LayersArrangeOptions { difficulty, trills: recorded_trills(comp), ..Default::default() })
}

/// Options of the song arrangement.
#[derive(Debug, Clone, Default)]
pub struct SongOptions {
    /// "minimal" (8 parts; the default when empty) or "quartet".
    pub lineup: String,
    /// The player's seat (instruments::SEATS): their part; with `lead` "seat", the tune's.
    pub seat: Option<String>,
    /// "treble" or "bass": the clef the seat's part is written in (bass: at concert pitch); None = the band's.
    pub reads: Option<String>,
    /// Who plays the tune: "lineup" (default when empty) or "seat".
    pub lead: String,
    /// The drum kit the Percussion part plays (instruments::KITS): "band" (default when empty) or "pop".
    pub kit: String,
}

/// The option value of a song lineup and the lineup ("" -> minimal).
fn song_lineup(name: &str) -> Result<(&'static str, crate::instruments::Lineup), String> {
    match name {
        "" | "minimal" => Ok(("minimal", crate::instruments::minimal_band())),
        "quartet" => Ok(("quartet", crate::instruments::quartet())),
        other => Err(format!("unknown song lineup {other} (minimal or quartet)")),
    }
}

/// Records a non-default lineup (and kit) of the non-layered arrangers in the composition.
fn record_lineup(comp: &mut Composition, key: &str, seat: Option<&str>, reads: Option<&str>, lead: &str, kit: &str) {
    if key != "minimal" || seat.is_some() || kit != "band" {
        let mut a = serde_json::Map::new();
        a.insert("lineup".into(), key.into());
        a.insert("difficulty".into(), "faithful".into());
        a.insert("transpose_semitones".into(), 0.into());
        if let Some(s) = seat {
            a.insert("seat".into(), s.into());
            if let Some(r) = reads {
                a.insert("reads".into(), r.into());
            }
            if lead == "seat" {
                a.insert("lead".into(), "seat".into());
            }
        }
        if kit != "band" {
            a.insert("kit".into(), kit.into());
        }
        comp.arrangement = Some(serde_json::Value::Object(a));
    }
}

/// Minimal brass-band arrangement: melody (MuScriptor confirmed by Basic Pitch),
/// bass line, and the accompaniment reduced to a per-beat harmonic rhythm.
pub fn arrange_song(inp: &SongInputs, beats: &Beats, title: &str) -> Result<BandResult, String> {
    arrange_song_opts(inp, beats, title, &SongOptions::default())
}

/// What [`arrange_song_opts`] refuses in its options, before it reads a note: an unknown lineup, lead, seat
/// or clef, and a tune the seat cannot carry in the lineup. The bindings ask this first, so a refused option
/// is invalid input there and not a failed arrangement.
pub fn check_song_options(opts: &SongOptions) -> Result<(), String> {
    song_window(opts).map(|_| ())
}

/// The range the melody is taken in, with the lineup as the composition records it; checks the options.
fn song_window(opts: &SongOptions) -> Result<(&'static str, crate::instruments::Lineup, &'static str, (i32, i32)), String> {
    let (lineup_key, lineup) = song_lineup(&opts.lineup)?;
    let lead = if opts.lead.is_empty() { "lineup" } else { opts.lead.as_str() };
    let lead = *crate::instruments::LEADS
        .iter()
        .find(|l| **l == lead)
        .ok_or_else(|| format!("lead must be one of {:?}", crate::instruments::LEADS))?;
    crate::instruments::check_reads(opts.seat.as_deref(), opts.reads.as_deref())?;
    // With the tune on the player's part, the melody is taken in that part's range.
    let window = match (&opts.seat, lead) {
        (Some(s), "seat") => crate::instruments::lead_lineup(lineup.clone(), s)?.lead_part().instrument.pro,
        (None, "seat") => return Err("lead seat needs a seat".into()),
        (Some(s), _) => {
            crate::instruments::seat_by_id(s)?;
            SOLO_WINDOW
        }
        _ => SOLO_WINDOW,
    };
    Ok((lineup_key, lineup, lead, window))
}

/// [`arrange_song`] for a lineup (minimal band or quartet), recorded in the composition.
pub fn arrange_song_opts(inp: &SongInputs, beats: &Beats, title: &str, opts: &SongOptions) -> Result<BandResult, String> {
    let (lineup_key, _, lead, window) = song_window(opts)?;
    let mut comp = transcribe_song(inp, beats, title, window)?;
    let kit = if crate::instruments::kit_program(&opts.kit)? == 0 { "band" } else { opts.kit.as_str() };
    record_lineup(&mut comp, lineup_key, opts.seat.as_deref(), opts.reads.as_deref(), lead, kit);
    let arrangement = crate::arranger::arrange_opts(&comp, crate::arranger::composition_lineup(&comp).0, "faithful")?;
    let musicxml = write_score(&band_score(&arrangement, &comp));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts: Vec::new(), separation_check: None })
}

/// Arranger benchmark path: reference -> Composition -> minimal band score.
pub fn arrange_reference(reference: &Value, title: &str) -> Result<BandResult, String> {
    arrange_reference_with(reference, title, "")
}

/// [`arrange_reference`] for a lineup (minimal band or quartet), recorded in the composition.
pub fn arrange_reference_with(reference: &Value, title: &str, lineup: &str) -> Result<BandResult, String> {
    let (lineup_key, lineup) = song_lineup(lineup)?;
    let mut comp = composition_from_reference(reference, title)?;
    record_lineup(&mut comp, lineup_key, None, None, "lineup", "band");
    let arrangement = crate::arranger::arrange_opts(&comp, lineup, "faithful")?;
    let musicxml = write_score(&band_score(&arrangement, &comp));
    Ok(BandResult { composition: comp, arrangement, musicxml, parts: Vec::new(), separation_check: None })
}
