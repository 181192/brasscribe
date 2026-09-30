//! Written durations and staccato from performed note lengths.
//!
//! 1. Where a note really ends: [`contour_offsets`] follows a frame-level
//!    SwiftF0 contour (the note lasts while the contour stays on its pitch and
//!    loud enough, up to the next onset).
//! 2. What to write: per voice, a note is *held* (written until the next onset)
//!    when it was played for at least `LEGATO_RATIO` of the time to the next
//!    onset and the silence before that onset is at most `MAX_HELD_GAP`;
//!    otherwise it is written as the readable value nearest its performed
//!    length. A note performed under half its written length gets a staccato mark.

use crate::model::TICKS_PER_BEAT;
use crate::quantize::{BeatMap, QNote};

pub const LEGATO_RATIO: f64 = 0.5;
/// Ticks (a dotted 8th): a longer silence is written as a rest.
pub const MAX_HELD_GAP: f64 = 18.0;
pub const STACCATO_RATIO: f64 = 0.5;
/// Readable written lengths in ticks (24 per beat).
pub const READABLE: [i64; 10] = [6, 8, 12, 16, 18, 24, 36, 48, 72, 96];
/// SwiftF0 frame period (s).
pub const FRAME: f64 = 0.016;

/// `contour_offsets` settings for a separated stem.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct ContourSettings {
    pub tol: f64,
    pub drop_db: f64,
    pub floor_db: f64,
    pub max_hole: f64,
    pub attack: f64,
}

impl Default for ContourSettings {
    fn default() -> Self {
        ContourSettings { tol: 0.6, drop_db: 60.0, floor_db: -100.0, max_hole: 0.1, attack: 0.12 }
    }
}

/// Mega-53's solo stem keeps a sustained tone's pitch but pushes its level far
/// under the attack, so the default level gate cuts such notes short.
pub const SEPARATED_STEM: ContourSettings = ContourSettings { tol: 0.6, drop_db: 80.0, floor_db: -115.0, max_hole: 0.25, attack: 0.12 };

/// Frame-level monophonic pitch track (SwiftF0 output).
#[derive(Debug, Clone, PartialEq)]
pub struct Contour {
    pub t: Vec<f64>,
    /// Fractional MIDI pitch; NaN where no pitch.
    pub midi: Vec<f64>,
    pub loudness_db: Vec<f64>,
    /// SwiftF0 voicing confidence per frame, when the contour has it.
    pub confidence: Option<Vec<f64>>,
}

impl Contour {
    /// From per-frame time, pitch in Hz (<= 0 means unvoiced) and loudness.
    pub fn from_hz(t: Vec<f64>, pitch_hz: &[f64], loudness_db: Vec<f64>) -> Contour {
        let midi = pitch_hz.iter().map(|&hz| if hz > 0.0 { 69.0 + 12.0 * (hz / 440.0).log2() } else { f64::NAN }).collect();
        Contour { t, midi, loudness_db, confidence: None }
    }

    pub fn with_confidence(mut self, confidence: Option<Vec<f64>>) -> Contour {
        self.confidence = confidence;
        self
    }

    /// Err unless every array has one value per frame (one time each).
    pub fn check(&self) -> Result<(), String> {
        let n = self.t.len();
        let mut lens = vec![("pitch", self.midi.len()), ("loudness", self.loudness_db.len())];
        if let Some(c) = &self.confidence {
            lens.push(("confidence", c.len()));
        }
        match lens.into_iter().find(|&(_, l)| l != n) {
            Some((what, l)) => Err(format!("the contour has {n} times but {l} {what} values")),
            None => Ok(()),
        }
    }
}

fn searchsorted_left(a: &[f64], v: f64) -> usize {
    a.partition_point(|&x| x < v)
}

/// End time of each (onset_s, pitch) note of one voice, sorted by onset.
pub fn contour_offsets(c: &Contour, notes: &[(f64, i32)], s: ContourSettings) -> Vec<f64> {
    let mut out = Vec::with_capacity(notes.len());
    for (i, &(on, p)) in notes.iter().enumerate() {
        let limit = if i + 1 < notes.len() {
            notes[i + 1].0
        } else if !c.t.is_empty() {
            c.t[c.t.len() - 1] + FRAME
        } else {
            on
        };
        let a = searchsorted_left(&c.t, on - FRAME / 2.0);
        let b = searchsorted_left(&c.t, limit - FRAME / 2.0);
        if b <= a {
            out.push(on + FRAME);
            continue;
        }
        let m = &c.midi[a..b];
        let db = &c.loudness_db[a..b];
        let near: Vec<bool> = m
            .iter()
            .map(|&x| {
                let dev = (((x - p as f64) + 6.0).rem_euclid(12.0) - 6.0).abs();
                let dev = if dev.is_nan() { 99.0 } else { dev };
                dev <= s.tol
            })
            .collect();
        let head: Vec<bool> = (0..m.len()).map(|k| near[k] && c.t[a + k] < on + s.attack).collect();
        let peak = if head.iter().any(|&h| h) {
            db.iter().zip(head.iter()).filter(|(_, &h)| h).map(|(&d, _)| d).fold(f64::NEG_INFINITY, f64::max)
        } else {
            let k = ((s.attack / FRAME) as usize).max(1).min(db.len());
            db[..k].iter().cloned().fold(f64::NEG_INFINITY, f64::max)
        };
        let gate = s.floor_db.max(peak - s.drop_db);
        let mut end = on + FRAME;
        let mut hole = 0.0;
        for k in 0..m.len() {
            if near[k] && db[k] >= gate {
                end = c.t[a + k] + FRAME;
                hole = 0.0;
            } else {
                hole += FRAME;
                if hole > s.max_hole && end > on + FRAME {
                    break;
                }
                if hole > s.max_hole + s.attack {
                    break;
                }
            }
        }
        out.push(if limit < end { limit } else { end });
    }
    out
}

#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Written {
    /// Written length in ticks.
    pub dur: i64,
    /// Performed length in ticks (unsnapped).
    pub performed: f64,
    pub staccato: bool,
}

/// Log-length units: prefer a slightly off length to a 16th tied over a beat.
pub const STUB_PENALTY: f64 = 0.35;

/// The written note would cross a beat and end on a 16th tied from it.
fn stub(start: i64, end: i64) -> bool {
    let b = TICKS_PER_BEAT;
    let e = crate::py::pymod(end, b);
    crate::py::floordiv(start, b) != crate::py::floordiv(end - 1, b) && (e == 6 || e == 18) && e < end - start
}

fn readable(performed: f64, room: Option<i64>, start: i64) -> i64 {
    let mut cands: Vec<i64> = READABLE.iter().copied().filter(|&c| room.map_or(true, |r| c <= r)).collect();
    if let Some(r) = room {
        if !cands.contains(&r) && r <= READABLE[READABLE.len() - 1] {
            cands.push(r);
        }
    }
    if cands.is_empty() {
        return room.filter(|&r| r != 0).unwrap_or(1).max(1);
    }
    let p = performed.max(1.0);
    let key = |c: i64| ((c as f64 / p).ln().abs() + if stub(start, start + c) { STUB_PENALTY } else { 0.0 }, -c);
    let mut best = cands[0];
    for &c in &cands[1..] {
        let (kb, kc) = (key(best), key(c));
        if kc.0 < kb.0 || (kc.0 == kb.0 && kc.1 < kb.1) {
            best = c;
        }
    }
    best
}

/// Part-writing choices of [`written_durations`] (both 0 by default).
#[derive(Debug, Clone, Copy, Default, PartialEq)]
pub struct WriteOptions {
    /// Write every note whose next onset is at most this far away (ticks) up to it.
    pub hold_within: i64,
    /// The shortest value a detached note gets (ticks).
    pub min_detached: i64,
}

/// Written length and staccato flag per note of one voice (chords share an
/// onset), in input order. Performed length comes from onset_s/offset_s through
/// `bm` when given, else from the quantized start/end.
pub fn written_durations(notes: &[QNote], bm: Option<&BeatMap>) -> Vec<Written> {
    written_durations_with(notes, bm, WriteOptions::default())
}

pub fn written_durations_with(notes: &[QNote], bm: Option<&BeatMap>, o: WriteOptions) -> Vec<Written> {
    if notes.is_empty() {
        return Vec::new();
    }
    let mut starts: Vec<i64> = notes.iter().map(|q| q.start).collect();
    starts.sort();
    starts.dedup();
    let nxt = |s: i64| -> Option<i64> {
        let i = starts.partition_point(|&x| x <= s);
        starts.get(i).copied()
    };
    let perf: Vec<f64> = match bm {
        Some(bm) => notes.iter().map(|q| (bm.to_beats(q.offset_s) - bm.to_beats(q.onset_s)).max(0.0) * TICKS_PER_BEAT as f64).collect(),
        None => notes.iter().map(|q| (q.end - q.start) as f64).collect(),
    };
    notes
        .iter()
        .zip(perf)
        .map(|(q, p)| {
            let room = nxt(q.start).map(|n| n - q.start);
            let dur = match room {
                Some(r) if r <= o.hold_within || (p >= LEGATO_RATIO * r as f64 && r as f64 - p <= MAX_HELD_GAP) => r,
                _ => {
                    let d = readable(p, room, q.start);
                    if d < o.min_detached {
                        room.map_or(o.min_detached, |r| o.min_detached.min(r))
                    } else {
                        d
                    }
                }
            };
            Written { dur, performed: p, staccato: p < STACCATO_RATIO * dur as f64 }
        })
        .collect()
}

/// Set each note's end to its written length; returns (note, Written) pairs sorted by start.
pub fn apply_written(notes: Vec<QNote>, bm: Option<&BeatMap>) -> Vec<(QNote, Written)> {
    apply_written_with(notes, bm, WriteOptions::default())
}

pub fn apply_written_with(mut notes: Vec<QNote>, bm: Option<&BeatMap>, o: WriteOptions) -> Vec<(QNote, Written)> {
    notes.sort_by_key(|q| q.start);
    let res = written_durations_with(&notes, bm, o);
    notes
        .into_iter()
        .zip(res)
        .map(|(mut q, w)| {
            q.end = q.start + w.dur;
            (q, w)
        })
        .collect()
}
