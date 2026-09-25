//! Free-time (rubato, ad lib.) passages: find them in the beat track, notate them proportionally.
//!
//! 1. [`unstable_runs`] finds runs of beat intervals that fit neither the
//!    piece's tempo nor its double or half, nor a beat split in two. A run must
//!    span at least `MIN_INTERVALS` intervals and `MIN_SECONDS` seconds, and its
//!    intervals must vary. Fewer than `MIN_STABLE` stable-looking intervals
//!    inside a run do not end it.
//! 2. [`plan_free_time`] replaces each run's beats with evenly spaced synthetic
//!    beats at a local tempo, rounded to whole bars so the strict grid resumes on
//!    a bar line at the first stable downbeat.

use crate::model::{FreeRegion, Note, TICKS_PER_BEAT};
use crate::py;

pub const RATIO_TOL: f64 = 0.25;
pub const MIN_INTERVALS: usize = 3;
pub const MIN_SECONDS: f64 = 4.0;
pub const MIN_CV: f64 = 0.2;
pub const MIN_STABLE: usize = 4;
pub const TEMPO_RANGE: (f64, f64) = (40.0, 100.0);
pub const TARGET_IOI_BEATS: f64 = 2.0;

fn stable(ratio: f64) -> bool {
    [0.5, 1.0, 2.0].iter().any(|&m| (ratio - m).abs() <= RATIO_TOL * m)
}

fn mean(a: &[f64]) -> f64 {
    py::pairwise_sum_f64(a) / a.len() as f64
}

fn std(a: &[f64]) -> f64 {
    let m = mean(a);
    let sq: Vec<f64> = a.iter().map(|x| {
        let d = x - m;
        d * d
    }).collect();
    (py::pairwise_sum_f64(&sq) / a.len() as f64).sqrt()
}

/// (first, last) beat indices of each free-time run.
pub fn unstable_runs(t: &[f64]) -> Vec<(usize, usize)> {
    if t.len() < 3 {
        return Vec::new();
    }
    let ibi: Vec<f64> = t.windows(2).map(|w| w[1] - w[0]).collect();
    let rf = py::median(&ibi);
    let ratio: Vec<f64> = ibi.iter().map(|x| x / rf).collect();
    let mut ok: Vec<bool> = ratio.iter().map(|&r| stable(r)).collect();
    // A beat split in two is a tracker glitch, not free time.
    for i in 0..ibi.len() - 1 {
        if !ok[i] && !ok[i + 1] && stable(ratio[i] + ratio[i + 1]) {
            ok[i] = true;
            ok[i + 1] = true;
        }
    }
    // Short stable islands between unstable intervals belong to the run.
    let bad: Vec<usize> = (0..ok.len()).filter(|&i| !ok[i]).collect();
    for w in bad.windows(2) {
        let (x, y) = (w[0], w[1]);
        if 1 < y - x && y - x <= MIN_STABLE {
            for v in ok.iter_mut().take(y).skip(x + 1) {
                *v = false;
            }
        }
    }
    let mut runs = Vec::new();
    let mut i = 0;
    while i < ibi.len() {
        if ok[i] {
            i += 1;
            continue;
        }
        let mut j = i;
        while j + 1 < ibi.len() && !ok[j + 1] {
            j += 1;
        }
        let seg = &ibi[i..=j];
        if j - i + 1 >= MIN_INTERVALS && py::pairwise_sum_f64(seg) >= MIN_SECONDS && std(seg) / mean(seg) >= MIN_CV {
            runs.push((i, j + 1));
        }
        i = j + 1;
    }
    runs
}

/// BPM at which the median gap between distinct onsets in [t0, t1) is TARGET_IOI_BEATS, clamped to TEMPO_RANGE.
pub fn local_tempo(onsets: &[f64], t0: f64, t1: f64) -> f64 {
    let mut on: Vec<f64> = onsets.to_vec();
    on.sort_by(|a, b| a.partial_cmp(b).unwrap());
    let mut on: Vec<f64> = on.iter().map(|&x| py::np_round(x, 2)).collect();
    on.dedup();
    let on: Vec<f64> = on.into_iter().filter(|&x| x >= t0 && x < t1).collect();
    let gaps: Vec<f64> = on.windows(2).map(|w| w[1] - w[0]).filter(|&g| g > 0.12).collect();
    if gaps.is_empty() {
        return TEMPO_RANGE.0;
    }
    let bpm = 60.0 * TARGET_IOI_BEATS / py::median(&gaps);
    bpm.clamp(TEMPO_RANGE.0, TEMPO_RANGE.1)
}

/// One free-time region of a plan: beat index start and end, seconds, BPM.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Span {
    pub start: usize,
    pub end: usize,
    pub start_s: f64,
    pub end_s: f64,
    pub bpm: f64,
}

#[derive(Debug, Clone, PartialEq)]
pub struct FreeTimePlan {
    pub beat_times: Vec<f64>,
    /// Bar phase: a bar starts on this beat index (and every beats_per_bar from it).
    pub first_downbeat: i64,
    pub spans: Vec<Span>,
    /// "proportional" | "tempo"
    pub notation: &'static str,
    pub label: String,
}

impl FreeTimePlan {
    /// [start, end) beat indices of each region (for the quantizer's coarse grids).
    pub fn beat_ranges(&self) -> Vec<(f64, f64)> {
        self.spans.iter().map(|s| (s.start as f64, s.end as f64)).collect()
    }

    /// FreeRegions in ticks, with tick 0 at beat `first_downbeat`.
    pub fn regions(&self, first_downbeat: i64) -> Vec<FreeRegion> {
        self.spans
            .iter()
            .map(|s| FreeRegion {
                start: (s.start as i64 - first_downbeat) * TICKS_PER_BEAT,
                end: (s.end as i64 - first_downbeat) * TICKS_PER_BEAT,
                start_s: s.start_s,
                end_s: s.end_s,
                tempo_bpm: py::py_round(s.bpm, 2),
                notation: self.notation.to_string(),
                label: self.label.clone(),
            })
            .collect()
    }
}

/// Replace free-time runs by bar-aligned synthetic beats.
///
/// `downbeats` (per beat, e.g. beat position == 1) picks where the strict grid
/// resumes: the first labelled downbeat at or after the run's end. Without
/// labels, bars count from `first_downbeat`. A run that starts at the first beat
/// also takes in every onset before it and becomes the start of the piece. The
/// local tempo comes from `tempo_onsets` (default `onsets`); `tempo` notates
/// every region at that BPM instead.
pub fn plan_free_time(
    t: &[f64],
    onsets: &[f64],
    beats_per_bar: i64,
    first_downbeat: i64,
    downbeats: Option<&[bool]>,
    tempo: Option<f64>,
    tempo_onsets: Option<&[f64]>,
) -> FreeTimePlan {
    let label = "ad lib.".to_string();
    let runs = unstable_runs(t);
    let unchanged = |t: &[f64]| FreeTimePlan { beat_times: t.to_vec(), first_downbeat, spans: Vec::new(), notation: "proportional", label: label.clone() };
    if runs.is_empty() {
        return unchanged(t);
    }
    let is_down = |k: usize| -> bool {
        match downbeats {
            Some(d) => d[k],
            None => py::pymod(k as i64 - first_downbeat, beats_per_bar) == 0,
        }
    };
    let on_min = onsets.iter().cloned().fold(f64::INFINITY, f64::min);
    let mut out: Vec<f64> = Vec::new();
    let mut spans: Vec<Span> = Vec::new();
    let mut cursor = 0usize;
    let mut new_first = first_downbeat;
    for &(a0, b) in &runs {
        let Some(r) = (b..t.len()).find(|&k| is_down(k)) else { continue };
        let at_start = a0 == 0;
        let mut a = a0;
        if !at_start {
            // Start on the last bar line at or before the run.
            let base = out.len() as i64;
            a = (cursor..=a0)
                .filter(|&k| py::pymod(base + k as i64 - cursor as i64 - new_first, beats_per_bar) == 0)
                .max()
                .unwrap_or(a0);
        }
        if a < cursor {
            continue;
        }
        let s0 = if at_start && !onsets.is_empty() { t[a].min(on_min) } else { t[a] };
        let s1 = t[r];
        let bpm = tempo.unwrap_or_else(|| local_tempo(tempo_onsets.unwrap_or(onsets), s0, s1));
        let n = ((((s1 - s0) * bpm / 60.0 / beats_per_bar as f64).ceil() as i64).max(1) * beats_per_bar) as usize;
        let bpm = n as f64 * 60.0 / (s1 - s0);
        out.extend_from_slice(&t[cursor..a]);
        let start_idx = out.len();
        for k in 0..n {
            out.push(s0 + (k as f64 * (s1 - s0)) / n as f64);
        }
        spans.push(Span { start: start_idx, end: start_idx + n, start_s: s0, end_s: s1, bpm });
        if at_start {
            new_first = start_idx as i64;
        }
        cursor = r;
    }
    out.extend_from_slice(&t[cursor..]);
    if spans.is_empty() {
        return unchanged(t);
    }
    FreeTimePlan { beat_times: out, first_downbeat: new_first, spans, notation: if tempo.is_some() { "tempo" } else { "proportional" }, label }
}

/// End notes that start inside a free region at its end, so the strict grid resumes on a clean bar.
pub fn clip_to_regions(notes: &mut [Note], regions: &[FreeRegion]) {
    for r in regions {
        for n in notes.iter_mut() {
            if r.start <= n.start && n.start < r.end && r.end < n.end() {
                n.dur = r.end - n.start;
            }
        }
    }
}

/// Fermata on the last note of a line that starts inside each free region.
pub fn mark_fermatas(notes: &mut [Note], regions: &[FreeRegion]) {
    for r in regions {
        let mut last: Option<usize> = None;
        for (i, n) in notes.iter().enumerate() {
            if r.start <= n.start && n.start < r.end && last.map_or(true, |l| n.start > notes[l].start) {
                last = Some(i);
            }
        }
        if let Some(i) = last {
            if !notes[i].articulations.iter().any(|a| a == "fermata") {
                notes[i].articulations.push("fermata".into());
            }
        }
    }
}
