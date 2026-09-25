//! Loudness envelopes of layers: gate transcribed notes, and read dynamics.
//!
//! A transcriber run on a separated stem or a residual also "hears" bleed and
//! silence; `gate` drops notes whose layer is far under its loud level at the
//! onset. Computation follows the reference in float32.

use crate::midi::RawNote;

pub const HOP: f64 = 0.01;
/// Notes starting more than this far under the layer's loud level are dropped.
pub const GATE_DB: f64 = 30.0;
/// Seconds after the onset in which the layer must reach the level.
pub const ONSET_WINDOW: f64 = 0.06;

/// Audio as read from a file: interleaved float32 samples.
#[derive(Debug, Clone, PartialEq)]
pub struct Audio {
    pub samples: Vec<f32>,
    pub channels: usize,
    pub sample_rate: u32,
}

impl Audio {
    pub fn frames(&self) -> usize {
        self.samples.len() / self.channels.max(1)
    }

    /// Mean over channels (float32, as the reference averages).
    pub fn mono(&self) -> Vec<f32> {
        let c = self.channels.max(1);
        if c == 1 {
            return self.samples.clone();
        }
        self.samples
            .chunks_exact(c)
            .map(|f| {
                let s: f32 = crate::py::pairwise_sum_f32(f);
                s / c as f32
            })
            .collect()
    }
}

/// k-th smallest of a float slice.
fn kth(v: &[f32], k: usize) -> f32 {
    let mut s = v.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    s[k]
}

/// `np.percentile(x, q)` (linear) of a float32 array, as float32.
pub fn percentile_f32(x: &[f32], q: f64) -> f32 {
    let n = x.len();
    let virt = (n as f64 - 1.0) * (q / 100.0);
    if virt >= n as f64 - 1.0 {
        return kth(x, n - 1);
    }
    let prev = virt.floor();
    let gamma = virt - prev;
    let mut s = x.to_vec();
    s.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let (a, b) = (s[prev as usize], s[prev as usize + 1]);
    let d = b - a;
    if gamma >= 0.5 {
        b - d * ((1.0 - gamma) as f32)
    } else {
        a + d * (gamma as f32)
    }
}

/// Python slice `v[a:b]` with negative indices and clamping.
pub fn py_slice<T>(v: &[T], a: i64, b: i64) -> &[T] {
    let n = v.len() as i64;
    let norm = |i: i64| -> i64 {
        let i = if i < 0 { i + n } else { i };
        i.clamp(0, n)
    };
    let (a, b) = (norm(a), norm(b));
    if a >= b {
        &v[0..0]
    } else {
        &v[a as usize..b as usize]
    }
}

/// RMS level in dB per HOP seconds, and the layer's loud reference level (95th percentile).
#[derive(Debug, Clone, PartialEq)]
pub struct Envelope {
    pub db: Vec<f32>,
    pub reference: f32,
}

impl Envelope {
    pub fn of(audio: &Audio) -> Envelope {
        let y = audio.mono();
        let hop = ((HOP * audio.sample_rate as f64) as usize).max(1);
        let n = y.len() / hop;
        let rms: Vec<f32> = if n > 0 {
            y[..n * hop]
                .chunks_exact(hop)
                .map(|c| {
                    let sq: Vec<f32> = c.iter().map(|v| v * v).collect();
                    ((crate::py::pairwise_sum_f32(&sq) as f64 / hop as f64) as f32).sqrt()
                })
                .collect()
        } else {
            vec![0.0]
        };
        let db: Vec<f32> = rms.iter().map(|r| 20.0f32 * (r + 1e-9f32).log10()).collect();
        let reference = percentile_f32(&db, 95.0);
        Envelope { db, reference }
    }

    /// Peak level in [t, t + window), relative to the reference (dB).
    pub fn level_at(&self, t: f64, window: f64) -> f64 {
        let a = (t / HOP) as i64;
        let b = (a + 1).max(((t + window) / HOP) as i64);
        let seg = py_slice(&self.db, a, b);
        if seg.is_empty() {
            return -120.0;
        }
        let m = seg.iter().cloned().fold(f32::NEG_INFINITY, f32::max);
        (m - self.reference) as f64
    }

    /// Mean power level in [t0, t1) relative to the reference (dB).
    pub fn mean_level(&self, t0: f64, t1: f64) -> f64 {
        let a = (t0 / HOP) as i64;
        let seg = py_slice(&self.db, a, (a + 1).max((t1 / HOP) as i64));
        if seg.is_empty() {
            return -120.0;
        }
        let p: Vec<f32> = seg.iter().map(|d| 10f32.powf(d / 10.0)).collect();
        // np.mean divides by the count in float64 and stores float32
        let mean = (crate::py::pairwise_sum_f32(&p) as f64 / p.len() as f64) as f32;
        (10.0f32 * mean.log10() - self.reference) as f64
    }
}

/// Notes whose layer reaches the level at their onset, and how many were dropped.
pub fn gate(notes: Vec<RawNote>, env: &Envelope, gate_db: f64) -> (Vec<RawNote>, usize) {
    let n = notes.len();
    let kept: Vec<RawNote> = notes.into_iter().filter(|x| env.level_at(x.onset, ONSET_WINDOW) >= -gate_db).collect();
    let dropped = n - kept.len();
    (kept, dropped)
}
