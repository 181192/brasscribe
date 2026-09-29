//! Pitch-change onsets from the SwiftF0 contour: notes the segmentation merged
//! (slurred trills and runs), octave flips, and glides it split off. The same
//! rules as the reference (brasscribe_music/onsets.py), bit for bit.

use crate::durations::Contour;
use crate::midi::RawNote;
use crate::py;

pub const TIGHT: f64 = 0.25;
pub const MIN_RUN: usize = 3;
pub const STEP_DWELL: f64 = 0.7;
pub const SEMITONE_STEP_FRAMES: usize = 5;
pub const DWELL: f64 = 0.7;
pub const TRILL_DWELL: f64 = 0.85;
pub const TRILL_CHANGES: usize = 4;
pub const LONG_TRILL_CHANGES: usize = 8;
pub const LONG_TRILL_DWELL: f64 = 0.78;
pub const LONG_TRILL_FRAMES: f64 = 5.0;
pub const ALT_MAX_FRAMES: f64 = 16.0;
pub const ALT_MAX_SPAN: i64 = 7;
pub const MIN_SHARE: f64 = 0.25;
pub const GLIDE_FRAMES: usize = 5;
pub const GLIDE_STEP: i64 = 3;
pub const GLIDE_CHAIN_DWELL: f64 = 0.6;
pub const GLIDE_SLOPE: f64 = 22.0;
pub const FLIP_MAX: f64 = 0.3;
pub const CONFIRM_TOL: f64 = 0.05;
pub const GLIDE_MAX: f64 = 0.2;
pub const GLIDE_DWELL: f64 = 0.3;
pub const GLIDE_GAP: f64 = 0.03;
pub const CONFIDENT: f64 = 0.5;
pub const FRAME: f64 = 0.016;

/// (first frame, end frame, semitone) of a plateau.
pub type Plateau = (usize, usize, i64);

/// The piece's offset from A440 in semitones: circular mean of the voiced frames' fractions.
pub fn tuning(midi: &[f64], voiced: &[bool]) -> f64 {
    let k = 2.0 * std::f64::consts::PI;
    let ang: Vec<f64> = midi.iter().zip(voiced).filter(|(_, &v)| v).map(|(&m, _)| k * m).collect();
    if ang.is_empty() {
        return 0.0;
    }
    let s: Vec<f64> = ang.iter().map(|a| a.sin()).collect();
    let c: Vec<f64> = ang.iter().map(|a| a.cos()).collect();
    py::pairwise_sum_f64(&s).atan2(py::pairwise_sum_f64(&c)) / k
}

pub fn voiced(c: &Contour) -> Vec<bool> {
    c.midi
        .iter()
        .enumerate()
        .map(|(i, m)| m.is_finite() && c.confidence.as_ref().map_or(true, |conf| conf[i] > CONFIDENT))
        .collect()
}

/// Runs of >= MIN_RUN frames within TIGHT of one semitone (`x`: fractional semitones, tuned).
pub fn plateaus(x: &[f64], ok: &[bool]) -> Vec<Plateau> {
    let xs: Vec<f64> = x.iter().map(|&v| if v.is_nan() { -1000.0 } else { v }).collect();
    let s: Vec<f64> = xs.iter().map(|v| v.round_ties_even()).collect();
    let tight: Vec<bool> = (0..x.len()).map(|i| ok[i] && (xs[i] - s[i]).abs() <= TIGHT).collect();
    let mut out = Vec::new();
    let mut a: Option<usize> = None;
    for i in 0..=x.len() {
        if i < x.len() && tight[i] {
            if let Some(a0) = a {
                if s[i] == s[a0] {
                    continue;
                }
            }
        }
        if let Some(a0) = a {
            if i - a0 >= MIN_RUN {
                out.push((a0, i, s[a0] as i64));
            }
        }
        a = if i < x.len() && tight[i] { Some(i) } else { None };
    }
    out
}

fn len(p: &Plateau) -> usize {
    p.1 - p.0
}

fn splits(pl: &[Plateau], n_frames: usize) -> bool {
    let sems: Vec<i64> = pl.iter().map(|p| p.2).collect();
    let changes = sems.windows(2).filter(|w| w[0] != w[1]).count();
    if changes == 0 {
        return false;
    }
    let dwell = pl.iter().map(len).sum::<usize>() as f64 / n_frames.max(1) as f64;
    let steps: Vec<i64> = sems.windows(2).filter(|w| w[0] != w[1]).map(|w| w[1] - w[0]).collect();
    if steps.iter().all(|&d| d > 0) || steps.iter().all(|&d| d < 0) {
        if steps.len() == 1 && steps[0].abs() == 1 && pl.iter().map(len).min().unwrap() < SEMITONE_STEP_FRAMES {
            return false; // one semitone step: a bend or a vibrato swing unless both pitches really hold
        }
        return dwell >= STEP_DWELL;
    }
    let lens: Vec<f64> = pl.iter().map(|p| len(p) as f64).collect();
    if py::median(&lens) > ALT_MAX_FRAMES {
        return false;
    }
    let mut held: Vec<(i64, usize)> = Vec::new();
    for p in pl {
        match held.iter_mut().find(|h| h.0 == p.2) {
            Some(h) => h.1 += len(p),
            None => held.push((p.2, len(p))),
        }
    }
    let total: usize = held.iter().map(|h| h.1).sum();
    if (held.iter().map(|h| h.1).min().unwrap() as f64) < MIN_SHARE * total as f64 {
        return false;
    }
    let span = sems.iter().max().unwrap() - sems.iter().min().unwrap();
    if span > ALT_MAX_SPAN {
        return false;
    }
    if span == 1 {
        // A long trill whose plateaus hold (a transit frame between them) needs less dwell.
        let long_trill = changes >= LONG_TRILL_CHANGES && dwell >= LONG_TRILL_DWELL && py::median(&lens) >= LONG_TRILL_FRAMES;
        return long_trill || (dwell >= TRILL_DWELL && changes >= TRILL_CHANGES);
    }
    dwell >= DWELL
}

/// The plateaus without a glide at either end: a chain of short plateaus next to a held one, moving one way by
/// at most GLIDE_STEP a step, by semitones or holding still for under GLIDE_CHAIN_DWELL of its span.
fn without_glides(pl: &[Plateau]) -> Vec<Plateau> {
    let mut pl = pl.to_vec();
    for _ in 0..2 {
        let mut k = pl.len();
        while k > 0 && len(&pl[k - 1]) <= GLIDE_FRAMES {
            k -= 1;
        }
        if 0 < k && k < pl.len() && len(&pl[k - 1]) > 2 * GLIDE_FRAMES {
            let steps: Vec<i64> = pl[k - 1..].windows(2).map(|w| w[1].2 - w[0].2).collect();
            let span = pl[pl.len() - 1].1 - pl[k].0;
            let dwell = pl[k..].iter().map(len).sum::<usize>() as f64 / span.max(1) as f64;
            let small = steps.iter().all(|&d| 0 < d.abs() && d.abs() <= GLIDE_STEP);
            let one_way = steps.iter().all(|&d| d > 0) || steps.iter().all(|&d| d < 0);
            if small && one_way && (steps.iter().all(|&d| d.abs() == 1) || dwell < GLIDE_CHAIN_DWELL) {
                pl.truncate(k);
            }
        }
        pl.reverse();
    }
    pl
}

fn frames(c: &Contour, on: f64, off: f64) -> (usize, usize) {
    (c.t.partition_point(|&v| v < on - FRAME / 2.0), c.t.partition_point(|&v| v < off - FRAME / 2.0))
}

fn tuned(c: &Contour, a: usize, b: usize, tau: f64) -> Vec<f64> {
    c.midi[a..b].iter().map(|m| m - tau).collect()
}

/// One SwiftF0 note as the notes its contour plateaus show (itself when they do not).
pub fn split_note(n: &RawNote, c: &Contour, tau: f64, ok: &[bool]) -> Vec<RawNote> {
    let (a, b) = frames(c, n.onset, n.offset);
    if b < a + 2 * MIN_RUN {
        return vec![n.clone()];
    }
    let pl = without_glides(&plateaus(&tuned(c, a, b, tau), &ok[a..b]));
    if !splits(&pl, b - a) {
        return vec![n.clone()];
    }
    let mut total: Vec<(i64, usize)> = Vec::new();
    for p in &pl {
        match total.iter_mut().find(|h| h.0 == p.2) {
            Some(h) => h.1 += len(p),
            None => total.push((p.2, len(p))),
        }
    }
    total.sort();
    let mut main = total[0];
    for &h in &total[1..] {
        if h.1 > main.1 {
            main = h;
        }
    }
    // Each piece is its plateau's own semitone; only an octave of difference from the tracker's label carries
    // over (SwiftF0 labels a collapsed alternation with a compromise pitch between the plateaus).
    let delta = 12 * ((n.pitch as i64 - main.0) as f64 / 12.0).round_ties_even() as i64;
    let mut out = vec![RawNote { pitch: (pl[0].2 + delta) as i32, split: true, ..n.clone() }];
    for w in pl.windows(2) {
        let (p0, p1) = (w[0], w[1]);
        if p1.2 == p0.2 {
            continue;
        }
        let on = (c.t[a + p0.1 - 1] + FRAME + c.t[a + p1.0]) / 2.0;
        out.last_mut().unwrap().offset = on;
        out.push(RawNote { pitch: (p1.2 + delta) as i32, onset: on, split: true, ..n.clone() });
    }
    out.last_mut().unwrap().offset = n.offset;
    out
}

/// Pitch slope (semitones per second) across a note: median of the last third of its voiced frames minus the
/// median of the first third, over two thirds of the voiced span; 0 with fewer than 4 voiced frames.
fn slope(n: &RawNote, c: &Contour, ok: &[bool]) -> f64 {
    let (a, b) = frames(c, n.onset, n.offset);
    let idx: Vec<usize> = (a..b).filter(|&i| ok[i]).collect();
    if idx.len() < 4 {
        return 0.0;
    }
    let k = idx.len() / 3;
    let head = py::median(&idx[..k].iter().map(|&i| c.midi[i]).collect::<Vec<f64>>());
    let tail = py::median(&idx[idx.len() - k..].iter().map(|&i| c.midi[i]).collect::<Vec<f64>>());
    let span = c.t[idx[idx.len() - 1]] - c.t[idx[0]];
    if span > 0.0 {
        (tail - head) / (span * 2.0 / 3.0)
    } else {
        0.0
    }
}

fn glide(n: &RawNote, c: &Contour, tau: f64, ok: &[bool], toward: Option<i64>) -> bool {
    if n.offset - n.onset >= GLIDE_MAX {
        return false;
    }
    let (a, b) = frames(c, n.onset, n.offset);
    if b <= a {
        return false;
    }
    let pl = plateaus(&tuned(c, a, b, tau), &ok[a..b]);
    toward.is_some_and(|d| {
        (pl.iter().map(len).sum::<usize>() as f64) / ((b - a) as f64) < GLIDE_DWELL && slope(n, c, ok) * d as f64 >= GLIDE_SLOPE
    })
}

fn confirmed(n: &RawNote, others: &[RawNote]) -> bool {
    others.iter().any(|o| o.pitch == n.pitch && (o.onset - n.onset).abs() <= CONFIRM_TOL)
}

/// Runs of >= 3 touching notes alternating by exactly 12 semitones: the notes in the other octave that no
/// other transcriber confirms fold into their neighbours.
pub fn octave_flips(notes: &[RawNote], others: &[RawNote]) -> Vec<RawNote> {
    let mut out = Vec::new();
    let mut i = 0;
    while i < notes.len() {
        let mut j = i;
        while j + 1 < notes.len() && (notes[j + 1].pitch - notes[j].pitch).abs() == 12 && notes[j + 1].onset - notes[j].offset <= GLIDE_GAP {
            j += 1;
        }
        let run = &notes[i..=j];
        if j - i < 2 || run.iter().all(|n| n.offset - n.onset >= FLIP_MAX) {
            out.extend_from_slice(run);
            i = j + 1;
            continue;
        }
        let mut held: Vec<(i32, f64)> = Vec::new();
        for n in run {
            match held.iter_mut().find(|h| h.0 == n.pitch) {
                Some(h) => h.1 += n.offset - n.onset,
                None => held.push((n.pitch, n.offset - n.onset)),
            }
        }
        // The octave nearer the notes around the run, else the one held longer.
        let around: Vec<i32> = [i.checked_sub(1), Some(j + 1)].into_iter().flatten().filter(|&k| k < notes.len()).map(|k| notes[k].pitch).collect();
        let key = |h: &(i32, f64)| (around.iter().map(|q| (h.0 - q).abs()).sum::<i32>(), -h.1, h.0);
        let mut best = held[0];
        for &h in &held[1..] {
            let (a, b) = (key(&h), key(&best));
            if a.0 < b.0 || (a.0 == b.0 && (a.1 < b.1 || (a.1 == b.1 && a.2 < b.2))) {
                best = h;
            }
        }
        let pitch = best.0;
        let mut folded: Vec<RawNote> = Vec::new();
        for n in run {
            let keep = n.pitch == pitch || confirmed(n, others);
            if !keep && !folded.is_empty() {
                folded.last_mut().unwrap().offset = n.offset;
            } else if keep && folded.last().is_some_and(|l| l.pitch == n.pitch) && !confirmed(n, others) {
                folded.last_mut().unwrap().offset = n.offset;
            } else {
                folded.push(if keep { n.clone() } else { RawNote { pitch, ..n.clone() } });
            }
        }
        out.extend(folded);
        i = j + 1;
    }
    out
}

/// SwiftF0 notes (one voice, sorted by onset) with the contour's pitch-change onsets, without octave flips
/// and glides.
pub fn contour_notes(notes: &[RawNote], c: Option<&Contour>, others: &[RawNote]) -> Vec<RawNote> {
    let Some(c) = c else { return notes.to_vec() };
    if notes.is_empty() {
        return Vec::new();
    }
    let notes = octave_flips(notes, others);
    let ok = voiced(c);
    let tau = tuning(&c.midi, &ok);
    let mut kept: Vec<RawNote> = Vec::new();
    let mut carry: Option<f64> = None;
    for (i, n) in notes.iter().enumerate() {
        let prev_end = if i > 0 { notes[i - 1].offset } else { -1.0 };
        let next_on = if i + 1 < notes.len() { notes[i + 1].onset } else { f64::INFINITY };
        let touch_prev = n.onset - prev_end <= GLIDE_GAP;
        let touch_next = next_on - n.offset <= GLIDE_GAP;
        let toward = if touch_next {
            (notes[i + 1].pitch - n.pitch).signum() as i64
        } else if touch_prev {
            (n.pitch - notes[i - 1].pitch).signum() as i64
        } else {
            0
        };
        if (touch_prev || touch_next) && glide(n, c, tau, &ok, if toward != 0 { Some(toward) } else { None }) {
            if touch_next {
                carry = carry.or(Some(n.onset));
            } else if let Some(last) = kept.last_mut() {
                last.offset = n.offset;
            }
            continue;
        }
        kept.push(RawNote { onset: carry.unwrap_or(n.onset), ..n.clone() });
        carry = None;
    }
    kept.iter().flat_map(|n| split_note(n, c, tau, &ok)).collect()
}
