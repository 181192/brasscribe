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

use crate::check::{check, Violation};
use crate::instrument::{preset, Instrument};
use crate::solve::{assign, Fingering, Options};

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

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
#[serde(deny_unknown_fields)]
pub struct Request {
    pub instrument: InstrumentChoice,
    pub notes: Vec<Note>,
    #[serde(default)]
    pub options: Options,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Response {
    pub instrument: Instrument,
    pub fingering: Fingering,
    pub violations: Vec<Violation>,
}

/// Solve a [`Request`].
pub fn solve(req: &Request) -> Result<Response, String> {
    let instrument = req.instrument.resolve()?;
    let fingering = assign(&instrument, &req.notes, &req.options)?;
    let violations = check(&instrument, &req.notes, &fingering, &req.options);
    Ok(Response { instrument, fingering, violations })
}

/// Solve a JSON [`Request`] and answer with a JSON [`Response`].
pub fn solve_json(request: &str) -> Result<String, String> {
    let req: Request = serde_json::from_str(request).map_err(|e| format!("not a fingering request: {e}"))?;
    let resp = solve(&req)?;
    serde_json::to_string(&resp).map_err(|e| e.to_string())
}
