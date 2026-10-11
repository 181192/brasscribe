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
        v.sort_by(crate::py::fcmp);
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

// ---------------------------------------------------------------- meter from the notes

/// More labelled downbeats per beat than this: the labels carry no bar information.
pub const MAX_DOWNBEAT_RATE: f64 = 0.5;
pub const METERS: [i64; 3] = [2, 3, 4];
pub const ONSET_TOL_BEATS: f64 = 0.2;
/// Weight of the note accents against the tracker's (over-frequent) downbeat labels.
pub const ACCENT_WEIGHT: f64 = 0.25;
/// In units of the per-beat downbeat score (a label vote is 1).
pub const PHASE_JUMP_COST: f64 = 4.0;

#[derive(Debug, Clone, PartialEq)]
pub struct Meter {
    pub beats_per_bar: i64,
    /// A beat index that starts a bar.
    pub first_downbeat: i64,
    /// False: inferred from the note accents.
    pub from_labels: bool,
    /// Beats divide in three (6/8, 9/8, 12/8 read at the dotted-quarter beat).
    pub compound: bool,
    /// Accent contrast of the chosen meter and phase (inferred only).
    pub strength: f64,
    /// Beat times adjusted to the tracked bar phase (inferred only).
    pub times: Option<Vec<f64>>,
}

pub fn downbeat_rate(downbeat: &[bool]) -> f64 {
    if downbeat.is_empty() {
        0.0
    } else {
        py::pairwise_sum_f64(&downbeat.iter().map(|&d| d as i64 as f64).collect::<Vec<_>>()) / downbeat.len() as f64
    }
}

fn np_mean(v: &[f64]) -> f64 {
    py::pairwise_sum_f64(v) / v.len() as f64
}

/// First index i with a[i] >= v (`np.searchsorted`, side left).
fn searchsorted(a: &[f64], v: f64) -> usize {
    a.partition_point(|&x| x < v)
}

/// Accent per beat from the notes starting on it: 1 per note plus its length in
/// beats (capped at 2), so long notes (agogic accents) weigh more.
pub fn beat_strengths(t: &[f64], onsets: &[f64], durations: &[f64]) -> Vec<f64> {
    let ibi: Vec<f64> = t.windows(2).map(|w| w[1] - w[0]).collect();
    let mut s = vec![0.0; t.len()];
    for (&on, &d) in onsets.iter().zip(durations) {
        let k = searchsorted(t, on) as i64;
        for j in [k - 1, k] {
            if 0 <= j && (j as usize) < t.len() {
                let j = j as usize;
                let beat = if ibi.is_empty() { 1.0 } else { ibi[j.min(ibi.len() - 1)] };
                if (on - t[j]).abs() <= ONSET_TOL_BEATS * beat {
                    let r = d / beat;
                    s[j] += 1.0 + if r < 2.0 { r } else { 2.0 };
                    break;
                }
            }
        }
    }
    s
}

/// Beats per bar and bar phase from the labels and the note accents.
///
/// For each meter m and phase p the score is how much beats p, p+m, ... exceed
/// the average in label rate plus ACCENT_WEIGHT x note accent (normalised to
/// mean 1). The best score wins; a bar of 4 must also have its downbeat clearly
/// above beat 3, else it is 2.
pub fn infer_meter(t: &[f64], onsets: &[f64], durations: &[f64], downbeat: Option<&[bool]>, positions: Option<&[i64]>) -> Meter {
    let mut a = beat_strengths(t, onsets, durations);
    let am = np_mean(&a);
    if am > 0.0 {
        a = a.iter().map(|x| x / am).collect();
    }
    let lab: Vec<f64> = match downbeat {
        Some(d) => d.iter().map(|&x| x as i64 as f64).collect(),
        None => vec![0.0; t.len()],
    };
    let s: Vec<f64> = lab.iter().zip(&a).map(|(l, x)| l + ACCENT_WEIGHT * x).collect();
    let mean = if s.is_empty() { 0.0 } else { np_mean(&s) };
    let phase_score = |m: i64, p: i64| -> f64 {
        let seg: Vec<f64> = s.iter().skip(p as usize).step_by(m as usize).copied().collect();
        if seg.is_empty() {
            f64::NEG_INFINITY
        } else {
            np_mean(&seg) - mean
        }
    };
    // (score, phase) per meter; ties go to the larger phase (tuple max)
    let best: Vec<(i64, f64, i64)> = METERS
        .iter()
        .map(|&m| {
            let mut b = (phase_score(m, 0), 0);
            for p in 1..m {
                let c = (phase_score(m, p), p);
                if c.0 > b.0 || (c.0 == b.0 && c.1 > b.1) {
                    b = c;
                }
            }
            (m, b.0, b.1)
        })
        .collect();
    let mut pick = best[0];
    for &b in &best[1..] {
        if b.1 > pick.1 {
            pick = b;
        }
    }
    let mut m = pick.0;
    if m == 4 {
        let (c4, p4) = (pick.1, pick.2);
        if phase_score(4, (p4 + 2) % 4) > 0.5 * c4 {
            m = 2;
        }
    }
    let c = best.iter().find(|b| b.0 == m).unwrap().1;
    // Compound: most onsets inside a beat fall on its thirds rather than its halves.
    let mut frac = Vec::new();
    for &on in onsets {
        let k = searchsorted(t, on) as i64 - 1;
        if 0 <= k && (k as usize) + 1 < t.len() {
            let k = k as usize;
            let f = (on - t[k]) / (t[k + 1] - t[k]);
            if 0.1 < f && f < 0.9 {
                frac.push(f);
            }
        }
    }
    let thirds = frac
        .iter()
        .filter(|&&f| {
            let a = (f - 1.0 / 3.0).abs().min((f - 2.0 / 3.0).abs());
            let h = (f - 0.5).abs();
            a < if h < 0.1 { h } else { 0.1 }
        })
        .count();
    let compound = !frac.is_empty() && thirds as f64 > 0.5 * frac.len() as f64;
    // Every label votes: a beat labelled k (1 = downbeat) supports bar position k - 1.
    let emission = positions.filter(|_| m > 1).map(|pos| {
        let mut e: Vec<Vec<f64>> = pos.iter().map(|&p| (0..m).map(|j| (p == j + 1) as i64 as f64).collect()).collect();
        for j in 0..m as usize {
            let col_sum: f64 = e.iter().map(|r| r[j]).fold(0.0, |acc, x| acc + x);
            let mean = col_sum / e.len() as f64;
            for r in e.iter_mut() {
                r[j] -= mean;
            }
        }
        e
    });
    // Constant labels say nothing about the phase: then the accents decide.
    let (lo, hi) = lab.iter().fold((f64::INFINITY, f64::NEG_INFINITY), |(l, h), &x| (l.min(x), h.max(x)));
    let phase = if lo != hi { lab.clone() } else { s.clone() };
    let (times, first) = track_bar_phase(t, &phase, m, PHASE_JUMP_COST, emission.as_deref());
    Meter { beats_per_bar: m, first_downbeat: first, from_labels: false, compound, strength: py::py_round(c, 3), times: Some(times) }
}

/// The tracker's bars when its downbeat labels give bars (a most common gap of 2
/// beats or more), else bars inferred from the labels and the note accents.
pub fn meter_of(t: &[f64], downbeat: &[bool], onsets: &[f64], durations: &[f64], positions: Option<&[i64]>) -> Meter {
    let idx: Vec<usize> = downbeat.iter().enumerate().filter(|(_, &d)| d).map(|(i, _)| i).collect();
    let mut counts: Vec<(i64, usize)> = Vec::new();
    for w in idx.windows(2) {
        let g = (w[1] - w[0]) as i64;
        match counts.iter_mut().find(|(k, _)| *k == g) {
            Some(e) => e.1 += 1,
            None => counts.push((g, 1)),
        }
    }
    let mut bpb = 0;
    let mut bc = 0;
    for &(k, c) in &counts {
        if c > bc {
            bpb = k;
            bc = c;
        }
    }
    if bpb >= 2 {
        return Meter { beats_per_bar: bpb, first_downbeat: idx.first().map(|&i| i as i64).unwrap_or(0), from_labels: true, compound: false, strength: 0.0, times: None };
    }
    infer_meter(t, onsets, durations, Some(downbeat), positions)
}

/// Follow the bar phase through the piece (Viterbi) and make the beat grid fit
/// it. States are positions in the bar; from position j the next beat is j+1
/// (free), j again (an inserted beat: dropped) or j+2 (a missed beat: restored
/// halfway). Returns the adjusted beat times and the index of the first downbeat.
pub fn track_bar_phase(t: &[f64], strength: &[f64], m: i64, jump_cost: f64, emission: Option<&[Vec<f64>]>) -> (Vec<f64>, i64) {
    let n = t.len();
    if n < 2 || m < 2 {
        return (t.to_vec(), 0);
    }
    let mu = np_mean(strength);
    let default: Vec<Vec<f64>>;
    let em: &[Vec<f64>] = match emission {
        Some(e) => e,
        None => {
            default = strength.iter().map(|x| (0..m).map(|j| if j == 0 { x - mu } else { 0.0 }).collect()).collect();
            &default
        }
    };
    let mu_ = m as usize;
    let mut score = vec![vec![f64::NEG_INFINITY; mu_]; n];
    let mut back = vec![vec![(0usize, 0u8); mu_]; n];
    score[0] = em[0].clone();
    let ibi: Vec<f64> = t.windows(2).map(|w| w[1] - w[0]).collect();
    let med = py::median(&ibi);
    for k in 1..n {
        let r = ibi[k - 1] / med;
        let x = r - 0.5;
        let drop = jump_cost * (0.25 + 2.0 * if x > 0.0 { x } else { 0.0 });
        let restore = jump_cost * (0.25 + 2.0 * (r - 2.0).abs());
        for j in 0..mu_ {
            let p1 = (j + mu_ - 1) % mu_;
            let p2 = (j + 2 * mu_ - 2) % mu_;
            let cands = [(score[k - 1][p1], p1, 0u8), (score[k - 1][j] - drop, j, 1u8), (score[k - 1][p2] - restore, p2, 2u8)];
            let mut best = cands[0];
            for c in &cands[1..] {
                if c.0 > best.0 {
                    best = *c;
                }
            }
            score[k][j] = best.0 + em[k][j];
            back[k][j] = (best.1, best.2);
        }
    }
    let last = &score[n - 1];
    let mut j = 0;
    for (i, &v) in last.iter().enumerate() {
        if v > last[j] {
            j = i;
        }
    }
    let mut states = vec![j];
    let mut moves = Vec::new();
    for k in (1..n).rev() {
        let (pj, mv) = back[k][j];
        moves.push(mv);
        j = pj;
        states.push(j);
    }
    states.reverse();
    moves.reverse();
    let mut out = vec![t[0]];
    let mut pos = vec![states[0]];
    for k in 1..n {
        match moves[k - 1] {
            1 => continue,
            2 => {
                out.push((out[out.len() - 1] + t[k]) / 2.0);
                pos.push((pos[pos.len() - 1] + 1) % mu_);
            }
            _ => {}
        }
        out.push(t[k]);
        pos.push(states[k]);
    }
    let first = pos.iter().position(|&p| p == 0).unwrap_or(0) as i64;
    (out, first)
}

// ---------------------------------------------------------------- the solo path's bar grid

/// Inferred meters with a weaker phase contrast keep the grid's own bars.
pub const MIN_METER_STRENGTH: f64 = 0.15;

/// Carry per-beat labels from one beat grid to another (nearest beat within a tenth of a beat).
pub fn labels_on(new_times: &[f64], old_times: &[f64], labels: &[i64], fill: i64) -> Vec<i64> {
    let mut out = vec![fill; new_times.len()];
    if old_times.len() < 2 || new_times.is_empty() {
        return out;
    }
    let ibi: Vec<f64> = old_times.windows(2).map(|w| w[1] - w[0]).collect();
    let tol = 0.1 * py::median(&ibi);
    for (i, &x) in new_times.iter().enumerate() {
        let k = searchsorted(old_times, x).clamp(1, old_times.len() - 1);
        let near = if (old_times[k - 1] - x).abs() <= (old_times[k] - x).abs() { k - 1 } else { k };
        if (old_times[near] - x).abs() <= tol {
            out[i] = labels[near];
        }
    }
    out
}

/// Notes of one voice that keep an onset of their own when quantized on `times`.
pub fn kept_notes(times: &[f64], onsets: &[f64], durations: &[f64]) -> usize {
    if times.len() < 2 || onsets.is_empty() {
        return 0;
    }
    let notes: Vec<crate::midi::RawNote> = onsets
        .iter()
        .zip(durations)
        .map(|(&o, &d)| crate::midi::RawNote::new(60, o, o + if 1e-3 > d { 1e-3 } else { d }))
        .collect();
    crate::quantize::quantize(&notes, times, true, false).len()
}

/// Bars for a beat grid whose downbeat labels do not give bars (most common gap
/// under 2 beats). `times` is the final grid with the tracker's labels carried
/// onto it; `beats_per_bar` and `first_downbeat` are what the grid gives
/// without inference. The inferred meter replaces them only when its phase
/// contrast reaches MIN_METER_STRENGTH. Fitting the grid to the tracked phase
/// must not merge notes: if the fitted grid keeps fewer notes apart, the input
/// grid is kept and only the phase is taken from it.
#[allow(clippy::too_many_arguments)]
pub fn solo_meter(times: &[f64], downbeat: &[bool], positions: &[i64], beats_per_bar: i64, first_downbeat: i64, onsets: &[f64], durations: &[f64]) -> Meter {
    let m = infer_meter(times, onsets, durations, Some(downbeat), Some(positions));
    if m.strength < MIN_METER_STRENGTH {
        return Meter { beats_per_bar, first_downbeat, from_labels: true, compound: false, strength: 0.0, times: None };
    }
    if let Some(mt) = &m.times {
        if kept_notes(mt, onsets, durations) < kept_notes(times, onsets, durations) {
            let constant = downbeat.iter().all(|&d| d == downbeat[0]);
            let phase: Vec<f64> = if !constant { downbeat.iter().map(|&d| d as i64 as f64).collect() } else { beat_strengths(times, onsets, durations) };
            let (_, first) = track_bar_phase(times, &phase, m.beats_per_bar, 1e9, None);
            return Meter { first_downbeat: first, times: Some(times.to_vec()), ..m };
        }
    }
    m
}

#[cfg(test)]
mod meter_tests {
    use super::*;

    fn grid(n: usize) -> Vec<f64> {
        (0..n).map(|k| k as f64 * 0.5).collect()
    }

    #[test]
    fn plausible_labels_pass_through() {
        let t = grid(40);
        let lab: Vec<bool> = (0..40).map(|k| k % 4 == 1).collect();
        let m = meter_of(&t, &lab, &t, &vec![0.2; 40], None);
        assert!(m.from_labels && m.beats_per_bar == 4 && m.first_downbeat == 1 && m.times.is_none());
    }

    #[test]
    fn labels_on_every_beat_meter_from_accents() {
        for meter in [3usize, 4] {
            let t: Vec<f64> = (0..12 * meter).map(|k| k as f64 * 0.5).collect();
            let dur: Vec<f64> = (0..t.len()).map(|k| if k % meter == 0 { 1.0 } else { 0.25 }).collect();
            let on: Vec<f64> = t.iter().map(|x| x + 0.01).collect();
            let m = meter_of(&t, &vec![true; t.len()], &on, &dur, None);
            assert!(!m.from_labels && m.beats_per_bar == meter as i64);
            assert_eq!(m.first_downbeat % meter as i64, 0);
        }
    }

    #[test]
    fn track_bar_phase_drops_and_restores() {
        let t = grid(40);
        let strength: Vec<f64> = (0..40).map(|k| (k % 4 == 0) as i64 as f64).collect();
        let mut t_ins = t.clone();
        t_ins.insert(11, 5.25);
        let mut s_ins = strength.clone();
        s_ins.insert(11, 0.0);
        let (out, first) = track_bar_phase(&t_ins, &s_ins, 4, PHASE_JUMP_COST, None);
        assert_eq!((out.len(), first), (40, 0));
        let mut t_miss = t.clone();
        t_miss.remove(10);
        let mut s_miss = strength.clone();
        s_miss.remove(10);
        let (out, _) = track_bar_phase(&t_miss, &s_miss, 4, PHASE_JUMP_COST, None);
        assert_eq!(out.len(), 40);
        assert!(out.iter().zip(&t).all(|(a, b)| (a - b).abs() < 1e-9));
    }
}

/// A take whose beat tracker found fewer than two beats gets a grid from its onsets: the beat is
/// the multiple of the typical inter-onset interval (the median over FALLBACK_MIN_IOI) within
/// FALLBACK_BEAT seconds, nearest FALLBACK_PREFERRED (else FALLBACK_PREFERRED), through the
/// tracked beat (else the first onset), with bars of 4, over the take.
pub const FALLBACK_MULTIPLES: [f64; 6] = [1.0, 2.0, 3.0, 4.0, 6.0, 8.0];
pub const FALLBACK_BEAT: (f64, f64) = (0.4, 0.8);
pub const FALLBACK_PREFERRED: f64 = 0.5;
pub const FALLBACK_MIN_IOI: f64 = 0.05;

/// (beat times, positions 1-4) for a take with fewer than two tracked beats.
pub fn fallback_beats(tracked: &[f64], onsets: &[f64]) -> (Vec<f64>, Vec<i64>) {
    let mut on: Vec<f64> = onsets.iter().map(|&x| py::np_round(x, 3)).collect();
    on.sort_by(crate::py::fcmp);
    on.dedup();
    let ioi: Vec<f64> = on.windows(2).map(|w| w[1] - w[0]).filter(|&d| d > FALLBACK_MIN_IOI).collect();
    let mut period = FALLBACK_PREFERRED;
    if !ioi.is_empty() {
        let base = py::median(&ioi);
        let best = FALLBACK_MULTIPLES
            .iter()
            .map(|m| base * m)
            .filter(|&p| FALLBACK_BEAT.0 <= p && p <= FALLBACK_BEAT.1)
            .min_by(|a, b| crate::py::fcmp(&(a - FALLBACK_PREFERRED).abs(), &(b - FALLBACK_PREFERRED).abs()).then(crate::py::fcmp(a, b)));
        if let Some(p) = best {
            period = p;
        }
    }
    let anchor = tracked.first().copied().or_else(|| on.first().copied()).unwrap_or(0.0);
    let (first, last) = match (on.first(), on.last()) {
        (Some(&a), Some(&b)) => (a, b),
        _ => (anchor, anchor),
    };
    let k0 = ((first - anchor) / period).floor() as i64 - 1;
    let k1 = ((last - anchor) / period).ceil() as i64 + 3;
    let ks: Vec<i64> = (k0..k1).collect();
    (ks.iter().map(|&k| anchor + k as f64 * period).collect(), ks.iter().map(|&k| k.rem_euclid(4) + 1).collect())
}
