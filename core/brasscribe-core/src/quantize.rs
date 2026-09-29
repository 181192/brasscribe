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

/// Dense passages (fast runs, trills) on a monophonic line: a beat whose chosen grid would put two onsets on
/// one slot picks again from these grids, 32nds included (see `choose_grids_dense`).
pub const DENSE_GRIDS: [(i64, f64); 6] = [(1, 0.0), (2, 0.01), (4, 0.03), (3, 0.06), (6, 0.12), (8, 0.2)];
pub const COLLIDE: f64 = 1.0;
/// Snap error weight when a dense beat chooses again: triplets are not 16ths 50 ms off.
pub const DENSE_ERR: f64 = 10.0;
/// Leaving the previous beat's grid: a run keeps one subdivision.
pub const SWITCH: f64 = 1.0;
/// A tuplet or 32nd grid needs this many onsets in the beat, each within DENSE_FIT beats of its slot.
pub const DENSE_MIN_ONSETS: usize = 3;
pub const DENSE_FIT: f64 = 0.045;
/// Seconds: a grid of 6 or 8 with shorter slots is not offered (no 64ths on a doubled beat).
pub const MIN_SLOT: f64 = 0.045;

/// Onsets of one beat (fractions `f`) that grid `g` cannot hold: two on one slot, or one rounded onto the
/// next beat's downbeat when that beat starts with an onset.
fn lost(f: &[f64], g: i64, next_head: Option<&Vec<f64>>) -> i64 {
    let gf = g as f64;
    let mut slots: Vec<f64> = f.iter().map(|&x| (x * gf).round_ties_even()).collect();
    let on_next = slots.iter().any(|&s| s == gf);
    slots.sort_by(|a, b| a.partial_cmp(b).unwrap());
    slots.dedup();
    let mut n = (f.len() - slots.len()) as i64;
    if let Some(h) = next_head {
        if on_next && h.iter().any(|&x| x.abs() < 0.5 / gf) {
            n += 1;
        }
    }
    n
}

/// `choose_grids`, then every beat whose grid loses onsets chooses again from DENSE_GRIDS (free time
/// included), paying COLLIDE per onset a grid cannot hold and SWITCH for leaving the previous beat's grid.
/// Beats that hold their onsets keep their choice.
pub fn choose_grids_dense(onset_beats: &[f64], coarse: Option<&Ranges>, beat_seconds: &[f64]) -> HashMap<i64, i64> {
    let mut choice = choose_grids(onset_beats, coarse);
    let mut by_beat: HashMap<i64, Vec<f64>> = HashMap::new();
    for &x in onset_beats {
        let k = beat_index(x);
        by_beat.entry(k).or_default().push(x - k as f64);
    }
    let mut ks: Vec<i64> = by_beat.keys().copied().collect();
    ks.sort();
    for k in ks {
        let f = &by_beat[&k];
        let nxt = by_beat.get(&(k + 1));
        if lost(f, choice[&k], nxt) == 0 {
            continue;
        }
        let spb = if beat_seconds.is_empty() { 1.0 } else { beat_seconds[k.clamp(0, beat_seconds.len() as i64 - 1) as usize] };
        let (mut best, mut best_cost) = (choice[&k], f64::INFINITY);
        for &(g, pen) in DENSE_GRIDS.iter() {
            if g >= 6 && spb / (g as f64) < MIN_SLOT {
                continue;
            }
            let gf = g as f64;
            if matches!(g, 3 | 6 | 8)
                && (f.len() < DENSE_MIN_ONSETS || f.iter().map(|&x| (x - (x * gf).round_ties_even() / gf).abs()).fold(0.0, f64::max) > DENSE_FIT)
            {
                continue; // no evidence for the finer grid
            }
            let sq: Vec<f64> = f
                .iter()
                .map(|&x| {
                    let d = x - (x * gf).round_ties_even() / gf;
                    d * d
                })
                .collect();
            let switch = if choice.get(&(k - 1)).is_some_and(|&p| p != g) { SWITCH } else { 0.0 };
            let cost = DENSE_ERR * py::pairwise_sum_f64(&sq) + pen * f.len() as f64 + COLLIDE * lost(f, g, nxt) as f64 + switch;
            if cost < best_cost {
                best = g;
                best_cost = cost;
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
    quantize_with(notes, beat_times, monophonic, auto_level, coarse, false)
}

/// Notes on the beat grid. `dense` (a monophonic line: the solo) lets beats whose grid would lose onsets
/// choose a finer one (`choose_grids_dense`), and moves a note that still lands on a taken slot to the next
/// free slot of its beat's grid, at half its confidence, instead of dropping it.
pub fn quantize_with(
    notes: &[RawNote],
    beat_times: &[f64],
    monophonic: bool,
    auto_level: bool,
    coarse: Option<&Ranges>,
    dense: bool,
) -> Vec<QNote> {
    if notes.is_empty() {
        return Vec::new();
    }
    let onsets: Vec<f64> = notes.iter().map(|n| n.onset).collect();
    let bt = if auto_level { choose_level(beat_times, &onsets) } else { beat_times.to_vec() };
    let bm = BeatMap::new(&bt).expect("two beats");
    let on: Vec<f64> = notes.iter().map(|n| bm.to_beats(n.onset)).collect();
    let off: Vec<f64> = notes.iter().map(|n| bm.to_beats(n.offset)).collect();
    let dense = dense && monophonic;
    let grids = if dense {
        let n = bt.len();
        let mut spb: Vec<f64> = bt.windows(2).map(|w| w[1] - w[0]).collect();
        spb.push(bt[n - 1] - bt[n - 2]);
        choose_grids_dense(&on, coarse, &spb)
    } else {
        choose_grids(&on, coarse)
    };
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
    if dense {
        out.sort_by(|a, b| a.start.cmp(&b.start).then(a.onset_s.partial_cmp(&b.onset_s).unwrap()).then(b.pitch.cmp(&a.pitch)));
        return monophonize_dense(out, &grids);
    }
    out.sort_by_key(|q| (q.start, -q.pitch));
    if monophonic {
        out = monophonize(out);
    }
    out
}

/// `monophonize`, but a note on a taken slot moves to the next slot of its beat's grid when that is free
/// (before the next note), at half its confidence; only then is it dropped.
fn monophonize_dense(notes: Vec<QNote>, grids: &HashMap<i64, i64>) -> Vec<QNote> {
    let starts: Vec<i64> = notes.iter().map(|q| q.start).collect();
    let mut kept: Vec<QNote> = Vec::new();
    for (i, mut q) in notes.into_iter().enumerate() {
        if let Some(last) = kept.last() {
            if q.start <= last.start {
                let k = py::floordiv(last.start, TICKS_PER_BEAT);
                let new = last.start + TICKS_PER_BEAT / grids.get(&k).copied().unwrap_or(4);
                if i + 1 < starts.len() && starts[i + 1] <= new {
                    continue;
                }
                q.end = q.end.max(new + (new - last.start));
                q.start = new;
                q.confidence = py::py_round(q.confidence * 0.5, 3);
            }
        }
        if let Some(last) = kept.last_mut() {
            if last.end > q.start {
                last.end = q.start;
            }
        }
        kept.push(q);
    }
    kept
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
