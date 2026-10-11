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
    /// WAV (PCM 16/24/32-bit or float32) as float32 samples scaled like libsndfile.
    pub fn from_wav(b: &[u8]) -> Result<Audio, String> {
        if b.len() < 12 || &b[0..4] != b"RIFF" || &b[8..12] != b"WAVE" {
            return Err("not a RIFF/WAVE file".into());
        }
        let u16le = |b: &[u8], i: usize| u16::from_le_bytes([b[i], b[i + 1]]);
        let u32le = |b: &[u8], i: usize| u32::from_le_bytes([b[i], b[i + 1], b[i + 2], b[i + 3]]);
        let mut i = 12usize;
        let (mut fmt, mut channels, mut rate, mut bits) = (0u16, 0usize, 0u32, 0u16);
        let mut data: Option<&[u8]> = None;
        while b.len() - i >= 8 {
            let id = &b[i..i + 4];
            let len = u32le(b, i + 4) as usize;
            // A chunk claiming more bytes than the file has ends at the end of the file.
            let body = &b[i + 8..i + 8 + len.min(b.len() - i - 8)];
            if id == b"fmt " {
                if body.len() < 16 {
                    return Err("WAV fmt chunk is too short".into());
                }
                fmt = u16le(body, 0);
                channels = u16le(body, 2) as usize;
                rate = u32le(body, 4);
                bits = u16le(body, 14);
                if fmt == 0xFFFE {
                    if body.len() < 26 {
                        return Err("WAV fmt chunk is too short".into());
                    }
                    fmt = u16le(body, 24); // sub-format GUID starts with the format code
                }
            } else if id == b"data" {
                data = Some(body);
            }
            match len.checked_add(8 + (len & 1)).and_then(|n| n.checked_add(i)) {
                Some(next) if next <= b.len() => i = next,
                _ => break,
            }
        }
        let data = data.ok_or("no data chunk")?;
        if rate == 0 {
            return Err("WAV without a sample rate".into());
        }
        let samples: Vec<f32> = match (fmt, bits) {
            (1, 16) => data.chunks_exact(2).map(|c| i16::from_le_bytes([c[0], c[1]]) as f32 * (1.0 / 32768.0)).collect(),
            (1, 24) => data
                .chunks_exact(3)
                .map(|c| (((c[2] as i32) << 24) | ((c[1] as i32) << 16) | ((c[0] as i32) << 8)) as f32 * (1.0 / 2147483648.0))
                .collect(),
            (1, 32) => data.chunks_exact(4).map(|c| i32::from_le_bytes([c[0], c[1], c[2], c[3]]) as f32 * (1.0 / 2147483648.0)).collect(),
            // A sample that is not a number (NaN, infinity) is silence.
            (3, 32) => data.chunks_exact(4).map(|c| f32::from_le_bytes([c[0], c[1], c[2], c[3]])).map(|x| if x.is_finite() { x } else { 0.0 }).collect(),
            other => return Err(format!("unsupported WAV format {other:?}")),
        };
        Ok(Audio { samples, channels: channels.max(1), sample_rate: rate })
    }

    pub fn frames(&self) -> usize {
        self.samples.len() / self.channels.max(1)
    }

    /// Mean over channels (float32, as the reference averages).
    pub fn mono(&self) -> Vec<f32> {
        mono_of(&self.samples, self.channels)
    }
}

/// Interleaved samples as mono: the mean of each frame, summed pairwise like numpy.
pub fn mono_of(samples: &[f32], channels: usize) -> Vec<f32> {
    let c = channels.max(1);
    if c == 1 {
        return samples.to_vec();
    }
    samples
        .chunks_exact(c)
        .map(|f| {
            let s: f32 = crate::py::pairwise_sum_f32(f);
            s / c as f32
        })
        .collect()
}

/// k-th smallest of a float slice.
fn kth(v: &[f32], k: usize) -> f32 {
    let mut s = v.to_vec();
    s.sort_by(crate::py::fcmp);
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
    s.sort_by(crate::py::fcmp);
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

#[cfg(test)]
mod tests {
    use super::*;

    fn chunk(id: &[u8], body: &[u8]) -> Vec<u8> {
        let mut c = id.to_vec();
        c.extend((body.len() as u32).to_le_bytes());
        c.extend(body);
        if body.len() % 2 == 1 {
            c.push(0);
        }
        c
    }

    fn fmt_body(format: u16, bits: u16) -> Vec<u8> {
        let mut f = Vec::new();
        f.extend(format.to_le_bytes());
        f.extend(1u16.to_le_bytes()); // channels
        f.extend(8000u32.to_le_bytes());
        f.extend((8000 * bits as u32 / 8).to_le_bytes());
        f.extend((bits / 8).to_le_bytes());
        f.extend(bits.to_le_bytes());
        f
    }

    fn wav(chunks: &[Vec<u8>]) -> Vec<u8> {
        let body: Vec<u8> = chunks.concat();
        let mut w = b"RIFF".to_vec();
        w.extend(((body.len() + 4) as u32).to_le_bytes());
        w.extend(b"WAVE");
        w.extend(body);
        w
    }

    fn floats(xs: &[f32]) -> Vec<u8> {
        xs.iter().flat_map(|x| x.to_le_bytes()).collect()
    }

    #[test]
    fn reads_pcm_float_and_extensible() {
        let a = Audio::from_wav(&wav(&[chunk(b"fmt ", &fmt_body(1, 16)), chunk(b"data", &[0, 0x40, 0, 0xC0])])).unwrap();
        assert_eq!((a.samples, a.sample_rate), (vec![0.5, -0.5], 8000));
        let a = Audio::from_wav(&wav(&[chunk(b"fmt ", &fmt_body(3, 32)), chunk(b"data", &floats(&[0.25]))])).unwrap();
        assert_eq!(a.samples, vec![0.25]);
        let mut ext = fmt_body(0xFFFE, 32);
        ext.extend(22u16.to_le_bytes());
        ext.extend(32u16.to_le_bytes());
        ext.extend(4u32.to_le_bytes());
        ext.extend(3u16.to_le_bytes()); // sub-format: float
        ext.extend([0u8; 14]);
        let a = Audio::from_wav(&wav(&[chunk(b"fmt ", &ext), chunk(b"data", &floats(&[0.75]))])).unwrap();
        assert_eq!(a.samples, vec![0.75]);
    }

    #[test]
    fn a_short_or_cut_off_fmt_chunk_is_an_error() {
        // fmt claims 16 bytes, the file ends after 4 of them.
        let mut cut = wav(&[chunk(b"fmt ", &fmt_body(1, 16))]);
        cut.truncate(12 + 8 + 4);
        assert_eq!(Audio::from_wav(&cut).unwrap_err(), "WAV fmt chunk is too short");
        // fmt of 8 bytes followed by the data chunk: its fields are not read from the data chunk.
        let short = wav(&[chunk(b"fmt ", &fmt_body(1, 16)[..8]), chunk(b"data", &[0; 8])]);
        assert_eq!(Audio::from_wav(&short).unwrap_err(), "WAV fmt chunk is too short");
        let ext = wav(&[chunk(b"fmt ", &fmt_body(0xFFFE, 32)), chunk(b"data", &[0; 8])]);
        assert_eq!(Audio::from_wav(&ext).unwrap_err(), "WAV fmt chunk is too short");
        let mut no_rate = fmt_body(1, 16);
        no_rate[4..8].copy_from_slice(&[0; 4]);
        assert!(Audio::from_wav(&wav(&[chunk(b"fmt ", &no_rate), chunk(b"data", &[0; 4])])).is_err());
    }

    #[test]
    fn a_chunk_longer_than_the_file_ends_with_it() {
        let mut w = wav(&[chunk(b"fmt ", &fmt_body(1, 16)), chunk(b"data", &[0, 0x40])]);
        let n = w.len();
        w[n - 6..n - 2].copy_from_slice(&u32::MAX.to_le_bytes());
        assert_eq!(Audio::from_wav(&w).unwrap().samples, vec![0.5]);
        let mut junk = wav(&[chunk(b"fmt ", &fmt_body(1, 16)), chunk(b"data", &[0, 0x40])]);
        junk.extend(b"LIST");
        junk.extend(u32::MAX.to_le_bytes());
        assert_eq!(Audio::from_wav(&junk).unwrap().samples, vec![0.5]);
    }

    #[test]
    fn samples_that_are_not_numbers_are_silence() {
        let a = Audio::from_wav(&wav(&[chunk(b"fmt ", &fmt_body(3, 32)), chunk(b"data", &floats(&[f32::NAN, 0.5, f32::INFINITY, f32::NEG_INFINITY]))])).unwrap();
        assert_eq!(a.samples, vec![0.0, 0.5, 0.0, 0.0]);
        let e = Envelope::of(&Audio { samples: vec![f32::NAN; 400], channels: 1, sample_rate: 8000 });
        assert_eq!(e.db.len(), 5);
        assert_eq!(percentile_f32(&[1.0, f32::NAN, 3.0, 2.0], 50.0), 2.5);
    }
}
