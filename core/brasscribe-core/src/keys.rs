//! Key signatures per passage: key changes where the music modulates, and the mode.
//!
//! Each bar gets a cost per key signature, the share of its note duration
//! outside that signature's scale; a Viterbi pass picks one signature per bar
//! with a penalty per change. The mode names the estimated tonic as a degree
//! of the signature's scale (a C-signature passage in F is F lydian).

use crate::model::{KeySig, Note};
use crate::py;
use crate::spelling::key_of;

pub const FIFTHS: std::ops::RangeInclusive<i32> = -5..=5;
/// In bars of fully out-of-key music.
pub const CHANGE_PENALTY: f64 = 0.5;
pub const MIN_BAR_WEIGHT: f64 = 1e-6;

fn mode_of_degree(d: i64) -> Option<&'static str> {
    Some(match d {
        0 => "major",
        2 => "dorian",
        4 => "phrygian",
        5 => "lydian",
        7 => "mixolydian",
        9 => "minor",
        11 => "locrian",
        _ => return None,
    })
}

pub fn scale(fifths: i32) -> [i64; 7] {
    let tonic = py::pymod(7 * fifths as i64, 12);
    let mut out = [0i64; 7];
    for (k, s) in [0, 2, 4, 5, 7, 9, 11].iter().enumerate() {
        out[k] = (tonic + s) % 12;
    }
    out
}

fn tonic_pc(name: &str) -> i64 {
    match name {
        "C" => 0,
        "C#" | "Db" => 1,
        "D" => 2,
        "Eb" | "D#" => 3,
        "E" => 4,
        "F" => 5,
        "F#" | "Gb" => 6,
        "G" => 7,
        "Ab" | "G#" => 8,
        "A" => 9,
        "Bb" | "A#" => 10,
        "B" | "Cb" => 11,
        _ => 0,
    }
}

/// (mode name, tonic pitch class): the Krumhansl-Kessler tonic as a mode of the signature's scale.
pub fn mode(notes: &[&Note], fifths: i32) -> (&'static str, i64) {
    if notes.is_empty() {
        return ("major", py::pymod(7 * fifths as i64, 12));
    }
    let du: Vec<f64> = notes.iter().map(|n| n.dur as f64 / 24.0).collect();
    let ps: Vec<i32> = notes.iter().map(|n| n.pitch).collect();
    let (name, _) = key_of(&du, &ps);
    let tonic = tonic_pc(name.trim_end_matches('m'));
    let degree = py::pymod(tonic - 7 * fifths as i64, 12);
    match mode_of_degree(degree) {
        Some(m) => (m, tonic),
        None if name.ends_with('m') => ("minor", py::pymod(7 * fifths as i64 + 9, 12)),
        None => ("major", py::pymod(7 * fifths as i64, 12)),
    }
}

#[derive(Debug, Clone, PartialEq)]
pub struct KeyPlan {
    pub keys: Vec<KeySig>,
    /// Fifths per bar.
    pub per_bar: Vec<i32>,
}

/// Key signatures (at bar starts) for concert-pitch notes; tick 0 is a bar line.
pub fn key_plan(notes: &[Note], bar: i64, penalty: f64, bass: &[Note]) -> KeyPlan {
    let notes: Vec<&Note> = notes.iter().filter(|n| n.start >= 0).collect();
    if notes.is_empty() {
        return KeyPlan { keys: vec![KeySig { tick: 0, fifths: 0, mode: "major".into() }], per_bar: Vec::new() };
    }
    let fifths: Vec<i32> = FIFTHS.collect();
    let k = fifths.len();
    let n_bars = (notes.iter().map(|n| n.start).max().unwrap() / bar + 1) as usize;
    // weights per bar per pitch class, in insertion order (integer sums)
    let mut weights: Vec<Vec<(i64, i64)>> = vec![Vec::new(); n_bars];
    for n in &notes {
        let b = py::floordiv(n.start, bar);
        if 0 <= b && (b as usize) < n_bars {
            let pc = py::pymod(n.pitch as i64, 12);
            let w = &mut weights[b as usize];
            match w.iter_mut().find(|(p, _)| *p == pc) {
                Some(e) => e.1 += n.dur,
                None => w.push((pc, n.dur)),
            }
        }
    }
    let mut cost = vec![vec![0.0f64; k]; n_bars];
    for (b, w) in weights.iter().enumerate() {
        let total: i64 = w.iter().map(|x| x.1).sum();
        if (total as f64) < MIN_BAR_WEIGHT {
            continue;
        }
        for (j, &f) in fifths.iter().enumerate() {
            let sc = scale(f);
            let out: i64 = w.iter().filter(|(pc, _)| !sc.contains(pc)).map(|x| x.1).sum();
            cost[b][j] = out as f64 / total as f64;
        }
    }
    for row in cost.iter_mut() {
        for (j, &f) in fifths.iter().enumerate() {
            row[j] += 1e-3 * f.abs() as f64;
        }
    }
    let argmin = |v: &[f64]| -> usize {
        let mut best = 0;
        for i in 1..v.len() {
            if v[i] < v[best] {
                best = i;
            }
        }
        best
    };
    let mut acc = cost[0].clone();
    let mut back = vec![vec![0usize; k]; n_bars];
    for b in 1..n_bars {
        let amin = argmin(&acc);
        let mv = acc[amin] + penalty;
        let mut next = vec![0.0; k];
        for j in 0..k {
            let choose_move = mv < acc[j];
            back[b][j] = if choose_move { amin } else { j };
            next[j] = acc[j].min(mv) + cost[b][j];
        }
        acc = next;
    }
    let mut path = vec![argmin(&acc)];
    for b in (1..n_bars).rev() {
        let last = *path.last().unwrap();
        path.push(back[b][last]);
    }
    path.reverse();
    let per_bar: Vec<i32> = path.iter().map(|&j| fifths[j]).collect();
    let mut keys: Vec<KeySig> = Vec::new();
    for (b, &f) in per_bar.iter().enumerate() {
        if keys.last().map_or(true, |k| k.fifths != f) {
            let seg_end = (b..n_bars).find(|&e| per_bar[e] != f).unwrap_or(n_bars) as i64;
            let (lo, hi) = (b as i64 * bar, seg_end * bar);
            let seg: Vec<&Note> = notes.iter().copied().chain(bass.iter()).filter(|n| lo <= n.start && n.start < hi).collect();
            let (m, _) = mode(&seg, f);
            keys.push(KeySig { tick: b as i64 * bar, fifths: f, mode: m.into() });
        }
    }
    KeyPlan { keys, per_bar }
}
