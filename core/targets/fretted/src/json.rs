//! JSON in and out, for callers outside Rust.
//!
//! Request:
//! ```json
//! {"instrument": {"preset": "guitar-standard", "capo": 2},
//!  "notes": [{"pitch": 64, "start": 0, "dur": 24}],
//!  "options": {"style": "open-position", "tempo_bpm": 96, "pins": [{"note": 0, "string": 2}]}}
//! ```
//! `instrument` is a preset id (with an optional capo) or a full [`Instrument`]. `options` may be
//! left out. The response holds the instrument used, the fingering and any hard violations.

use brasscribe_core::model::Note;
use serde::{Deserialize, Serialize};

use crate::check::{check_with_techniques, Violation};
use crate::instrument::{preset, preset_family, Instrument};
use crate::solve::{assign_with_techniques, Fingering, Options};
use crate::suggest::{suggest_tunings, TuningFit};
use crate::tab::{write_tab_musicxml, TabDocument, TabOptions, TabScore};
use crate::instructions::write_playing_instructions;
use crate::technique::Technique;
use crate::text::{write_tab_text, TextOptions};

#[derive(Debug, Clone, PartialEq, Serialize)]
#[serde(untagged)]
pub enum InstrumentChoice {
    Preset {
        preset: String,
        #[serde(default)]
        capo: u8,
    },
    Custom(Instrument),
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PresetChoice {
    preset: String,
    #[serde(default)]
    capo: u8,
}

/// An object with a `preset` key is a preset (only `capo` may go with it); any other object is a
/// full instrument. Either way an error names what was wrong rather than "no variant matched".
impl<'de> Deserialize<'de> for InstrumentChoice {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        use serde::de::Error;
        let v = serde_json::Value::deserialize(d)?;
        if !v.is_object() {
            return Err(D::Error::custom("instrument: expected a preset ({\"preset\": ...}) or an instrument object"));
        }
        if v.get("preset").is_some() {
            let p = PresetChoice::deserialize(v).map_err(|e| D::Error::custom(format!("instrument preset: {e}")))?;
            Ok(InstrumentChoice::Preset { preset: p.preset, capo: p.capo })
        } else {
            Instrument::deserialize(v).map(InstrumentChoice::Custom).map_err(|e| D::Error::custom(format!("custom instrument: {e}")))
        }
    }
}

impl InstrumentChoice {
    pub fn resolve(&self) -> Result<Instrument, String> {
        match self {
            InstrumentChoice::Preset { preset: id, capo } => preset(id).map(|i| i.with_capo(*capo)).ok_or_else(|| format!("no instrument preset named {id:?}")),
            InstrumentChoice::Custom(i) => Ok(i.clone()),
        }
    }
}

/// A note of the request: the shared model's note plus the techniques it is played with.
#[derive(Debug, Clone, PartialEq, Serialize)]
pub struct InputNote {
    #[serde(flatten)]
    pub note: Note,
    #[serde(skip_serializing_if = "Vec::is_empty")]
    pub techniques: Vec<Technique>,
}

/// The keys a note of a request may have: the shared model's note and `techniques`.
pub const NOTE_KEYS: [&str; 11] = ["pitch", "start", "dur", "confidence", "sources", "onset_s", "offset_s", "performed_dur", "articulations", "trill", "techniques"];

/// Read by hand, because a flattened struct cannot refuse unknown keys: a misspelled `techniques`
/// would otherwise be dropped without a word.
impl<'de> Deserialize<'de> for InputNote {
    fn deserialize<D: serde::Deserializer<'de>>(d: D) -> Result<Self, D::Error> {
        use serde::de::Error;
        let mut fields = serde_json::Map::<String, serde_json::Value>::deserialize(d)?;
        if let Some(key) = fields.keys().find(|k| !NOTE_KEYS.contains(&k.as_str())) {
            return Err(D::Error::custom(format!("unknown field `{key}` in a note, expected one of {}", NOTE_KEYS.join(", "))));
        }
        let techniques = match fields.remove("techniques") {
            Some(t) => Vec::<Technique>::deserialize(t).map_err(|e| D::Error::custom(format!("techniques: {e}")))?,
            None => Vec::new(),
        };
        let note = Note::deserialize(serde_json::Value::Object(fields)).map_err(D::Error::custom)?;
        Ok(InputNote { note, techniques })
    }
}

impl From<Note> for InputNote {
    fn from(note: Note) -> Self {
        InputNote { note, techniques: Vec::new() }
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub instrument: InstrumentChoice,
    pub notes: Vec<InputNote>,
    #[serde(default)]
    pub options: Options,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Response {
    pub instrument: Instrument,
    pub fingering: Fingering,
    pub violations: Vec<Violation>,
    /// For a preset instrument: the presets of its family ranked by fit to the notes, best first.
    #[serde(default)]
    pub tuning_suggestions: Vec<TuningFit>,
}

/// Solve a [`Request`].
pub fn solve(req: &Request) -> Result<Response, String> {
    let instrument = req.instrument.resolve()?;
    let notes: Vec<Note> = req.notes.iter().map(|n| n.note.clone()).collect();
    let techniques: Vec<Vec<Technique>> = req.notes.iter().map(|n| n.techniques.clone()).collect();
    let fingering = assign_with_techniques(&instrument, &notes, &techniques, &req.options)?;
    let violations = check_with_techniques(&instrument, &notes, &techniques, &fingering, &req.options);
    let tuning_suggestions = match &req.instrument {
        InstrumentChoice::Preset { preset: id, capo } => preset_family(id).map(|f| suggest_tunings(f, &notes, *capo)).unwrap_or_default(),
        InstrumentChoice::Custom(_) => Vec::new(),
    };
    Ok(Response { instrument, fingering, violations, tuning_suggestions })
}

/// Solve a JSON [`Request`] and answer with a JSON [`Response`].
pub fn solve_json(request: &str) -> Result<String, String> {
    let req: Request = serde_json::from_str(request).map_err(|e| format!("not a fingering request: {e}"))?;
    let resp = solve(&req)?;
    serde_json::to_string(&resp).map_err(|e| e.to_string())
}

/// Time signature of a [`TabRequest`].
#[derive(Debug, Clone, Copy, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct MeterChoice {
    pub beats: i64,
    #[serde(default = "four")]
    pub beat_unit: i64,
}

fn four() -> i64 {
    4
}

/// Key signature of a [`TabRequest`].
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct KeyChoice {
    pub fifths: i32,
    #[serde(default = "major")]
    pub mode: String,
}

fn major() -> String {
    "major".into()
}

/// A request for tablature: a fingering [`Request`] plus what the page says.
///
/// ```json
/// {"title": "Study", "instrument": {"preset": "guitar-standard", "capo": 2},
///  "notes": [{"pitch": 66, "start": 0, "dur": 24, "confidence": 0.3}],
///  "tempo_bpm": 96, "meter": {"beats": 3, "beat_unit": 4}, "key": {"fifths": 2},
///  "tab": {"layout": "tab", "doubt_below": 0.4}, "text": {"width": 72, "lang": "nb"}}
/// ```
/// Without `fingering` the notes are solved with `options` first; with it (a fingering from an
/// earlier response, perhaps edited) they are written where it says. `text` is read by the text
/// exports only: the text tab's line width and the language of the playing instructions.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct TabRequest {
    #[serde(default)]
    pub title: String,
    pub instrument: InstrumentChoice,
    pub notes: Vec<InputNote>,
    #[serde(default)]
    pub options: Options,
    #[serde(default)]
    pub fingering: Option<Fingering>,
    /// Quarter notes per minute; when left out, `options.tempo_bpm`, else 120.
    #[serde(default)]
    pub tempo_bpm: Option<f64>,
    #[serde(default)]
    pub meter: Option<MeterChoice>,
    #[serde(default)]
    pub key: Option<KeyChoice>,
    #[serde(default)]
    pub tab: TabOptions,
    #[serde(default)]
    pub text: TextOptions,
}

/// The score a [`TabRequest`] asks for: its notes where its fingering has them, or solved first.
fn score(req: &TabRequest) -> Result<TabScore, String> {
    let instrument = req.instrument.resolve()?;
    let notes: Vec<Note> = req.notes.iter().map(|n| n.note.clone()).collect();
    let techniques: Vec<Vec<Technique>> = req.notes.iter().map(|n| n.techniques.clone()).collect();
    let fingering = match &req.fingering {
        Some(f) => f.clone(),
        None => assign_with_techniques(&instrument, &notes, &techniques, &req.options)?,
    };
    let mut score = TabScore::new(&req.title, &instrument, &notes, &techniques, &fingering)?;
    if let Some(bpm) = req.tempo_bpm.or(req.options.tempo_bpm) {
        score = score.with_tempo(bpm);
    }
    if let Some(m) = req.meter {
        score = score.with_meter(m.beats, m.beat_unit);
    }
    if let Some(k) = &req.key {
        score = score.with_key(k.fifths, &k.mode);
    }
    Ok(score)
}

/// The tablature of a [`TabRequest`]: the MusicXML document and how many notes were moved to a
/// start or length that can be written.
pub fn tab(req: &TabRequest) -> Result<TabDocument, String> {
    write_tab_musicxml(&score(req)?, &req.tab)
}

/// The tablature of a [`TabRequest`] as plain text, its lines as wide as `text.width` allows.
pub fn tab_text(req: &TabRequest) -> Result<String, String> {
    write_tab_text(&score(req)?, &req.tab, &req.text)
}

/// The playing instructions of a [`TabRequest`], in the language of `text.lang`.
pub fn playing_instructions(req: &TabRequest) -> Result<String, String> {
    write_playing_instructions(&score(req)?, &req.tab, &req.text)
}

/// A JSON [`TabRequest`], read; Err names what is not one.
pub fn tab_request(request: &str) -> Result<TabRequest, String> {
    serde_json::from_str(request).map_err(|e| format!("not a tablature request: {e}"))
}

/// The tablature of a JSON [`TabRequest`] as JSON: `{"musicxml": "...", "adjusted_notes": 0}`.
pub fn tab_json(request: &str) -> Result<String, String> {
    let doc = tab(&tab_request(request)?)?;
    serde_json::to_string(&doc).map_err(|e| e.to_string())
}

/// The MusicXML tablature of a JSON [`TabRequest`], without the count of adjusted notes.
pub fn tab_musicxml_json(request: &str) -> Result<String, String> {
    Ok(tab(&tab_request(request)?)?.musicxml)
}

/// The text tab of a JSON [`TabRequest`]: plain text, not JSON.
pub fn tab_text_json(request: &str) -> Result<String, String> {
    tab_text(&tab_request(request)?)
}

/// The playing instructions of a JSON [`TabRequest`]: plain text, not JSON.
pub fn playing_instructions_json(request: &str) -> Result<String, String> {
    playing_instructions(&tab_request(request)?)
}
