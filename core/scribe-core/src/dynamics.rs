//! Dynamics per layer from its loudness.
//!
//! Each layer's level per bar (relative to the layer's own loud level) is
//! mapped to a marking, smoothed over three bars, and a new marking is only
//! written when it holds for `MIN_HOLD` bars.

use crate::energy::Envelope;
use crate::py;

/// Upper edge (dB relative to the layer's loud level) of each marking, softest first.
pub const MARKS: [(&str, f64); 6] = [("pp", -30.0), ("p", -22.0), ("mp", -15.0), ("mf", -9.0), ("f", -4.0), ("ff", 99.0)];
pub const MIN_HOLD: usize = 4;
/// A bar this quiet has no dynamic of its own (the layer rests).
pub const SILENT_DB: f64 = -45.0;

pub fn mark_of(level_db: f64) -> &'static str {
    MARKS.iter().find(|(_, hi)| level_db < *hi).map(|(m, _)| *m).unwrap_or("ff")
}

/// A bar: (start tick, start s, end s).
pub type Bar = (i64, f64, f64);

/// (tick, marking) changes for one layer.
pub fn layer_dynamics(env: &Envelope, bars: &[Bar]) -> Vec<(i64, String)> {
    let levels: Vec<f64> = bars.iter().map(|&(_, t0, t1)| env.mean_level(t0, t1)).collect();
    let active: Vec<bool> = levels.iter().map(|&l| l > SILENT_DB).collect();
    let n = bars.len();
    let mut marks: Vec<Option<&str>> = Vec::with_capacity(n);
    for i in 0..n {
        let win: Vec<f64> = (i.saturating_sub(1)..n.min(i + 2)).filter(|&j| active[j]).map(|j| levels[j]).collect();
        marks.push(if active[i] && !win.is_empty() { Some(mark_of(py::median(&win))) } else { None });
    }
    let mut out = Vec::new();
    let mut current: Option<&str> = None;
    let mut i = 0;
    while i < n {
        let m = marks[i];
        if m.is_none() || m == current {
            i += 1;
            continue;
        }
        let mut run = 1;
        while i + run < n && (marks[i + run] == m || marks[i + run].is_none()) {
            run += 1;
        }
        if current.is_none() || run >= MIN_HOLD {
            out.push((bars[i].0, m.unwrap().to_string()));
            current = m;
        }
        i += 1;
    }
    out
}
