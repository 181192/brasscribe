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
}

fn one() -> f64 {
    1.0
}

impl Note {
    pub fn new(pitch: i32, start: i64, dur: i64, confidence: f64, sources: Vec<String>) -> Self {
        Note { pitch, start, dur, confidence, sources, onset_s: None, offset_s: None, performed_dur: None, articulations: Vec::new() }
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
        diffs.sort_by(|a, b| a.partial_cmp(b).unwrap());
        60.0 / diffs[diffs.len() / 2]
    }

    pub fn to_value(&self) -> Value {
        serde_json::to_value(self).expect("composition serialises")
    }

    /// The exact text of `Composition.to_json` in the reference.
    pub fn to_json_string(&self) -> String {
        crate::pyjson::dumps(&self.to_value())
    }

    pub fn from_json_str(s: &str) -> Result<Self, serde_json::Error> {
        serde_json::from_str(s)
    }
}
