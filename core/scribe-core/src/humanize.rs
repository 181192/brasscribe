//! Deterministic humanization of score notes for playback (sounds/README.md, "Humanization").
//!
//! Timing and dynamics come from the Composition's performed fields where they
//! exist (onset_s against the performed beat map, performed_dur, articulations,
//! velocity), and from small seeded jitter otherwise. Every random value comes
//! from a keyed hash, so the result does not depend on evaluation order.
//!
//! Part-note pitches are concert MIDI numbers: voice matching compares pitch
//! classes with the Composition.

use serde_json::{json, Map, Value};
use std::collections::HashMap;

use crate::py::py_round;

pub const TPB: i64 = 24;
pub const MAX_DEV_S: f64 = 0.040;
pub const MIN_CONFIDENCE: f64 = 0.5;
pub const MATCH_RATE: f64 = 0.5;
pub const DETUNE_CENTS: [f64; 4] = [0.0, 4.0, -5.0, 3.0];

pub fn fnv1a64(data: &[u8]) -> u64 {
    let mut h: u64 = 0xCBF29CE484222325;
    for &b in data {
        h = (h ^ b as u64).wrapping_mul(0x100000001B3);
    }
    h
}

pub fn splitmix64(x: u64) -> u64 {
    let mut x = x.wrapping_add(0x9E3779B97F4A7C15);
    x = (x ^ (x >> 30)).wrapping_mul(0xBF58476D1CE4E5B9);
    x = (x ^ (x >> 27)).wrapping_mul(0x94D049BB133111EB);
    x ^ (x >> 31)
}

/// [0, 1) from the key.
pub fn uniform(key: &str) -> f64 {
    (splitmix64(fnv1a64(key.as_bytes())) >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
}

/// Triangular on (-1, 1).
pub fn tri(key: &str) -> f64 {
    uniform(&format!("{key}#a")) + uniform(&format!("{key}#b")) - 1.0
}

fn clip(x: f64, lim: f64) -> f64 {
    // max(-lim, min(lim, x)) with Python's argument order
    let m = if x < lim { x } else { lim };
    if m > -lim {
        m
    } else {
        -lim
    }
}

/// One part note: score position in Composition ticks plus its score-tempo seconds.
#[derive(Debug, Clone, PartialEq, serde::Serialize, serde::Deserialize)]
pub struct ScoreNote {
    pub tick: i64,
    pub dur_tick: i64,
    pub start_s: f64,
    pub end_s: f64,
    /// Concert MIDI pitch.
    pub pitch: i32,
    pub velocity: i64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct PlayedNote {
    pub start: f64,
    pub end: f64,
    pub pitch: i32,
    pub velocity: i64,
    pub staccato: bool,
    pub from_composition: bool,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum Timing {
    Score,
    Performed,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Stats {
    pub voice: Option<String>,
    pub own_timing: usize,
    pub ensemble_timing: usize,
    pub jitter_only: usize,
    pub lag_ms: f64,
    pub detune_cents: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct Humanized {
    pub notes: Vec<PlayedNote>,
    pub detune: f64,
    pub stats: Stats,
}

/// A Composition note as the humanizer reads it (JSON fields, absent = None).
#[derive(Debug, Clone)]
struct PerfNote {
    start: i64,
    onset_s: Option<f64>,
    confidence: f64,
    performed_dur: Option<f64>,
    dur: Option<f64>,
    velocity: Option<f64>,
    staccato: bool,
}

/// What the Composition says about how the music was played.
#[derive(Debug, Clone, Default)]
pub struct Performance {
    beat_times: Vec<f64>,
    first_downbeat: i64,
    tick_dev: HashMap<i64, f64>,
    /// Voices in file order: id -> (start, pitch class) -> first note.
    voices: Vec<(String, HashMap<(i64, i64), PerfNote>)>,
    roles: HashMap<String, String>,
}

fn num(v: Option<&Value>) -> Option<f64> {
    v.and_then(|x| x.as_f64())
}

/// Python truthiness of a number field: absent, null and 0 are false.
fn truthy(v: Option<f64>) -> Option<f64> {
    v.filter(|x| *x != 0.0)
}

impl Performance {
    /// From Composition JSON text.
    pub fn from_json_str(s: &str) -> Result<Performance, String> {
        let d: Value = serde_json::from_str(s).map_err(|e| e.to_string())?;
        Performance::from_value(&d)
    }

    pub fn from_value(d: &Value) -> Result<Performance, String> {
        let mut perf = Performance {
            beat_times: d.get("beat_times").and_then(|v| v.as_array()).map(|a| a.iter().filter_map(|x| x.as_f64()).collect()).unwrap_or_default(),
            first_downbeat: d.get("first_downbeat").and_then(|v| v.as_i64()).unwrap_or(0),
            ..Default::default()
        };
        let mut devs: Vec<(i64, Vec<f64>)> = Vec::new();
        let mut dev_idx: HashMap<i64, usize> = HashMap::new();
        for v in d.get("voices").and_then(|v| v.as_array()).map(|a| a.as_slice()).unwrap_or(&[]) {
            let id = v.get("id").and_then(|x| x.as_str()).ok_or("voice without id")?.to_string();
            perf.roles.insert(id.clone(), v.get("role").and_then(|x| x.as_str()).unwrap_or("").to_string());
            let vi = match perf.voices.iter().position(|(k, _)| *k == id) {
                Some(i) => i,
                None => {
                    perf.voices.push((id.clone(), HashMap::new()));
                    perf.voices.len() - 1
                }
            };
            for n in v.get("notes").and_then(|x| x.as_array()).map(|a| a.as_slice()).unwrap_or(&[]) {
                let start = n.get("start").and_then(|x| x.as_i64()).ok_or("note without start")?;
                let pitch = n.get("pitch").and_then(|x| x.as_i64()).ok_or("note without pitch")?;
                let pn = PerfNote {
                    start,
                    onset_s: num(n.get("onset_s")),
                    confidence: num(n.get("confidence")).unwrap_or(1.0),
                    performed_dur: truthy(num(n.get("performed_dur"))),
                    dur: truthy(num(n.get("dur"))),
                    velocity: truthy(num(n.get("velocity"))),
                    staccato: n
                        .get("articulations")
                        .and_then(|a| a.as_array())
                        .map(|a| a.iter().any(|x| x.as_str() == Some("staccato")))
                        .unwrap_or(false),
                };
                // A deviation that is not a number (beat times at the ends of the float range) says nothing.
                if let Some(dev) = perf.deviation(&pn).filter(|d| d.is_finite()) {
                    let i = *dev_idx.entry(start).or_insert_with(|| {
                        devs.push((start, Vec::new()));
                        devs.len() - 1
                    });
                    devs[i].1.push(dev);
                }
                perf.voices[vi].1.entry((start, pitch.rem_euclid(12))).or_insert(pn);
            }
        }
        for (t, mut v) in devs {
            v.sort_by(crate::py::fcmp);
            let n = v.len();
            let med = if n % 2 == 1 { v[n / 2] } else { (v[n / 2 - 1] + v[n / 2]) / 2.0 };
            perf.tick_dev.insert(t, clip(med, MAX_DEV_S));
        }
        Ok(perf)
    }

    /// B(b): performed time of beat index b, piecewise linear, extrapolated with the end intervals.
    pub fn beat_seconds(&self, beat: f64) -> f64 {
        let bt = &self.beat_times;
        if beat <= 0.0 {
            return bt[0] + beat * (bt[1] - bt[0]);
        }
        let last = bt.len() - 1;
        if beat >= last as f64 {
            return bt[last] + (beat - last as f64) * (bt[last] - bt[last - 1]);
        }
        let i = beat as usize;
        bt[i] + (beat - i as f64) * (bt[i + 1] - bt[i])
    }

    pub fn tick_seconds(&self, tick: i64) -> f64 {
        self.beat_seconds(tick as f64 / TPB as f64 + self.first_downbeat as f64)
    }

    fn deviation(&self, n: &PerfNote) -> Option<f64> {
        let onset = n.onset_s?;
        if n.confidence < MIN_CONFIDENCE || self.beat_times.len() < 2 {
            return None;
        }
        Some(onset - self.tick_seconds(n.start))
    }

    fn match_voice(&self, notes: &[ScoreNote]) -> Option<usize> {
        let (mut best, mut best_rate) = (None, 0.0);
        for (i, (_, table)) in self.voices.iter().enumerate() {
            let hits = notes.iter().filter(|n| table.contains_key(&(n.tick, (n.pitch as i64).rem_euclid(12)))).count();
            let rate = hits as f64 / notes.len().max(1) as f64;
            if rate > best_rate {
                best = Some(i);
                best_rate = rate;
            }
        }
        if best_rate >= MATCH_RATE {
            best
        } else {
            None
        }
    }
}

/// Played notes, the detune in cents for the whole player, and stats.
pub fn humanize(notes: &[ScoreNote], part: &str, player: i64, seed: &str, perf: Option<&Performance>, timing: Timing) -> Result<Humanized, String> {
    if timing == Timing::Performed && perf.is_none() {
        return Err("performed timing needs a Composition".into());
    }
    if let Some(p) = perf {
        if timing == Timing::Performed && p.beat_times.len() < 2 {
            return Err("Composition has fewer than two beat_times".into());
        }
    }
    let mut notes = notes.to_vec();
    notes.sort_by_key(|n| (n.tick, n.pitch));
    let pkey = format!("{seed}|{part}|{player}|-|");
    let lag = 0.002 + 0.008 * tri(&format!("{pkey}lag"));
    let detune = DETUNE_CENTS[player.rem_euclid(4) as usize] + 1.5 * tri(&format!("{pkey}detune"));
    let voice = perf.and_then(|p| p.match_voice(&notes));
    let empty = HashMap::new();
    let table = match (perf, voice) {
        (Some(p), Some(v)) => &p.voices[v].1,
        _ => &empty,
    };
    let voice_id = match (perf, voice) {
        (Some(p), Some(v)) => Some(p.voices[v].0.clone()),
        _ => None,
    };
    let own_timing = voice_id.as_ref().is_some_and(|v| perf.unwrap().roles.get(v).map(|r| r == "melody").unwrap_or(false));
    let (mut out, mut n_own, mut n_tick) = (Vec::with_capacity(notes.len()), 0usize, 0usize);
    for (i, n) in notes.iter().enumerate() {
        let key = format!("{seed}|{part}|{player}|{i}|");
        let m = table.get(&(n.tick, (n.pitch as i64).rem_euclid(12)));
        let own = match (perf, m) {
            (Some(p), Some(m)) if own_timing => p.deviation(m),
            _ => None,
        };
        let (e, from_comp) = if let Some(own) = own {
            n_own += 1;
            (clip(own, MAX_DEV_S), true)
        } else if let Some(d) = perf.and_then(|p| p.tick_dev.get(&n.tick)) {
            n_tick += 1;
            (*d, true)
        } else {
            (0.0, false)
        };
        let sigma = if from_comp { 0.004 } else { 0.010 };
        let (base, span) = match timing {
            Timing::Performed => {
                let p = perf.unwrap();
                let b = p.tick_seconds(n.tick);
                (b, p.tick_seconds(n.tick + n.dur_tick) - b)
            }
            Timing::Score => (n.start_s, n.end_s - n.start_s),
        };
        let mut f = 1.0;
        if let Some(m) = m {
            if let (Some(pd), Some(d)) = (m.performed_dur, m.dur) {
                let r = pd / d;
                let lo = if r < 1.0 { r } else { 1.0 };
                f = if lo > 0.3 { lo } else { 0.3 };
            }
        }
        let x = base + e + lag + sigma * tri(&format!("{key}onset"));
        let onset = if x > 0.0 { x } else { 0.0 };
        let sf = span * f;
        let end = onset + if sf > 0.03 { sf } else { 0.03 };
        let v0 = m.and_then(|m| m.velocity).unwrap_or(n.velocity as f64);
        let vel = (v0 + 5.0 * tri(&format!("{key}vel"))).round_ties_even() as i64;
        let vel = vel.clamp(1, 127);
        let stac = m.is_some_and(|m| m.staccato);
        out.push(PlayedNote { start: onset, end, pitch: n.pitch, velocity: vel, staccato: stac, from_composition: from_comp });
    }
    let total = notes.len();
    Ok(Humanized {
        notes: out,
        detune,
        stats: Stats {
            voice: voice_id,
            own_timing: n_own,
            ensemble_timing: n_tick,
            jitter_only: total - n_own - n_tick,
            lag_ms: py_round(lag * 1000.0, 2),
            detune_cents: py_round(detune, 2),
        },
    })
}

impl Humanized {
    pub fn to_value(&self) -> Value {
        let notes: Vec<Value> = self
            .notes
            .iter()
            .map(|n| {
                let mut m = Map::new();
                m.insert("start".into(), json!(n.start));
                m.insert("end".into(), json!(n.end));
                m.insert("pitch".into(), json!(n.pitch));
                m.insert("velocity".into(), json!(n.velocity));
                m.insert("staccato".into(), json!(n.staccato));
                m.insert("from_composition".into(), json!(n.from_composition));
                Value::Object(m)
            })
            .collect();
        let s = &self.stats;
        let mut st = Map::new();
        st.insert("voice".into(), s.voice.clone().map(Value::String).unwrap_or(Value::Null));
        st.insert("own_timing".into(), json!(s.own_timing));
        st.insert("ensemble_timing".into(), json!(s.ensemble_timing));
        st.insert("jitter_only".into(), json!(s.jitter_only));
        st.insert("lag_ms".into(), json!(s.lag_ms));
        st.insert("detune_cents".into(), json!(s.detune_cents));
        json!({"notes": notes, "detune": self.detune, "stats": Value::Object(st)})
    }

    pub fn to_json_string(&self) -> String {
        crate::pyjson::dumps_compact(&self.to_value())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prng_vectors() {
        assert_eq!(fnv1a64(b""), 0xcbf29ce484222325);
        assert_eq!(uniform(""), 0.7636945250957473);
        assert_eq!(uniform("a"), 0.3717309634354091);
        let k = "brasscribe|Solo Cornet|0|-|lag";
        assert_eq!(fnv1a64(k.as_bytes()), 0xee216da0d3be2b6a);
        assert_eq!(splitmix64(0xee216da0d3be2b6a), 0xc0c340d7787c06ac);
        assert_eq!(tri(k), -0.7633896560002583);
    }

    #[test]
    fn deviations_that_are_not_numbers_are_left_out() {
        // Beat times at the ends of the float range: the beat length overflows, the deviations are NaN.
        let note = |start: i64, onset: f64| serde_json::json!({"start": start, "pitch": 60, "dur": 24, "onset_s": onset});
        let comp = serde_json::json!({
            "beat_times": [-1e308, 1e308],
            "voices": [{"id": "melody", "role": "melody", "notes": [note(0, 0.1), note(0, 0.2), note(0, 0.3)]}],
        });
        let p = Performance::from_value(&comp).unwrap();
        assert!(p.tick_dev.is_empty());
        let n = ScoreNote { tick: 0, dur_tick: 24, start_s: 0.0, end_s: 0.5, pitch: 60, velocity: 80 };
        assert!(humanize(&[n], "Solo Cornet", 0, "brasscribe", Some(&p), Timing::Score).is_ok());
    }
}
