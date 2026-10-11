//! Rehearsal marks at section boundaries, from changes in the layers' energy.
//!
//! Each bar has a feature vector: the level of every layer (dB relative to the
//! layer's loud level, silence floored). A boundary is where the mean of the next
//! `SPAN` bars differs most from the mean of the previous `SPAN` bars. Boundaries
//! are picked greedily by that novelty, at least `MIN_GAP` bars apart; a gap
//! longer than `MAX_GAP` bars gets its best boundary as well; the end of a
//! free-time passage is always one. Letters run A, B, C... (no I).

use crate::dynamics::Bar;
use crate::energy::Envelope;

pub const SPAN: usize = 4;
pub const MIN_GAP: i64 = 8;
pub const MAX_GAP: i64 = 24;
pub const FLOOR_DB: f64 = -45.0;
/// dB (Euclidean over layers): smaller changes are not a new section.
pub const MIN_NOVELTY: f64 = 6.0;

pub fn bar_features(envs: &[&Envelope], bars: &[Bar]) -> Vec<Vec<f64>> {
    bars.iter().map(|&(_, t0, t1)| envs.iter().map(|e| FLOOR_DB.max(e.mean_level(t0, t1))).collect()).collect()
}

/// Euclidean norm with the summation order of the reference's BLAS dot product.
fn norm(x: &[f64]) -> f64 {
    let p: Vec<f64> = x.iter().map(|v| v * v).collect();
    let s = if p.len() == 4 {
        (p[0] + p[2]) + (p[1] + p[3])
    } else {
        p.iter().fold(0.0, |a, b| a + b)
    };
    s.sqrt()
}

pub fn novelty(features: &[Vec<f64>], span: usize) -> Vec<f64> {
    let n = features.len();
    let mut out = vec![0.0; n];
    if n == 0 {
        return out;
    }
    let m = features[0].len();
    let mean = |rows: &[Vec<f64>]| -> Vec<f64> {
        let mut acc = vec![0.0; m];
        for r in rows {
            for j in 0..m {
                acc[j] += r[j];
            }
        }
        acc.iter().map(|v| v / rows.len() as f64).collect()
    };
    if n + 1 < span * 2 {
        return out;
    }
    for b in span..(n + 1).saturating_sub(span) {
        let after = mean(&features[b..b + span]);
        let before = mean(&features[b - span..b]);
        let d: Vec<f64> = after.iter().zip(before.iter()).map(|(a, c)| a - c).collect();
        out[b] = norm(&d);
    }
    out
}

/// Bar indices where rehearsal marks go (sorted; bar 0 gets none).
pub fn section_starts(features: &[Vec<f64>], forced: &[i64]) -> Vec<i64> {
    let nov = novelty(features, SPAN);
    let n = nov.len() as i64;
    let mut chosen: Vec<i64> = forced.iter().copied().filter(|&b| 0 < b && b < n).collect();
    chosen.sort();
    chosen.dedup();
    let neg: Vec<f64> = nov.iter().map(|v| -v).collect();
    for b in crate::py::np_argsort(&neg) {
        if nov[b] < MIN_NOVELTY {
            break;
        }
        let b = b as i64;
        let free = chosen.iter().all(|&c| (b - c).abs() >= MIN_GAP) && b >= MIN_GAP / 2 && b <= n - MIN_GAP / 2;
        if free {
            chosen.push(b);
            chosen.sort();
        }
    }
    loop {
        let mut edges = vec![0];
        let mut sorted = chosen.clone();
        sorted.sort();
        edges.extend(sorted);
        edges.push(n);
        let mut changed = false;
        for w in edges.windows(2) {
            let (a, z) = (w[0], w[1]);
            let lo = a + MIN_GAP;
            let hi = z - MIN_GAP + 1;
            if z - a > MAX_GAP && lo < hi {
                // first maximum
                let mut best = lo;
                for b in lo..hi {
                    if nov[b as usize] > nov[best as usize] {
                        best = b;
                    }
                }
                chosen.push(best);
                changed = true;
                break;
            }
        }
        if !changed {
            break;
        }
    }
    chosen.sort();
    chosen.dedup();
    chosen
}

pub fn letters(n: usize) -> Vec<String> {
    let abc: Vec<char> = ('A'..='Z').filter(|&c| c != 'I').collect();
    let l = abc.len();
    (0..n)
        .map(|i| if i < l { abc[i].to_string() } else { format!("{}{}", abc[i / l - 1], abc[i % l]) })
        .collect()
}
