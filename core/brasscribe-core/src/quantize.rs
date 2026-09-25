//! Beat-grid quantization: note times in seconds -> positions in ticks.
//!
//! Times are warped onto the detected beat grid (piecewise linear between
//! beats), so tempo drift is absorbed before snapping. Each beat then picks the
//! simplest subdivision that explains the onsets falling in it; simpler grids
//! get a smaller penalty so a slightly late 8th note is not turned into a
//! 16th-triplet.

use std::collections::HashMap;

use crate::midi::RawNote;
use crate::model::TICKS_PER_BEAT;
use crate::py;

/// Subdivisions per beat and their complexity penalty (squared-beat units per
/// note), in the order they are tried.
pub const GRIDS: [(i64, f64); 5] = [(1, 0.0), (2, 0.01), (4, 0.03), (3, 0.06), (6, 0.12)];

#[derive(Debug, Clone, PartialEq)]
pub struct QNote {
    pub pitch: i32,
    /// Ticks from beat 0.
    pub start: i64,
    pub end: i64,
    pub onset_s: f64,
    pub offset_s: f64,
    pub confidence: f64,
    /// "staccato", "fermata".
    pub articulations: Vec<String>,
}

/// Monotonic mapping between seconds and fractional beat index.
#[derive(Debug, Clone)]
pub struct BeatMap {
    t: Vec<f64>,
    b: Vec<f64>,
}

impl BeatMap {
    pub fn new(beat_times: &[f64]) -> Result<Self, String> {
        if beat_times.len() < 2 {
            return Err("need at least two beats".into());
        }
        Ok(BeatMap { t: beat_times.to_vec(), b: (0..beat_times.len()).map(|i| i as f64).collect() })
    }

    pub fn to_beats(&self, s: f64) -> f64 {
        let t = &self.t;
        let n = t.len();
        let head = t[1] - t[0];
        let tail = t[n - 1] - t[n - 2];
        if s < t[0] {
            (s - t[0]) / head
        } else if s > t[n - 1] {
            self.b[n - 1] + (s - t[n - 1]) / tail
        } else {
            py::interp(s, t, &self.b)
        }
    }

    pub fn to_seconds(&self, x: f64) -> f64 {
        let t = &self.t;
        let n = t.len();
        let head = t[1] - t[0];
        let tail = t[n - 1] - t[n - 2];
        if x < 0.0 {
            t[0] + x * head
        } else if x > self.b[n - 1] {
            t[n - 1] + (x - self.b[n - 1]) * tail
        } else {
            py::interp(x, &self.b, t)
        }
    }
}

/// Double the beat grid when the tracker locked onto half notes.
///
/// When the detected tempo is slow and notes are dense relative to the beat,
/// the notated beat is almost always twice as fast.
pub fn choose_level(beat_times: &[f64], onsets: &[f64]) -> Vec<f64> {
    let diffs: Vec<f64> = beat_times.windows(2).map(|w| w[1] - w[0]).collect();
    let bpm = 60.0 / py::median(&diffs);
    let mut on: Vec<f64> = onsets.iter().map(|&x| py::np_round(x, 2)).collect();
    on.sort_by(|a, b| a.partial_cmp(b).unwrap());
    on.dedup();
    let bm = BeatMap::new(beat_times).expect("two beats");
    let ob: Vec<f64> = on.iter().map(|&x| bm.to_beats(x)).collect();
    let ioi: Vec<f64> = ob.windows(2).map(|w| w[1] - w[0]).filter(|&d| d > 0.08).collect();
    if !ioi.is_empty() && bpm < 90.0 && py::median(&ioi) <= 0.3 {
        let mut out = beat_times.to_vec();
        out.extend(beat_times.windows(2).map(|w| (w[0] + w[1]) / 2.0));
        out.sort_by(|a, b| a.partial_cmp(b).unwrap());
        return out;
    }
    beat_times.to_vec()
}

#[inline]
fn beat_index(x: f64) -> i64 {
    (x + 1.0 / 12.0).floor() as i64
}

/// Inside free-time regions: quarters and 8ths only.
pub const FREE_GRIDS: [i64; 2] = [1, 2];

/// [start, end) beat-index ranges where only `FREE_GRIDS` apply.
pub type Ranges = [(f64, f64)];

fn in_ranges(k: i64, ranges: Option<&Ranges>) -> bool {
    ranges.is_some_and(|r| r.iter().any(|&(a, b)| a <= k as f64 && (k as f64) < b))
}

/// Pick a subdivision per beat index that minimizes squared snap error + complexity.
///
/// Beats inside a `coarse` range choose only from FREE_GRIDS: in proportional
/// notation finer values would just transcribe rubato.
pub fn choose_grids(onset_beats: &[f64], coarse: Option<&Ranges>) -> HashMap<i64, i64> {
    let mut by_beat: HashMap<i64, Vec<f64>> = HashMap::new();
    for &x in onset_beats {
        let k = beat_index(x);
        by_beat.entry(k).or_default().push(x - k as f64);
    }
    let mut choice = HashMap::new();
    for (k, fracs) in by_beat {
        let free = in_ranges(k, coarse);
        let mut best = GRIDS[0].0;
        let mut best_cost = f64::INFINITY;
        for &(g, pen) in GRIDS.iter().filter(|(g, _)| !free || FREE_GRIDS.contains(g)) {
            let gf = g as f64;
            let sq: Vec<f64> = fracs.iter().map(|&f| {
                let d = f - (f * gf).round_ties_even() / gf;
                d * d
            }).collect();
            let cost = py::pairwise_sum_f64(&sq) + pen * fracs.len() as f64;
            if cost < best_cost {
                best_cost = cost;
                best = g;
            }
        }
        choice.insert(k, best);
    }
    choice
}

pub fn snap(x: f64, grids: &HashMap<i64, i64>, default: i64) -> i64 {
    let k = beat_index(x);
    let g = *grids.get(&k).unwrap_or(&default) as f64;
    let r = ((x - k as f64) * g).round_ties_even();
    ((k as f64 + r / g) * TICKS_PER_BEAT as f64).round_ties_even() as i64
}

pub fn quantize(notes: &[RawNote], beat_times: &[f64], monophonic: bool, auto_level: bool) -> Vec<QNote> {
    quantize_coarse(notes, beat_times, monophonic, auto_level, None)
}

pub fn quantize_coarse(notes: &[RawNote], beat_times: &[f64], monophonic: bool, auto_level: bool, coarse: Option<&Ranges>) -> Vec<QNote> {
    if notes.is_empty() {
        return Vec::new();
    }
    let onsets: Vec<f64> = notes.iter().map(|n| n.onset).collect();
    let bt = if auto_level { choose_level(beat_times, &onsets) } else { beat_times.to_vec() };
    let bm = BeatMap::new(&bt).expect("two beats");
    let on: Vec<f64> = notes.iter().map(|n| bm.to_beats(n.onset)).collect();
    let off: Vec<f64> = notes.iter().map(|n| bm.to_beats(n.offset)).collect();
    let grids = choose_grids(&on, coarse);
    let mut out: Vec<QNote> = notes
        .iter()
        .zip(on.iter().zip(off.iter()))
        .map(|(n, (&a, &b))| {
            let start = snap(a, &grids, 4);
            let kb = beat_index(b);
            let end = snap(b, &grids, if in_ranges(kb, coarse) { 2 } else { 4 });
            let k = beat_index(a);
            let unit = TICKS_PER_BEAT / grids.get(&k).copied().unwrap_or(if in_ranges(k, coarse) { 2 } else { 4 });
            QNote { pitch: n.pitch, start, end: end.max(start + unit), onset_s: n.onset, offset_s: n.offset, confidence: n.confidence.unwrap_or(1.0), articulations: Vec::new() }
        })
        .collect();
    out.sort_by_key(|q| (q.start, -q.pitch));
    if monophonic {
        out = monophonize(out);
    }
    out
}

/// Keep the highest note per onset and cut each note at the next onset.
fn monophonize(notes: Vec<QNote>) -> Vec<QNote> {
    let mut kept: Vec<QNote> = Vec::new();
    for q in notes {
        if let Some(last) = kept.last_mut() {
            if last.start == q.start {
                continue;
            }
            if last.end > q.start {
                last.end = q.start;
            }
        }
        kept.push(q);
    }
    kept
}

/// Infer notated durations in one voice: hold each note until the next onset.
///
/// A gap up to `max_gap_ticks`, or one that is small relative to the note
/// (gap <= min_ratio * duration), is absorbed; longer gaps stay as rests.
pub fn fill_gaps(notes: Vec<QNote>, max_gap_ticks: i64, min_ratio: f64) -> Vec<QNote> {
    let mut out = notes;
    out.sort_by_key(|q| q.start);
    let mut starts: Vec<i64> = out.iter().map(|q| q.start).collect();
    starts.dedup();
    let nxt: HashMap<i64, i64> = starts.windows(2).map(|w| (w[0], w[1])).collect();
    for q in out.iter_mut() {
        let Some(&n) = nxt.get(&q.start) else { continue };
        let gap = n - q.end;
        let lim = (max_gap_ticks as f64).max(min_ratio * (q.end - q.start) as f64);
        if gap > 0 && (gap as f64) <= lim {
            q.end = n;
        } else if gap < 0 {
            q.end = n;
        }
    }
    out
}
