//! Canonical symbolic score: the boundary between transcription and arrangement.
//!
//! Everything is at concert pitch in integer ticks (`TICKS_PER_BEAT` per beat);
//! seconds are kept alongside so the score can be aligned back to the
//! recording. The JSON form is the `composition.json` written by the Python
//! reference (`brasscribe_music.score_model`), field for field and in the
//! same order.

use serde::{Deserialize, Serialize};
use serde_json::Value;

pub const TICKS_PER_BEAT: i64 = 24;

/// The longest piece the core reads or arranges, in beats: 5,000 bars of 4/4, nearly three hours
/// at 120 BPM. Every tick of a Composition (notes, meters, keys, marks) lies within this many beats
/// of tick 0, so what is written grows with the music and never without bound.
pub const MAX_BEATS: i64 = 20_000;
/// [`MAX_BEATS`] in ticks.
pub const MAX_TICKS: i64 = MAX_BEATS * TICKS_PER_BEAT;
/// The most beats a bar of a meter can have.
pub const MAX_BAR_BEATS: i64 = 32;

/// Err unless [start, end) ticks lie within [`MAX_TICKS`] of tick 0.
pub fn check_span(start: i64, end: i64) -> Result<(), String> {
    if start < -MAX_TICKS || end > MAX_TICKS {
        return Err(format!("the music is longer than the {MAX_BEATS} beats Brasscribe arranges"));
    }
    Ok(())
}

/// The largest transposition, in semitones either way: four octaves.
pub const MAX_TRANSPOSE: i32 = 48;

/// `semitones` as a transposition, or Err beyond [`MAX_TRANSPOSE`].
pub fn check_transpose(semitones: i64) -> Result<i32, String> {
    match i32::try_from(semitones) {
        Ok(t) if t.abs() <= MAX_TRANSPOSE => Ok(t),
        _ => Err(format!("a transposition is at most {MAX_TRANSPOSE} semitones either way, not {semitones}")),
    }
}

/// Err unless a bar of `beats` beats can be written (1 to [`MAX_BAR_BEATS`]).
pub fn check_bar_beats(beats: i64) -> Result<(), String> {
    if !(1..=MAX_BAR_BEATS).contains(&beats) {
        return Err(format!("a bar has 1 to {MAX_BAR_BEATS} beats, not {beats}"));
    }
    Ok(())
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash, Serialize, Deserialize)]
#[serde(rename_all = "lowercase")]
pub enum VoiceRole {
    Melody,
    Countermelody,
    Harmony,
    Bass,
    Rhythm,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Note {
    /// Concert MIDI pitch.
    pub pitch: i32,
    /// Ticks from the first downbeat (may be negative in a pickup).
    pub start: i64,
    /// Notated duration in ticks.
    pub dur: i64,
    #[serde(default = "one")]
    pub confidence: f64,
    #[serde(default)]
    pub sources: Vec<String>,
    #[serde(default)]
    pub onset_s: Option<f64>,
    #[serde(default)]
    pub offset_s: Option<f64>,
    /// Performed length in ticks (offset - onset on the tick map); None = unknown.
    #[serde(default)]
    pub performed_dur: Option<i64>,
    /// "staccato" (performed under half the written length) or "fermata".
    #[serde(default)]
    pub articulations: Vec<String>,
    /// A trill mark: semitones up to the auxiliary (1 or 2; trills.rs). Not written when None.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub trill: Option<i32>,
}

fn one() -> f64 {
    1.0
}

impl Note {
    pub fn new(pitch: i32, start: i64, dur: i64, confidence: f64, sources: Vec<String>) -> Self {
        Note { pitch, start, dur, confidence, sources, onset_s: None, offset_s: None, performed_dur: None, articulations: Vec::new(), trill: None }
    }

    pub fn with_times(mut self, onset_s: Option<f64>, offset_s: Option<f64>) -> Self {
        self.onset_s = onset_s;
        self.offset_s = offset_s;
        self
    }

    #[inline]
    pub fn end(&self) -> i64 {
        self.start + self.dur
    }
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Voice {
    pub id: String,
    pub role: VoiceRole,
    #[serde(default)]
    pub notes: Vec<Note>,
    /// What the source instrument seemed to be; never binding.
    #[serde(default)]
    pub instrument_hint: Option<String>,
    /// Textural layer it came from: solo, strings, brass, keys, bass, drums.
    #[serde(default)]
    pub layer: Option<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Meter {
    pub tick: i64,
    pub beats: i64,
    #[serde(default = "four")]
    pub beat_unit: i64,
}

fn four() -> i64 {
    4
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct KeySig {
    pub tick: i64,
    pub fifths: i32,
    #[serde(default = "major")]
    pub mode: String,
}

fn major() -> String {
    "major".into()
}

/// A passage played in free time (ad lib): notated proportionally or at a fixed tempo.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct FreeRegion {
    pub start: i64,
    pub end: i64,
    pub start_s: f64,
    pub end_s: f64,
    pub tempo_bpm: f64,
    /// "proportional" (local tempo from the notes) | "tempo" (a tempo the user gave)
    #[serde(default = "proportional")]
    pub notation: String,
    #[serde(default = "ad_lib")]
    pub label: String,
}

fn proportional() -> String {
    "proportional".into()
}

fn ad_lib() -> String {
    "ad lib.".into()
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Composition {
    pub title: String,
    pub voices: Vec<Voice>,
    pub meters: Vec<Meter>,
    pub keys: Vec<KeySig>,
    /// Seconds of beat 0, 1, 2 ... (tempo map).
    #[serde(default)]
    pub beat_times: Vec<f64>,
    /// Index into beat_times of tick 0.
    #[serde(default)]
    pub first_downbeat: i64,
    #[serde(default = "tpb")]
    pub ticks_per_beat: i64,
    #[serde(default)]
    pub free_regions: Vec<FreeRegion>,
    /// Dynamic markings per textural layer.
    #[serde(default)]
    pub dynamics: Vec<Dynamic>,
    /// Rehearsal marks at bar lines.
    #[serde(default)]
    pub sections: Vec<Section>,
    /// Neighbouring uncertain notes of one voice, reviewed together (one "?" in the score).
    #[serde(default, skip_serializing_if = "Vec::is_empty")]
    pub review: Vec<ReviewItem>,
    /// Options the arrangement was made with (lineup, difficulty,
    /// transpose_semitones); absent = the defaults.
    #[serde(default, skip_serializing_if = "Option::is_none")]
    pub arrangement: Option<Value>,
    /// The beat grid is a guess from the onsets (the tracker found under two beats).
    #[serde(default, skip_serializing_if = "is_false")]
    pub tempo_estimated: bool,
}

fn is_false(b: &bool) -> bool {
    !*b
}

/// A dynamic marking (pp, p, mp, mf, f, ff) for one textural layer from `tick` on.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Dynamic {
    pub tick: i64,
    pub layer: String,
    pub mark: String,
}

/// A rehearsal mark: section `label` (A, B, ...) starts at `tick` (a bar line).
/// [start, end) ticks of marked notes of one voice; `notes` marked notes in
/// it; `very` when any is very unsure.
#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReviewItem {
    pub voice: String,
    pub start: i64,
    pub end: i64,
    pub notes: i64,
    #[serde(default)]
    pub very: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct Section {
    pub tick: i64,
    pub label: String,
}

fn tpb() -> i64 {
    TICKS_PER_BEAT
}

impl Composition {
    pub fn voices_with(&self, role: VoiceRole) -> impl Iterator<Item = &Voice> {
        self.voices.iter().filter(move |v| v.role == role)
    }

    pub fn end_tick(&self) -> i64 {
        self.voices.iter().flat_map(|v| v.notes.iter().map(|n| n.end())).max().unwrap_or(0)
    }

    pub fn free_region_at(&self, tick: i64) -> Option<&FreeRegion> {
        self.free_regions.iter().find(|r| r.start <= tick && tick < r.end)
    }

    /// Tempo of the strict (gridded) passages, from the upper-middle beat interval.
    pub fn bpm(&self) -> f64 {
        if self.beat_times.len() < 2 {
            return 120.0;
        }
        let tpb = self.ticks_per_beat;
        let mut diffs: Vec<f64> = self
            .beat_times
            .windows(2)
            .enumerate()
            .filter(|(i, _)| self.free_region_at((*i as i64 - self.first_downbeat) * tpb).is_none())
            .map(|(_, w)| w[1] - w[0])
            .collect();
        if diffs.is_empty() {
            diffs = self.beat_times.windows(2).map(|w| w[1] - w[0]).collect();
        }
        diffs.sort_by(crate::py::fcmp);
        60.0 / diffs[diffs.len() / 2]
    }

    /// The whole piece `semitones` higher at concert pitch (drums and tick positions unchanged).
    /// Err when a note would leave MIDI 0-127.
    pub fn transposed(&self, semitones: i32) -> Result<Composition, String> {
        let mut c = self.clone();
        for v in c.voices.iter_mut() {
            if v.layer.as_deref() == Some("drums") || v.role == VoiceRole::Rhythm {
                continue;
            }
            for n in v.notes.iter_mut() {
                n.pitch = n.pitch.saturating_add(semitones);
                if !(0..=127).contains(&n.pitch) {
                    return Err(format!("transposed by {semitones} semitones, a note of {} is outside MIDI 0-127", v.id));
                }
            }
        }
        c.keys = c.keys.iter().map(|k| crate::keys::transposed_key(k, semitones)).collect();
        Ok(c)
    }

    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).expect("composition serialises")
    }

    /// The exact text of `Composition.to_json` in the reference.
    pub fn to_json_string(&self) -> String {
        crate::pyjson::dumps(&self.to_value())
    }

    /// Parse composition.json and [`validate`](Self::validate) it.
    pub fn from_json_str(s: &str) -> Result<Self, serde_json::Error> {
        let c: Composition = serde_json::from_str(s)?;
        c.validate().map_err(<serde_json::Error as serde::de::Error>::custom)?;
        Ok(c)
    }

    /// Err when the Composition cannot be arranged: a meter outside 1 to [`MAX_BAR_BEATS`] beats
    /// or with a beat unit that is not a note value, a note with a negative length or a pitch
    /// outside MIDI 0-127, beat times that are not numbers or go backwards, or anything further
    /// than [`MAX_BEATS`] from tick 0.
    pub fn validate(&self) -> Result<(), String> {
        let tick = |what: &str, t: i64| check_span(t, t).map_err(|e| format!("{what} at tick {t}: {e}"));
        if self.ticks_per_beat < 1 {
            return Err(format!("ticks_per_beat must be positive, not {}", self.ticks_per_beat));
        }
        for m in &self.meters {
            check_bar_beats(m.beats).map_err(|e| format!("meter at tick {}: {e}", m.tick))?;
            if !(1..=64).contains(&m.beat_unit) || m.beat_unit & (m.beat_unit - 1) != 0 {
                return Err(format!("meter at tick {}: beat unit {} is not a note value", m.tick, m.beat_unit));
            }
            tick("meter", m.tick)?;
        }
        for v in &self.voices {
            for n in &v.notes {
                if !(0..=127).contains(&n.pitch) {
                    return Err(format!("voice {}: pitch {} is outside MIDI 0-127", v.id, n.pitch));
                }
                if !(0..=MAX_TICKS).contains(&n.dur) {
                    return Err(format!("voice {}: note at tick {} has length {}", v.id, n.start, n.dur));
                }
                check_span(n.start, n.start.saturating_add(n.dur)).map_err(|e| format!("voice {}: note at tick {}: {e}", v.id, n.start))?;
            }
        }
        if self.beat_times.iter().any(|t| !t.is_finite()) || self.beat_times.windows(2).any(|w| w[1] < w[0]) {
            return Err("beat_times must be numbers in order".into());
        }
        if !(-MAX_BEATS..=MAX_BEATS).contains(&self.first_downbeat) {
            return Err(format!("first_downbeat {} is further than {MAX_BEATS} beats from the start", self.first_downbeat));
        }
        for k in &self.keys {
            tick("key", k.tick)?;
        }
        for r in &self.free_regions {
            tick("free region", r.start)?;
            tick("free region", r.end)?;
        }
        for d in &self.dynamics {
            tick("dynamic", d.tick)?;
        }
        for x in &self.sections {
            tick("rehearsal mark", x.tick)?;
        }
        for r in &self.review {
            tick("review mark", r.start)?;
            tick("review mark", r.end)?;
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn comp(edit: impl FnOnce(&mut Value)) -> Result<Composition, serde_json::Error> {
        let mut v = serde_json::json!({
            "title": "t",
            "voices": [{"id": "melody", "role": "melody", "notes": [{"pitch": 60, "start": 0, "dur": 24}]}],
            "meters": [{"tick": 0, "beats": 4}],
            "keys": [{"tick": 0, "fifths": 0}],
            "beat_times": [0.0, 0.5, 1.0],
        });
        edit(&mut v);
        Composition::from_json_str(&v.to_string())
    }

    #[test]
    fn reads_a_plain_composition() {
        assert!(comp(|_| {}).is_ok());
        assert!(comp(|v| v["meters"][0]["beats"] = 32.into()).is_ok());
        assert!(comp(|v| v["voices"][0]["notes"][0]["dur"] = 0.into()).is_ok());
        assert!(comp(|v| v["voices"][0]["notes"][0]["start"] = (MAX_TICKS - 24).into()).is_ok());
    }

    #[test]
    fn refuses_meters_that_cannot_be_written() {
        for beats in [0, -3, 33, 100_000, 1_000_000] {
            let e = comp(|v| v["meters"][0]["beats"] = beats.into()).unwrap_err().to_string();
            assert!(e.contains("a bar has 1 to 32 beats"), "{beats}: {e}");
        }
        for unit in [0, 3, -4, 128] {
            assert!(comp(|v| v["meters"][0]["beat_unit"] = unit.into()).unwrap_err().to_string().contains("beat unit"), "{unit}");
        }
    }

    #[test]
    fn refuses_notes_that_cannot_be_written() {
        assert!(comp(|v| v["voices"][0]["notes"][0]["dur"] = (-12).into()).unwrap_err().to_string().contains("length -12"));
        for p in [-1, 128, i32::MAX] {
            assert!(comp(|v| v["voices"][0]["notes"][0]["pitch"] = p.into()).unwrap_err().to_string().contains("outside MIDI"), "{p}");
        }
        for (start, dur) in [(0, 200_000_000), (0, 1_000_000_000), (MAX_TICKS, 24), (-MAX_TICKS - 1, 24), (i64::MAX, 24), (i64::MIN, 24)] {
            let e = comp(|v| {
                v["voices"][0]["notes"][0]["start"] = start.into();
                v["voices"][0]["notes"][0]["dur"] = dur.into();
            })
            .unwrap_err()
            .to_string();
            assert!(e.contains("length") || e.contains("longer"), "{start} {dur}: {e}");
        }
    }

    #[test]
    fn refuses_other_marks_far_from_the_music() {
        let far = MAX_TICKS + 1;
        assert!(comp(|v| v["meters"][0]["tick"] = far.into()).is_err());
        assert!(comp(|v| v["keys"][0]["tick"] = far.into()).is_err());
        assert!(comp(|v| v["sections"] = serde_json::json!([{"tick": far, "label": "A"}])).is_err());
        assert!(comp(|v| v["dynamics"] = serde_json::json!([{"tick": -far, "layer": "solo", "mark": "f"}])).is_err());
        assert!(comp(|v| v["review"] = serde_json::json!([{"voice": "melody", "start": 0, "end": far, "notes": 1}])).is_err());
        assert!(comp(|v| v["free_regions"] = serde_json::json!([{"start": 0, "end": far, "start_s": 0.0, "end_s": 1.0, "tempo_bpm": 60.0}])).is_err());
        assert!(comp(|v| v["first_downbeat"] = i64::MIN.into()).is_err());
        assert!(comp(|v| v["ticks_per_beat"] = 0.into()).is_err());
    }

    #[test]
    fn refuses_beat_times_that_go_back() {
        assert!(comp(|v| v["beat_times"] = serde_json::json!([0.0, 0.0, 1.0])).is_ok());
        assert!(comp(|v| v["beat_times"] = serde_json::json!([0.0, 1.0, 0.5])).unwrap_err().to_string().contains("beat_times"));
    }
}
