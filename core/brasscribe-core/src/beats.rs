//! Beat-track cleanup: restore missed beats, remove inserted ones, and fix the
//! bar phase from the tracker's downbeat labels.
//!
//! Against the local tempo (median of the neighbouring intervals): an interval
//! of about k beats (k = 2, 3) gets k - 1 evenly spaced beats if a note starts
//! on one of them; an interval under `SPLIT_RATIO` of a beat loses the beat that
//! leaves the more regular pair of intervals. Free-time runs are left alone.
//! `clean_beats_gated` keeps the result only when the evidence says the track
//! was wrong.

use crate::py;

/// Intervals on each side for the local tempo.
pub const WINDOW: usize = 8;
/// An interval within 20% of k beats (k >= 2) is k beats.
pub const MISS_TOL: f64 = 0.2;
/// An interval under 60% of a beat has an inserted beat.
pub const SPLIT_RATIO: f64 = 0.6;
/// Beats: a restored beat needs a note onset this close.
pub const ONSET_TOL: f64 = 0.15;
pub const MIN_ONSETS: usize = 1;
pub const MIN_AGREEMENT_GAIN: f64 = 0.02;
pub const MIN_EDITS_UNLABELLED: usize = 3;

#[derive(Debug, Clone, PartialEq)]
pub struct CleanBeats {
    pub times: Vec<f64>,
    /// Labelled downbeat per beat (false for restored beats).
    pub downbeat: Vec<bool>,
    pub inserted: usize,
    pub removed: usize,
    /// False when gated: the times and labels are the tracker's own.
    pub applied: bool,
}

/// (value, count) in order of first appearance; the most common, first seen on ties.
fn most_common(values: impl Iterator<Item = i64>) -> Option<(i64, usize)> {
    let mut counts: Vec<(i64, usize)> = Vec::new();
    for v in values {
        match counts.iter_mut().find(|(k, _)| *k == v) {
            Some(e) => e.1 += 1,
            None => counts.push((v, 1)),
        }
    }
    let mut best: Option<(i64, usize)> = None;
    for &(k, c) in &counts {
        if best.map_or(true, |(_, bc)| c > bc) {
            best = Some((k, c));
        }
    }
    best
}

impl CleanBeats {
    /// Share of labelled downbeats that fall on the majority bar phase.
    pub fn agreement(&self, beats_per_bar: i64) -> f64 {
        let idx: Vec<i64> = (0..self.downbeat.len()).filter(|&i| self.downbeat[i]).map(|i| i as i64).collect();
        if idx.is_empty() {
            return 0.0;
        }
        let (_, c) = most_common(idx.iter().map(|&i| py::pymod(i, beats_per_bar))).unwrap();
        c as f64 / idx.len() as f64
    }

    /// Beat index (0 <= i < beats_per_bar) of the first downbeat, by majority of the labels.
    pub fn phase(&self, beats_per_bar: i64) -> i64 {
        let idx: Vec<i64> = (0..self.downbeat.len()).filter(|&i| self.downbeat[i]).map(|i| i as i64).collect();
        if idx.is_empty() {
            return 0;
        }
        most_common(idx.iter().map(|&i| py::pymod(i, beats_per_bar))).unwrap().0
    }
}

fn skipped(i: usize, skip: &[(usize, usize)]) -> bool {
    skip.iter().any(|&(a, b)| a <= i && i < b)
}

/// Local beat length: median of the neighbouring intervals, leaving out free-time ones.
fn local(ibi: &[f64], i: usize, skip: &[(usize, usize)]) -> f64 {
    let strict: Vec<f64> = (0..ibi.len()).filter(|&j| !skipped(j, skip)).map(|j| ibi[j]).collect();
    let g = if strict.is_empty() { py::median(ibi) } else { py::median(&strict) };
    let lo = i.saturating_sub(WINDOW);
    let hi = ibi.len().min(i + WINDOW + 1);
    let seg: Vec<f64> = (lo..hi)
        .filter(|&j| j != i && !skipped(j, skip))
        .map(|j| ibi[j] / (1i64.max(py::round_int(ibi[j] / g)) as f64))
        .collect();
    if seg.is_empty() {
        g
    } else {
        py::median(&seg)
    }
}

fn has_onset(on: &[f64], t0: f64, d: f64, k: i64) -> bool {
    let beat = d / k as f64;
    for m in 1..k {
        let x = t0 + beat * m as f64;
        let lo = on.partition_point(|&v| v < x - ONSET_TOL * beat);
        let hi = on.partition_point(|&v| v <= x + ONSET_TOL * beat);
        if hi - lo >= MIN_ONSETS {
            return true;
        }
    }
    false
}

/// Restore missed and remove inserted beats outside the `skip` beat-index ranges.
pub fn clean_beats(times: &[f64], downbeat: Option<&[bool]>, skip: &[(usize, usize)], onsets: Option<&[f64]>) -> CleanBeats {
    let on: Option<Vec<f64>> = onsets.map(|o| {
        let mut v = o.to_vec();
        v.sort_by(|a, b| a.partial_cmp(b).unwrap());
        v
    });
    let mut t: Vec<f64> = times.to_vec();
    let mut lab: Vec<bool> = downbeat.map(|d| d.to_vec()).unwrap_or_else(|| vec![false; t.len()]);
    let mut keep_out: Vec<(usize, usize)> = skip.to_vec();
    let mut removed = 0;
    // Remove inserted beats first, so they do not distort the local tempo for restoring missed ones.
    let mut i = 1;
    while t.len() >= 2 && i < t.len() - 1 {
        let ibi: Vec<f64> = t.windows(2).map(|w| w[1] - w[0]).collect();
        if !skipped(i, &keep_out) && ibi[i - 1] < SPLIT_RATIO * local(&ibi, i - 1, &keep_out) {
            let rf = local(&ibi, i - 1, &keep_out);
            let cost_i = ((t[i + 1] - t[i - 1]) - rf).abs();
            let cost_prev = if i >= 2 { ((t[i] - t[i - 2]) - rf).abs() } else { f64::INFINITY };
            let j = if cost_i <= cost_prev { i } else { i - 1 };
            if lab[j] {
                let k = if j == i - 1 { j + 1 } else { j - 1 };
                lab[k] = true;
            }
            t.remove(j);
            lab.remove(j);
            keep_out = keep_out.iter().map(|&(a, b)| (a - (a > j) as usize, b - (b > j) as usize)).collect();
            removed += 1;
            continue;
        }
        i += 1;
    }
    let mut inserted = 0;
    let mut out_t = vec![t[0]];
    let mut out_l = vec![lab[0]];
    let ibi: Vec<f64> = t.windows(2).map(|w| w[1] - w[0]).collect();
    for (i, &d) in ibi.iter().enumerate() {
        if !skipped(i, &keep_out) {
            let rf = local(&ibi, i, &keep_out);
            let k = py::round_int(d / rf);
            if k >= 2 && (d / rf - k as f64).abs() <= MISS_TOL * k as f64 && on.as_ref().map_or(true, |o| has_onset(o, t[i], d, k)) {
                for m in 1..k {
                    out_t.push(t[i] + d * m as f64 / k as f64);
                    out_l.push(false);
                }
                inserted += (k - 1) as usize;
            }
        }
        out_t.push(t[i + 1]);
        out_l.push(lab[i + 1]);
    }
    CleanBeats { times: out_t, downbeat: out_l, inserted, removed, applied: true }
}

/// `clean_beats`, applied only when the evidence says the track was wrong: with bars the
/// downbeat labels must agree better with the cleaned beats; with one beat per bar only a
/// systematic problem is fixed.
pub fn clean_beats_gated(times: &[f64], downbeat: &[bool], beats_per_bar: i64, skip: &[(usize, usize)], onsets: Option<&[f64]>) -> CleanBeats {
    let raw = CleanBeats { times: times.to_vec(), downbeat: downbeat.to_vec(), inserted: 0, removed: 0, applied: false };
    let c = clean_beats(times, Some(downbeat), skip, onsets);
    let edits = c.inserted + c.removed;
    if edits == 0 {
        return raw;
    }
    let ok = if beats_per_bar > 1 {
        c.agreement(beats_per_bar) >= raw.agreement(beats_per_bar) + MIN_AGREEMENT_GAIN
    } else {
        edits >= MIN_EDITS_UNLABELLED
    };
    if !ok {
        return raw;
    }
    c
}
