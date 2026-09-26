//! Talking score (docs/accessibility/talking-score-spec.md): the document, the
//! announcer, navigation and the text/HTML export. Apps never build
//! announcement strings themselves.

use std::sync::Arc;

use brasscribe_core::talking_score as ts;
use serde_json::{json, Value};

use crate::{invalid, CoreError};

#[derive(Debug, Clone, uniffi::Record)]
pub struct TalkingSettings {
    /// "en" or "nb".
    pub lang: String,
    /// "written" or "concert".
    pub pitch_mode: String,
    /// "brief", "standard" or "full".
    pub verbosity: String,
    /// "scientific" or "helmholtz" (nb only).
    pub octave_style: String,
    /// In full verbosity, say "confident" for notes at or above 0.7.
    pub announce_confident: bool,
}

impl From<TalkingSettings> for ts::Settings {
    fn from(s: TalkingSettings) -> Self {
        ts::Settings { lang: s.lang, pitch_mode: s.pitch_mode, verbosity: s.verbosity, octave_style: s.octave_style, announce_confident: s.announce_confident }
    }
}

/// Default settings (English, written pitch, standard verbosity).
#[uniffi::export]
pub fn talking_settings_default() -> TalkingSettings {
    let d = ts::Settings::default();
    TalkingSettings { lang: d.lang, pitch_mode: d.pitch_mode, verbosity: d.verbosity, octave_style: d.octave_style, announce_confident: d.announce_confident }
}

/// What the previous announcement left behind (all None at the start).
#[derive(Debug, Clone, Default, uniffi::Record)]
pub struct TalkingContext {
    #[uniffi(default = None)]
    pub part: Option<String>,
    #[uniffi(default = None)]
    pub bar: Option<i64>,
    #[uniffi(default = None)]
    pub pitch_mode: Option<String>,
}

impl From<TalkingContext> for ts::Context {
    fn from(c: TalkingContext) -> Self {
        ts::Context { part: c.part, bar: c.bar, pitch_mode: c.pitch_mode }
    }
}

/// Indices of part, bar and event in the document.
#[derive(Debug, Clone, Copy, PartialEq, Eq, uniffi::Record)]
pub struct TalkingCursor {
    pub part: u32,
    pub bar: u32,
    pub event: u32,
}

impl From<TalkingCursor> for ts::Cursor {
    fn from(c: TalkingCursor) -> Self {
        ts::Cursor { part: c.part as usize, bar: c.bar as usize, event: c.event as usize }
    }
}

impl From<ts::Cursor> for TalkingCursor {
    fn from(c: ts::Cursor) -> Self {
        TalkingCursor { part: c.part as u32, bar: c.bar as u32, event: c.event as u32 }
    }
}

#[derive(Debug, Clone, Copy, uniffi::Enum)]
pub enum TalkingUnit {
    /// Next event in the part, skipping tie continuations.
    Note,
    /// First event of the next bar.
    Bar,
    /// Same time position in the next part.
    Part,
    /// Next note with confidence below 0.7 that has not been checked.
    Uncertain,
}

impl From<TalkingUnit> for ts::Unit {
    fn from(u: TalkingUnit) -> Self {
        match u {
            TalkingUnit::Note => ts::Unit::Note,
            TalkingUnit::Bar => ts::Unit::Bar,
            TalkingUnit::Part => ts::Unit::Part,
            TalkingUnit::Uncertain => ts::Unit::Uncertain,
        }
    }
}

#[derive(Debug, Clone, uniffi::Record)]
pub struct TalkingBarLines {
    pub heading: String,
    pub lines: Vec<String>,
}

/// A TalkingScore document (spec §6), built once per score.
#[derive(uniffi::Object)]
pub struct TalkingScore {
    doc: Value,
}

#[uniffi::export]
impl TalkingScore {
    /// From partwise MusicXML text plus the Composition JSON when known
    /// (confidence, sources, performed time, free regions).
    #[uniffi::constructor]
    pub fn new(musicxml: String, composition_json: Option<String>) -> Result<Arc<Self>, CoreError> {
        let comp: Option<Value> = composition_json.map(|c| serde_json::from_str(&c)).transpose().map_err(invalid)?;
        Ok(Arc::new(TalkingScore { doc: ts::build(&musicxml, comp.as_ref()).map_err(invalid)? }))
    }

    /// The document as JSON (spec §6 shape).
    pub fn to_json(&self) -> String {
        brasscribe_core::pyjson::dumps(&self.doc)
    }

    pub fn title(&self) -> String {
        self.doc["title"].as_str().unwrap_or("").to_string()
    }

    pub fn total_bars(&self) -> u32 {
        self.doc["total_bars"].as_u64().unwrap_or(0) as u32
    }

    pub fn part_names(&self) -> Vec<String> {
        self.doc["parts"].as_array().map(|a| a.iter().map(|p| p["name"].as_str().unwrap_or("").to_string()).collect()).unwrap_or_default()
    }

    pub fn bar_count(&self, part: u32) -> u32 {
        ts::shape(&self.doc).get(part as usize).map(|b| b.len() as u32).unwrap_or(0)
    }

    pub fn event_count(&self, part: u32, bar: u32) -> u32 {
        ts::shape(&self.doc).get(part as usize).and_then(|b| b.get(bar as usize)).map(|n| *n as u32).unwrap_or(0)
    }

    /// The announcement at `cursor`, arriving from `context`. `by_bar`: the
    /// user navigated by bar. The caller then stores the new context:
    /// {part name, bar number, pitch mode}.
    pub fn announce(&self, cursor: TalkingCursor, context: TalkingContext, settings: TalkingSettings, by_bar: bool) -> Result<String, CoreError> {
        ts::announce_at(&self.doc, cursor.into(), &context.into(), &settings.into(), by_bar).map_err(invalid)
    }

    /// The context an announcement at `cursor` leaves behind.
    pub fn context_at(&self, cursor: TalkingCursor, settings: TalkingSettings) -> TalkingContext {
        let p = &self.doc["parts"][cursor.part as usize];
        TalkingContext {
            part: p["name"].as_str().map(String::from),
            bar: p["bars"][cursor.bar as usize]["number"].as_i64(),
            pitch_mode: Some(settings.pitch_mode),
        }
    }

    /// One step from `cursor`; None at either end.
    pub fn navigate(&self, cursor: TalkingCursor, unit: TalkingUnit, forward: bool) -> Option<TalkingCursor> {
        ts::navigate(&self.doc, cursor.into(), unit.into(), forward).map(Into::into)
    }

    /// Every bar of a part with its announcements, as the export reads them.
    pub fn part_lines(&self, part: u32, settings: TalkingSettings) -> Vec<TalkingBarLines> {
        if part as usize >= ts::shape(&self.doc).len() {
            return Vec::new();
        }
        ts::part_lines(&self.doc, part as usize, &settings.into()).into_iter().map(|(heading, lines)| TalkingBarLines { heading, lines }).collect()
    }

    /// Plain-text export (all parts when `parts` is None).
    pub fn to_text(&self, settings: TalkingSettings, parts: Option<Vec<u32>>) -> String {
        let p: Option<Vec<usize>> = parts.map(|v| v.into_iter().map(|x| x as usize).collect());
        ts::to_text(&self.doc, &settings.into(), p.as_deref())
    }

    /// HTML export (all parts when `parts` is None).
    pub fn to_html(&self, settings: TalkingSettings, parts: Option<Vec<u32>>) -> String {
        let p: Option<Vec<usize>> = parts.map(|v| v.into_iter().map(|x| x as usize).collect());
        ts::to_html(&self.doc, &settings.into(), p.as_deref())
    }
}

/// Announce one event given as JSON, outside a document: `request` is
/// `{"part": {...}, "bar": {...}, "event": {...}, "context": {...}, "settings": {...}, "by_bar": false}`
/// (see `talking_score::bar_from_json` for the bar fields). This is the form
/// the conformance vectors take.
#[uniffi::export]
pub fn talking_announce_json(request: String) -> Result<String, CoreError> {
    announce_json(&request).map_err(invalid)
}

pub(crate) fn announce_json(request: &str) -> Result<String, String> {
    let v: Value = serde_json::from_str(request).map_err(|e| e.to_string())?;
    let n = Value::Null;
    let g = |k: &str| v.get(k).unwrap_or(&n);
    Ok(ts::announce(
        &ts::part_from_json(g("part")),
        &ts::bar_from_json(g("bar")),
        v.get("event").unwrap_or(&json!({})),
        &ts::context_from_json(g("context")),
        &ts::settings_from_json(g("settings")),
        v.get("by_bar").and_then(|x| x.as_bool()).unwrap_or(false),
    ))
}

impl TalkingScore {
    pub(crate) fn doc(&self) -> &Value {
        &self.doc
    }

    pub(crate) fn from_doc(doc: Value) -> TalkingScore {
        TalkingScore { doc }
    }
}
