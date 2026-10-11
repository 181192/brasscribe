//! Calibrated note confidence and the review marks ("?") drawn from it.
//!
//! A solo note's confidence is the probability that it is right, from a
//! logistic model over which transcribers found it, its length, how strongly
//! the SwiftF0 contour supports it (mean voicing confidence of the frames near
//! its pitch over its first 0.3 s) and whether the solo was separated from a
//! mix. The weights, input ranges and mark thresholds are in calibration.json
//! (the same file as the Python reference's). A note is marked when its risk
//! of being wrong is at least `mark_risk`, boxed at `very_risk`; neighbouring
//! marked notes form one review group with a single mark.

use std::collections::BTreeSet;

use serde_json::Value;

use crate::durations::Contour;
use crate::py;

/// Seconds of the note's start over which the contour's voicing is averaged.
pub const SUPPORT_WINDOW: f64 = 0.3;
/// Semitones between the contour and the note's pitch.
pub const SUPPORT_TOL: f64 = 1.0;
pub const FEATURES: [&str; 10] = ["bias", "mus", "bp", "mus_bp", "log_dur", "support", "no_contour", "separated", "sep_support", "sep_voted"];
pub const CALIBRATION_JSON: &str = include_str!("calibration.json");

#[derive(Debug, Clone, PartialEq)]
pub struct Model {
    /// Weights in the file's order.
    pub weights: Vec<(String, f64)>,
    pub mark_risk: f64,
    pub very_risk: f64,
    /// Per input, the range seen in training: inputs are clamped to it.
    pub ranges: Vec<(String, f64, f64)>,
}

impl Model {
    pub fn from_json(s: &str) -> Result<Model, String> {
        let d: Value = serde_json::from_str(s).map_err(|e| e.to_string())?;
        let weights = d["weights"].as_object().ok_or("calibration without weights")?.iter().map(|(k, v)| (k.clone(), v.as_f64().unwrap_or(0.0))).collect();
        let ranges = d
            .get("ranges")
            .and_then(|r| r.as_object())
            .map(|r| r.iter().map(|(k, v)| (k.clone(), v[0].as_f64().unwrap_or(0.0), v[1].as_f64().unwrap_or(0.0))).collect())
            .unwrap_or_default();
        Ok(Model { weights, mark_risk: d["mark_risk"].as_f64().ok_or("no mark_risk")?, very_risk: d["very_risk"].as_f64().ok_or("no very_risk")?, ranges })
    }

    /// The shipped calibration.
    pub fn load() -> Model {
        Model::from_json(CALIBRATION_JSON).expect("calibration.json")
    }

    /// Confidence below which a note is marked.
    pub fn mark_below(&self) -> f64 {
        1.0 - self.mark_risk
    }

    /// Confidence below which a mark is boxed (very unsure).
    pub fn very_below(&self) -> f64 {
        1.0 - self.very_risk
    }
}

/// NumPy's float remainder (the sign of the divisor).
fn np_mod(a: f64, b: f64) -> f64 {
    let m = a % b;
    if m != 0.0 && ((b < 0.0) != (m < 0.0)) {
        m + b
    } else {
        m
    }
}

/// Mean SwiftF0 voicing confidence near `pitch` over the note's first
/// SUPPORT_WINDOW seconds (None: no contour).
pub fn support(contour: Option<&Contour>, onset: f64, pitch: i32) -> Option<f64> {
    let c = contour?;
    let t = &c.t;
    let a = t.partition_point(|&x| x < onset);
    let b = t.partition_point(|&x| x < onset + SUPPORT_WINDOW);
    if b <= a {
        return Some(0.0);
    }
    let vals: Vec<f64> = (a..b)
        .map(|i| {
            let dev = (np_mod((c.midi[i] - pitch as f64) + 6.0, 12.0) - 6.0).abs();
            let dev = if dev.is_nan() { 99.0 } else { dev };
            let conf = c.confidence.as_ref().map(|v| v[i]).unwrap_or(1.0);
            if dev <= SUPPORT_TOL {
                conf
            } else {
                0.0
            }
        })
        .collect();
    Some(py::pairwise_sum_f64(&vals) / vals.len() as f64)
}

/// Model inputs for one solo note, in FEATURES order. `separated`: the solo was
/// separated from a mix (a stem), not recorded alone.
pub fn features(sources: &BTreeSet<String>, duration: f64, sup: Option<f64>, separated: bool) -> Vec<(&'static str, f64)> {
    let mus = sources.contains("mus") as i64 as f64;
    let bp = sources.contains("bp") as i64 as f64;
    let sep = separated as i64 as f64;
    let s = sup.unwrap_or(0.0);
    vec![
        ("bias", 1.0),
        ("mus", mus),
        ("bp", bp),
        ("mus_bp", mus * bp),
        ("log_dur", (if 0.02 > duration { 0.02 } else { duration }).ln()),
        ("support", s),
        ("no_contour", if sup.is_some() { 0.0 } else { 1.0 }),
        ("separated", sep),
        ("sep_support", sep * s),
        ("sep_voted", sep * if bp > mus { bp } else { mus }),
    ]
}

pub fn p_correct(x: &[(&str, f64)], model: &Model) -> f64 {
    let mut terms = Vec::with_capacity(x.len());
    for &(k, v) in x {
        let v = match model.ranges.iter().find(|r| r.0 == k) {
            Some(&(_, lo, hi)) => {
                let m = if lo > v { lo } else { v };
                if hi < m {
                    hi
                } else {
                    m
                }
            }
            None => v,
        };
        let w = model.weights.iter().find(|w| w.0 == k).map(|w| w.1).unwrap_or(0.0);
        terms.push(w * v);
    }
    let z = py::builtin_sum(terms);
    1.0 / (1.0 + (-z).exp())
}

#[derive(Debug, Clone, PartialEq)]
pub struct ReviewGroup {
    /// Tick of the first marked note.
    pub start: i64,
    /// Tick after the last marked note.
    pub end: i64,
    /// Marked notes in the group.
    pub notes: i64,
    /// Any of them very unsure.
    pub very: bool,
}

/// Ticks (a beat) of silence between marked notes that end a phrase.
pub const PHRASE_BREAK: i64 = 24;
/// A group spans at most this many bars.
pub const MAX_GROUP_BARS: i64 = 2;

/// Group the marked notes (start, end, confidence) of one voice for review: a
/// marked note joins the previous group when at most one unmarked note lies
/// between them, no phrase break separates them, and the group stays within
/// MAX_GROUP_BARS bars.
pub fn review_groups(notes: &[(i64, i64, f64)], bar: i64, mark_below: f64, very_below: f64) -> Vec<ReviewGroup> {
    let mut notes = notes.to_vec();
    notes.sort_by(|a, b| a.0.cmp(&b.0).then(a.1.cmp(&b.1)).then(py::fcmp(&a.2, &b.2)));
    let mut groups: Vec<ReviewGroup> = Vec::new();
    let mut unmarked = 0;
    let mut phrase_break = false;
    let mut prev_end: Option<i64> = None;
    for &(s, e, c) in &notes {
        if prev_end.is_some_and(|p| s - p >= PHRASE_BREAK) {
            phrase_break = true;
        }
        if c < mark_below {
            let join = groups.last().is_some_and(|g| unmarked <= 1 && !phrase_break && py::floordiv(s, bar) - py::floordiv(g.start, bar) < MAX_GROUP_BARS);
            if join {
                let g = groups.last_mut().unwrap();
                g.end = g.end.max(e);
                g.notes += 1;
                g.very = g.very || c < very_below;
            } else {
                groups.push(ReviewGroup { start: s, end: e, notes: 1, very: c < very_below });
            }
            unmarked = 0;
            phrase_break = false;
        } else {
            unmarked += 1;
        }
        prev_end = Some(prev_end.map_or(e, |p| p.max(e)));
    }
    groups
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shipped_calibration_matches_the_reference_file() {
        let p = std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../music/src/brasscribe_music/calibration.json");
        if let Ok(s) = std::fs::read_to_string(p) {
            assert_eq!(s, CALIBRATION_JSON, "core/scribe-core/src/calibration.json is out of date");
        }
        let m = Model::load();
        assert_eq!((m.mark_risk, m.very_risk), (0.241, 0.6));
    }

    #[test]
    fn groups_join_neighbours_and_break_on_silence() {
        let n = |s: i64, c: f64| (s, s + 6, c);
        let g = review_groups(&[n(0, 0.5), n(6, 0.9), n(12, 0.3), n(60, 0.5)], 96, 0.759, 0.4);
        assert_eq!(g, vec![ReviewGroup { start: 0, end: 18, notes: 2, very: true }, ReviewGroup { start: 60, end: 66, notes: 1, very: false }]);
    }
}
