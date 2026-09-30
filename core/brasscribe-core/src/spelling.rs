//! Pitch spelling (Meredith's ps13, variant ps13s1 with K_pre=10, K_post=40)
//! and Krumhansl-Kessler key estimation, on concert-pitch notes.
//!
//! This follows partitura's implementation (the reference's spelling
//! backend) step for step, including its float32 note arrays, followed by the
//! reference's rewrite of double accidentals.

use crate::py;

#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
pub struct Spelled {
    /// 'A'..'G'
    pub step: char,
    pub alter: i32,
    pub octave: i32,
}

const PS_STEPS: [char; 7] = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
const UND_CHROMA: [i64; 7] = [0, 2, 3, 5, 7, 8, 10];
const K_PRE: usize = 10;
const K_POST: usize = 40;

/// ps13s1 on notes given in (onset, pitch) order; returns spellings in that order.
fn ps13s1_sorted(pitches: &[i32]) -> Vec<Spelled> {
    let n = pitches.len();
    let cp: Vec<i64> = pitches.iter().map(|&p| p as i64 - 21).collect();
    let chroma: Vec<usize> = cp.iter().map(|&c| c.rem_euclid(12) as usize).collect();

    // chroma frequency in the window [i - K_pre, i + K_post)
    let mut cv = [0i64; 12];
    for &c in chroma.iter().take(n.min(K_POST)) {
        cv[c] += 1;
    }
    let mut cva: Vec<[i64; 12]> = Vec::with_capacity(n);
    cva.push(cv);
    for i in 1..n {
        if i + K_POST <= n {
            cv[chroma[i + K_POST - 1]] += 1;
        }
        if i > K_PRE {
            cv[chroma[i - K_PRE - 1]] -= 1;
        }
        cva.push(cv);
    }

    const INIT_MORPH: [i64; 12] = [0, 1, 1, 2, 2, 3, 4, 4, 5, 5, 6, 6];
    const MORPH_INT: [i64; 12] = [0, 1, 1, 2, 2, 3, 3, 4, 5, 5, 6, 6];
    let c0 = chroma[0] as i64;
    let m0 = INIT_MORPH[c0 as usize];
    let tonic_morph: Vec<i64> = (0..12i64).map(|t| (m0 - MORPH_INT[(c0 - t).rem_euclid(12) as usize]).rem_euclid(7)).collect();
    let mut morph = vec![0i64; n];
    for j in 0..n {
        let mut strength = [0i64; 7];
        for ct in 0..12usize {
            let m = (MORPH_INT[(chroma[j] as i64 - ct as i64).rem_euclid(12) as usize] + tonic_morph[ct]).rem_euclid(7);
            strength[m as usize] += cva[j][ct];
        }
        // argmax: first maximum
        let mut best = 0;
        for m in 1..7 {
            if strength[m] > strength[best] {
                best = m;
            }
        }
        morph[j] = best as i64;
    }

    // morphetic pitch: octave choice nearest the chromatic position
    let mut out = Vec::with_capacity(n);
    for j in 0..n {
        let c = cp[j] as f64;
        let o1 = (c / 12.0).floor() as i64;
        let octs = [o1, o1 + 1, o1 - 1];
        let ch = c.rem_euclid(12.0);
        let cpos = o1 as f64 + ch / 12.0;
        let mf = morph[j] as f64 / 7.0;
        let mut bi = 0;
        let mut bd = f64::INFINITY;
        for (k, &o) in octs.iter().enumerate() {
            let d = (cpos - (o as f64 + mf)).abs();
            if d < bd {
                bd = d;
                bi = k;
            }
        }
        let mp = morph[j] + 7 * octs[bi];
        // chromamorphetic pitch -> name
        let mm = mp.rem_euclid(7) as usize;
        let fl = py::floordiv(mp, 7);
        let alter = cp[j] - 12 * fl - UND_CHROMA[mm];
        let octave = fl + if mm > 1 { 1 } else { 0 };
        out.push(Spelled { step: PS_STEPS[mm], alter: alter as i32, octave: octave as i32 });
    }
    out
}

const NATURAL: [(char, i32); 7] = [('C', 0), ('D', 2), ('E', 4), ('F', 5), ('G', 7), ('A', 9), ('B', 11)];

/// Rewrite double sharps/flats (ps13 emits them in dense chromatic runs) as a single accidental.
fn simplify(s: Spelled, midi: i32) -> Spelled {
    if s.alter.abs() < 2 {
        return s;
    }
    let pc = midi.rem_euclid(12);
    let same_side = if s.alter > 0 { 1 } else { -1 };
    for a in [same_side, 0, -same_side] {
        for (st, base) in NATURAL {
            if (base + a).rem_euclid(12) == pc {
                return Spelled { step: st, alter: a, octave: py::floordiv((midi - a) as i64, 12) as i32 - 1 };
            }
        }
    }
    s
}

/// (step, alter, octave) per note, in input order.
///
/// Notes are ordered by onset (stable) and, within an onset, by pitch, as the
/// reference does before running ps13.
pub fn spell(onsets_beats: &[f64], pitches: &[i32]) -> Vec<Spelled> {
    let n = pitches.len();
    if n == 0 {
        return Vec::new();
    }
    // order = argsort(onsets, stable); then ps13 sorts by pitch and (stably) by float32 onset
    let mut order: Vec<usize> = (0..n).collect();
    order.sort_by(|&a, &b| onsets_beats[a].partial_cmp(&onsets_beats[b]).unwrap());
    let on32: Vec<f32> = order.iter().map(|&i| onsets_beats[i] as f32).collect();
    let ps: Vec<i32> = order.iter().map(|&i| pitches[i]).collect();
    // NumPy's default argsort (unstable) by pitch, then a stable sort by onset:
    // equal (onset, pitch) notes of different parts keep NumPy's order.
    let mut idx: Vec<usize> = crate::py::np_argsort(&ps);
    idx.sort_by(|&a, &b| on32[a].partial_cmp(&on32[b]).unwrap());
    let sorted_pitches: Vec<i32> = idx.iter().map(|&k| ps[k]).collect();
    let sp = ps13s1_sorted(&sorted_pitches);
    let mut by_k = vec![Spelled { step: 'C', alter: 0, octave: 4 }; n];
    for (pos, &k) in idx.iter().enumerate() {
        by_k[k] = sp[pos];
    }
    let mut out = vec![Spelled { step: 'C', alter: 0, octave: 4 }; n];
    for (k, &i) in order.iter().enumerate() {
        out[i] = simplify(by_k[k], pitches[i]);
    }
    out
}

const KEYS: [(&str, bool); 24] = [
    ("C", true), ("Db", true), ("D", true), ("Eb", true), ("E", true), ("F", true), ("F#", true), ("G", true),
    ("Ab", true), ("A", true), ("Bb", true), ("B", true), ("C", false), ("C#", false), ("D", false), ("D#", false),
    ("E", false), ("F", false), ("F#", false), ("G", false), ("G#", false), ("A", false), ("Bb", false), ("B", false),
];
const KK_MAJOR: [f64; 12] = [6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88];
const KK_MINOR: [f64; 12] = [6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17];

fn corr(x: &[f64; 12], y: &[f64; 12]) -> f64 {
    let mx = py::pairwise_sum_f64(x) / 12.0;
    let my = py::pairwise_sum_f64(y) / 12.0;
    let dx: Vec<f64> = x.iter().map(|v| v - mx).collect();
    let dy: Vec<f64> = y.iter().map(|v| v - my).collect();
    let mut sxy = 0.0;
    let mut sxx = 0.0;
    let mut syy = 0.0;
    for i in 0..12 {
        sxy += dx[i] * dy[i];
        sxx += dx[i] * dx[i];
        syy += dy[i] * dy[i];
    }
    let f = 1.0 / 11.0;
    let (cxy, cxx, cyy) = (sxy * f, sxx * f, syy * f);
    let c = cxy / cxx.sqrt() / cyy.sqrt();
    c.clamp(-1.0, 1.0)
}

/// Key name like "F" or "Dm" from Krumhansl-Kessler profile correlation.
pub fn estimate_key(durations_beats: &[f64], pitches: &[i32]) -> &'static str {
    let dur32: Vec<f32> = durations_beats.iter().map(|&d| d.max(1e-3) as f32).collect();
    let mut dist = [0.0f64; 12];
    for (pc, slot) in dist.iter_mut().enumerate() {
        let sel: Vec<f32> = pitches.iter().zip(dur32.iter()).filter(|(p, _)| p.rem_euclid(12) as usize == pc).map(|(_, d)| *d).collect();
        *slot = py::pairwise_sum_f32(&sel) as f64;
    }
    let norm = |p: &[f64; 12]| -> [f64; 12] {
        let s = py::pairwise_sum_f64(p);
        let mut o = [0.0; 12];
        for i in 0..12 {
            o[i] = p[i] / s;
        }
        o
    };
    let maj = norm(&KK_MAJOR);
    let min = norm(&KK_MINOR);
    let mut best = 0;
    let mut best_c = f64::NEG_INFINITY;
    for k in 0..24 {
        let base = if k < 12 { &maj } else { &min };
        let tonic = k % 12;
        let mut prof = [0.0; 12];
        for j in 0..12 {
            prof[j] = base[(j + 12 - tonic) % 12];
        }
        let c = corr(&dist, &prof);
        if c > best_c || (best_c.is_nan() && !c.is_nan()) {
            best_c = c;
            best = k;
        }
    }
    let (root, major) = KEYS[best];
    if major {
        root
    } else {
        match root {
            "C" => "Cm",
            "C#" => "C#m",
            "D" => "Dm",
            "D#" => "D#m",
            "E" => "Em",
            "F" => "Fm",
            "F#" => "F#m",
            "G" => "Gm",
            "G#" => "G#m",
            "A" => "Am",
            "Bb" => "Bbm",
            _ => "Bm",
        }
    }
}

/// Fifths for a key name (minor keys three fifths below their tonic's major).
pub fn fifths(name: &str) -> i32 {
    let major = |n: &str| -> i32 {
        match n {
            "C" => 0, "G" => 1, "D" => 2, "A" => 3, "E" => 4, "B" => 5, "F#" => 6, "C#" => 7, "F" => -1, "Bb" => -2,
            "Eb" => -3, "Ab" => -4, "Db" => -5, "Gb" => -6, "Cb" => -7, _ => 0,
        }
    };
    match name.strip_suffix('m') {
        // G#, D# and A# minor: the major table has no G#, D# or A# (they are Ab, Eb and Bb there).
        Some("G#") => 5,
        Some("D#") => 6,
        Some("A#") => 7,
        Some(root) => major(root) - 3,
        None => major(name),
    }
}

/// (name, fifths) of the estimated key. Onsets do not affect the estimate.
pub fn key_of(durations_beats: &[f64], pitches: &[i32]) -> (&'static str, i32) {
    let name = estimate_key(durations_beats, pitches);
    (name, fifths(name))
}

pub fn name(step: char, alter: i32, octave: i32) -> String {
    let acc = if alter > 0 { "#".repeat(alter as usize) } else { "b".repeat((-alter) as usize) };
    format!("{step}{acc}{octave}")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sharp_minor_keys_get_their_sharps() {
        assert_eq!([fifths("G#m"), fifths("D#m"), fifths("C#m"), fifths("Bbm"), fifths("Am")], [5, 6, 4, -5, 0]);
        // G# harmonic minor up, then the tonic triad
        let tonic = 68;
        let mut ps: Vec<i32> = [0, 2, 3, 5, 7, 8, 11, 12, 7, 3, 0].iter().map(|i| tonic + i).collect();
        ps.extend([tonic - 12, tonic + 3, tonic + 7].repeat(3));
        let mut du = vec![1.0; ps.len()];
        du[0] = 4.0;
        assert_eq!(key_of(&du, &ps), ("G#m", 5));
    }
}
