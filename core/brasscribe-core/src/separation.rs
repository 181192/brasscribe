//! Separation-failure check: does a separated solo stem contain the soloist?
//!
//! When the separator misses the soloist, the stem is left near-silent and a
//! transcriber still returns a few notes. The check flags a stem more than
//! `FAIL_DB` under the mix overall, and lists the windows where the mix plays
//! but the stem is that quiet.

use serde_json::{json, Value};

use crate::py;

pub const FAIL_DB: f64 = 25.0;
pub const WINDOW: f64 = 10.0;
/// A mix window within this of the mix's loud level is playing.
pub const ACTIVE_DB: f64 = 30.0;

fn rms_db(y: &[f32]) -> f64 {
    let sq: Vec<f64> = y.iter().map(|&v| (v as f64) * (v as f64)).collect();
    let mean = py::pairwise_sum_f64(&sq) / sq.len() as f64;
    20.0 * (mean.sqrt() + 1e-9).log10()
}

#[derive(Debug, Clone, PartialEq)]
pub struct SeparationCheck {
    pub stem_minus_mix_db: f64,
    pub failed: bool,
    /// (start s, end s, stem - mix dB)
    pub quiet_windows: Vec<(f64, f64, f64)>,
}

impl SeparationCheck {
    /// The `separation-check.json` text the reference writes (compact `json.dumps`).
    pub fn to_json_string(&self) -> String {
        let v = json!({
            "stem_minus_mix_db": self.stem_minus_mix_db,
            "failed": self.failed,
            "quiet_windows": self.quiet_windows.iter().map(|(a, b, d)| json!([a, b, d])).collect::<Vec<Value>>(),
        });
        crate::pyjson::dumps_compact(&v)
    }
}

/// Compare a mono stem with its mono mix (same sample rate).
pub fn check_stem(stem: &[f32], mix: &[f32], sr: u32, fail_db: f64) -> SeparationCheck {
    let n = stem.len().min(mix.len());
    let (s, m) = (&stem[..n], &mix[..n]);
    let overall = rms_db(s) - rms_db(m);
    let w = (WINDOW * sr as f64) as usize;
    let mut levels = Vec::new();
    let mut i = 0;
    while i < n {
        let e = (i + w).min(n);
        levels.push((i as f64 / sr as f64, e as f64 / sr as f64, rms_db(&m[i..e]), rms_db(&s[i..e])));
        i += w;
    }
    let loud = levels.iter().map(|l| l.2).fold(f64::NEG_INFINITY, f64::max);
    let loud = if levels.is_empty() { -120.0 } else { loud };
    let quiet = levels
        .iter()
        .filter(|(_, _, lm, ls)| *lm >= loud - ACTIVE_DB && ls - lm < -fail_db)
        .map(|(a, b, lm, ls)| (*a, *b, py::py_round(ls - lm, 1)))
        .collect();
    SeparationCheck { stem_minus_mix_db: py::py_round(overall, 2), failed: overall < -fail_db, quiet_windows: quiet }
}
