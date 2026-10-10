//! Monophonic line extraction from a note list.

use crate::midi::RawNote;

/// Notes from the contour's pitch-change onsets (onsets.rs) are kept down to this length, and two of them
/// compete for one onset only within SPLIT_MERGE.
pub const SPLIT_MIN_DUR: f64 = 0.03;
pub const SPLIT_MERGE: f64 = 0.02;

/// Highest (or lowest) note among candidates starting within 50 ms of each
/// other, inside a pitch window, ignoring notes shorter than `min_dur` seconds.
pub fn line(notes: &[RawNote], lo: i32, hi: i32, top: bool, min_dur: f64) -> Vec<RawNote> {
    let mut cand: Vec<&RawNote> = notes
        .iter()
        .filter(|n| lo <= n.pitch && n.pitch <= hi && n.offset - n.onset >= if n.split { SPLIT_MIN_DUR } else { min_dur })
        .collect();
    cand.sort_by(|a, b| crate::py::fcmp(&a.onset, &b.onset));
    let mut out: Vec<RawNote> = Vec::new();
    for n in cand {
        if let Some(last) = out.last_mut() {
            let merge = if n.split && last.split { SPLIT_MERGE } else { 0.05 };
            if n.onset - last.onset < merge {
                let better = if top { n.pitch > last.pitch } else { n.pitch < last.pitch };
                if better {
                    *last = n.clone();
                }
                continue;
            }
        }
        out.push(n.clone());
    }
    out
}

pub const MIN_DUR: f64 = 0.06;
